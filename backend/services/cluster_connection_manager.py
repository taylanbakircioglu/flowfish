"""
Cluster Connection Manager

Unified entry point for all cluster operations.
Manages connections to multiple clusters (in-cluster and remote).

Features:
- Connection pooling and caching
- Automatic connection type detection
- Credential management from database
- Health monitoring support
- Fallback to legacy services for backward compatibility
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import structlog

from database.postgresql import database
from utils.encryption import decrypt_data
from services.connections.base import (
    ClusterConnection, ConnectionConfig, ClusterInfo, GadgetHealth,
    Namespace, Deployment, Pod, Service
)
from services.connections.in_cluster import InClusterConnection
from services.connections.remote_token import RemoteTokenConnection

# Legacy imports for fallback
from services.cluster_info_service import cluster_info_service
from grpc_clients.cluster_manager_client import cluster_manager_client

logger = structlog.get_logger()


class ClusterConnectionManager:
    """
    Unified manager for all cluster connections.
    
    Provides a single entry point for:
    - Cluster information retrieval
    - Namespace/Deployment/Pod/Service listing
    - Gadget health checking
    - Connection testing
    
    Automatically determines the correct connection method based on
    cluster configuration stored in the database.
    """
    
    def __init__(self):
        self._connections: Dict[int, ClusterConnection] = {}
        self._connection_configs: Dict[int, ConnectionConfig] = {}
        self._lock = asyncio.Lock()
        
        # Legacy services for fallback
        self._legacy_cluster_info = cluster_info_service
        self._legacy_cluster_manager = cluster_manager_client
    
    # =========================================================================
    # Connection Management
    # =========================================================================
    
    async def get_connection(self, cluster_id: int) -> ClusterConnection:
        """
        Get or create a connection for a cluster.
        
        Lazily creates connections as needed and caches them.
        Automatically determines the correct connection type from database.
        """
        async with self._lock:
            # Return cached connection if available
            if cluster_id in self._connections:
                connection = self._connections[cluster_id]
                if connection.is_connected:
                    return connection
            
            # Get or refresh connection config
            config = await self._get_connection_config(cluster_id)
            if not config:
                raise ValueError(f"Cluster {cluster_id} not found or inactive")
            
            # Create appropriate connection type
            connection = self._create_connection(config)
            
            # Connect
            success = await connection.connect()
            if not success:
                raise ConnectionError(f"Failed to connect to cluster {cluster_id}")
            
            # Cache
            self._connections[cluster_id] = connection
            self._connection_configs[cluster_id] = config
            
            return connection
    
    async def _get_connection_config(self, cluster_id: int) -> Optional[ConnectionConfig]:
        """Load connection configuration from database"""
        # Note: Live database uses api_server_url (not api_url) and status='active' (not is_active=true)
        # This is due to migration job schema differing from postgresql-schema.sql
        query = """
            SELECT id, name, connection_type, api_server_url, 
                   token_encrypted as token,
                   ca_cert_encrypted as ca_cert,
                   kubeconfig_encrypted as kubeconfig,
                   skip_tls_verify, gadget_endpoint, gadget_namespace
            FROM clusters 
            WHERE id = :cluster_id AND status = 'active'
        """
        
        try:
            result = await database.fetch_one(query, {"cluster_id": cluster_id})
            if not result:
                return None
            
            # Decrypt sensitive fields
            token = decrypt_data(result["token"]) if result["token"] else None
            ca_cert = decrypt_data(result["ca_cert"]) if result["ca_cert"] else None
            kubeconfig = decrypt_data(result["kubeconfig"]) if result["kubeconfig"] else None
            
            return ConnectionConfig(
                cluster_id=result["id"],
                name=result["name"],
                connection_type=result["connection_type"] or "in-cluster",
                api_server_url=result["api_server_url"],
                token=token,
                ca_cert=ca_cert,
                kubeconfig=kubeconfig,
                skip_tls_verify=result["skip_tls_verify"] or False,
                gadget_endpoint=result["gadget_endpoint"],
                gadget_namespace=result["gadget_namespace"]
            )
        except Exception as e:
            logger.error("Failed to get connection config", cluster_id=cluster_id, error=str(e))
            return None
    
    def _create_connection(self, config: ConnectionConfig) -> ClusterConnection:
        """Create appropriate connection based on type"""
        connection_type = config.connection_type.lower().replace('_', '-')
        
        if connection_type == "in-cluster":
            return InClusterConnection(config)
        elif connection_type == "token":
            return RemoteTokenConnection(config)
        elif connection_type == "kubeconfig":
            # TODO: Implement RemoteKubeconfigConnection
            # For now, fall back to token-like behavior
            logger.warning("Kubeconfig connection not fully implemented, using token fallback")
            return RemoteTokenConnection(config)
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")
    
    async def close_connection(self, cluster_id: int) -> None:
        """Close and remove a specific cluster connection"""
        async with self._lock:
            if cluster_id in self._connections:
                connection = self._connections[cluster_id]
                await connection.disconnect()
                del self._connections[cluster_id]
                if cluster_id in self._connection_configs:
                    del self._connection_configs[cluster_id]
                logger.info("Connection closed", cluster_id=cluster_id)
    
    async def close_all(self) -> None:
        """Close all connections"""
        async with self._lock:
            for cluster_id, connection in list(self._connections.items()):
                try:
                    await connection.disconnect()
                except Exception as e:
                    logger.warning("Error closing connection", cluster_id=cluster_id, error=str(e))
            self._connections.clear()
            self._connection_configs.clear()
            logger.info("All connections closed")
    
    async def refresh_connection(self, cluster_id: int) -> bool:
        """Close and recreate a connection (e.g., after config change)"""
        await self.close_connection(cluster_id)
        try:
            await self.get_connection(cluster_id)
            return True
        except Exception as e:
            logger.error("Failed to refresh connection", cluster_id=cluster_id, error=str(e))
            return False
    
    # =========================================================================
    # Cluster Information
    # =========================================================================
    
    async def get_cluster_info(self, cluster_id: int) -> Dict[str, Any]:
        """
        Get cluster information.
        
        Returns dict for backward compatibility with existing code.
        """
        try:
            connection = await self.get_connection(cluster_id)
            info = await connection.get_cluster_info()
            return info.to_dict()
        except Exception as e:
            logger.error("Failed to get cluster info", cluster_id=cluster_id, error=str(e))
            return {"error": str(e)}
    
    async def check_gadget_health(self, cluster_id: int) -> Dict[str, Any]:
        """
        Check Inspector Gadget health.
        
        Returns dict for backward compatibility.
        """
        try:
            connection = await self.get_connection(cluster_id)
            health = await connection.check_gadget_health()
            return health.to_dict()
        except Exception as e:
            logger.error("Failed to check gadget health", cluster_id=cluster_id, error=str(e))
            return {
                "health_status": "unknown",
                "error": str(e)
            }
    
    async def get_namespaces(self, cluster_id: int) -> List[Dict[str, Any]]:
        """Get list of namespaces"""
        try:
            connection = await self.get_connection(cluster_id)
            namespaces = await connection.get_namespaces()
            return [ns.to_dict() for ns in namespaces]
        except Exception as e:
            logger.error("Failed to get namespaces", cluster_id=cluster_id, error=str(e))
            return []
    
    async def get_deployments(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of deployments. Raises on error so callers can distinguish failure from empty."""
        connection = await self.get_connection(cluster_id)
        deployments = await connection.get_deployments(namespace)
        return [dep.to_dict() for dep in deployments]
    
    async def get_pods(self, cluster_id: int, namespace: Optional[str] = None, 
                      label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of pods"""
        try:
            connection = await self.get_connection(cluster_id)
            pods = await connection.get_pods(namespace, label_selector)
            return [pod.to_dict() for pod in pods]
        except Exception as e:
            logger.error("Failed to get pods", cluster_id=cluster_id, error=str(e))
            return []
    
    async def get_services(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of services. Raises on error so callers can distinguish failure from empty."""
        connection = await self.get_connection(cluster_id)
        services = await connection.get_services(namespace)
        return [svc.to_dict() for svc in services]
    
    async def get_network_policies(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of network policies with spec hash. Raises on error."""
        connection = await self.get_connection(cluster_id)
        return await connection.get_network_policies(namespace)

    async def get_ingresses(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of ingresses with spec hash. Raises on error."""
        connection = await self.get_connection(cluster_id)
        return await connection.get_ingresses(namespace)

    async def get_routes(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of OpenShift routes with spec hash. Raises on error."""
        connection = await self.get_connection(cluster_id)
        return await connection.get_routes(namespace)

    async def get_configmaps(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of configmaps with data hash. Raises on error."""
        connection = await self.get_connection(cluster_id)
        configmaps = await connection.get_configmaps(namespace)
        return [cm.to_dict() for cm in configmaps]

    async def get_secrets(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of secrets with data hash. Raises on error."""
        connection = await self.get_connection(cluster_id)
        secrets = await connection.get_secrets(namespace)
        return [sec.to_dict() for sec in secrets]

    async def get_statefulsets(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of statefulsets. Raises on error."""
        connection = await self.get_connection(cluster_id)
        statefulsets = await connection.get_statefulsets(namespace)
        return [sts.to_dict() for sts in statefulsets]

    async def get_labels(self, cluster_id: int, namespace: Optional[str] = None) -> List[str]:
        """Get unique labels"""
        try:
            connection = await self.get_connection(cluster_id)
            return await connection.get_labels(namespace)
        except Exception as e:
            logger.error("Failed to get labels", cluster_id=cluster_id, error=str(e))
            return []
    
    # =========================================================================
    # Connection Testing (for new clusters before saving)
    # =========================================================================
    
    async def test_connection(
        self,
        connection_type: str,
        api_server_url: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        skip_tls_verify: bool = False,
        gadget_namespace: Optional[str] = None  # From UI
    ) -> Dict[str, Any]:
        """
        Test connection without saving to database.
        
        Used by the UI to verify credentials before creating a cluster.
        Tests cluster connection and gadget pods status via K8s API.
        
        Args:
            gadget_namespace: Namespace where Inspector Gadget is deployed (REQUIRED from UI)
        """
        result = {
            "cluster_connection": {"status": "unknown", "error": None, "details": {}},
            "gadget_connection": {"status": "unknown", "error": None, "details": {}},
            "overall_status": "unknown"
        }
        
        normalized_type = connection_type.lower().replace('_', '-')
        
        # Test cluster connection
        try:
            if normalized_type == "in-cluster":
                # Use legacy client for in-cluster test
                info = await self._legacy_cluster_manager.get_cluster_info(cluster_id="test")
            elif normalized_type == "token":
                info = await self._legacy_cluster_info.get_cluster_info(
                    connection_type="token",
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=ca_cert,
                    skip_tls_verify=skip_tls_verify
                )
            elif normalized_type == "kubeconfig":
                info = await self._legacy_cluster_info.get_cluster_info(
                    connection_type="kubeconfig",
                    kubeconfig=kubeconfig,
                    skip_tls_verify=skip_tls_verify
                )
            else:
                raise ValueError(f"Unknown connection type: {connection_type}")
            
            if info.get("error"):
                result["cluster_connection"]["status"] = "failed"
                result["cluster_connection"]["error"] = info["error"]
            else:
                result["cluster_connection"]["status"] = "success"
                result["cluster_connection"]["details"] = {
                    "k8s_version": info.get("k8s_version"),
                    "total_nodes": info.get("total_nodes"),
                    "total_pods": info.get("total_pods"),
                    "total_namespaces": info.get("total_namespaces")
                }
                
        except Exception as e:
            result["cluster_connection"]["status"] = "failed"
            result["cluster_connection"]["error"] = str(e)
        
        # Test gadget connection via K8s API (pod status check)
        if gadget_namespace:
            try:
                if normalized_type == "in-cluster":
                    health = await self._legacy_cluster_manager.check_gadget_health(
                        cluster_id="test",
                        gadget_namespace=gadget_namespace
                    )
                    if health.get("health_status") == "healthy":
                        result["gadget_connection"]["status"] = "success"
                        result["gadget_connection"]["details"] = health
                    else:
                        result["gadget_connection"]["status"] = "warning"
                        result["gadget_connection"]["error"] = health.get("error")
                else:
                    # Remote cluster - check pods via K8s API
                    pods_result = await self._legacy_cluster_info.get_pods(
                        connection_type="token",
                        namespace=gadget_namespace,
                        label_selector="app=inspektor-gadget",
                        api_server_url=api_server_url,
                        token=token,
                        ca_cert=ca_cert,
                        skip_tls_verify=skip_tls_verify
                    )
                    pods = pods_result.get("pods", [])
                    
                    if not pods:
                        result["gadget_connection"]["status"] = "failed"
                        result["gadget_connection"]["error"] = f"No gadget pods found in namespace '{gadget_namespace}'"
                    else:
                        pods_ready = sum(1 for p in pods if p.get("status") == "Running")
                        pods_total = len(pods)
                        
                        if pods_ready == pods_total:
                            result["gadget_connection"]["status"] = "success"
                            result["gadget_connection"]["details"] = {
                                "pods_ready": pods_ready,
                                "pods_total": pods_total,
                                "namespace": gadget_namespace
                            }
                        elif pods_ready > 0:
                            result["gadget_connection"]["status"] = "warning"
                            result["gadget_connection"]["error"] = f"{pods_ready}/{pods_total} pods ready"
                        else:
                            result["gadget_connection"]["status"] = "failed"
                            result["gadget_connection"]["error"] = "No pods ready"
                        
            except Exception as e:
                result["gadget_connection"]["status"] = "failed"
                result["gadget_connection"]["error"] = str(e)
        else:
            result["gadget_connection"]["status"] = "skipped"
            result["gadget_connection"]["error"] = "No namespace provided"
        
        # Determine overall status
        cluster_ok = result["cluster_connection"]["status"] == "success"
        gadget_ok = result["gadget_connection"]["status"] in ["success", "skipped"]
        
        if cluster_ok and gadget_ok:
            result["overall_status"] = "success"
        elif cluster_ok:
            result["overall_status"] = "partial"
        else:
            result["overall_status"] = "failed"
        
        return result
    
    # =========================================================================
    # Health Monitoring
    # =========================================================================
    
    async def health_check_all(self) -> Dict[int, Dict[str, Any]]:
        """Check health of all cached connections"""
        results = {}
        
        for cluster_id, connection in list(self._connections.items()):
            try:
                if connection.is_connected:
                    health = await connection.check_gadget_health()
                    results[cluster_id] = {
                        "connected": True,
                        "gadget_health": health.to_dict()
                    }
                else:
                    results[cluster_id] = {
                        "connected": False,
                        "error": "Connection not active"
                    }
            except Exception as e:
                results[cluster_id] = {
                    "connected": False,
                    "error": str(e)
                }
        
        return results
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about current connections"""
        return {
            "total_connections": len(self._connections),
            "clusters": list(self._connections.keys()),
            "connection_types": {
                cid: conn.connection_type 
                for cid, conn in self._connections.items()
            }
        }


# Singleton instance
cluster_connection_manager = ClusterConnectionManager()

