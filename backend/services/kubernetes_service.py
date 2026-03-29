"""
Enhanced Kubernetes API service for workload discovery and management
"""

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes_asyncio import client as async_client, config as async_config
from typing import Optional, Dict, Any, List, Tuple
import base64
import tempfile
import structlog
import asyncio
import json
from datetime import datetime, timezone
import yaml

from database.postgresql import database
# from database.neo4j import neo4j_service  # To be enabled when graph operations are needed
# from database.clickhouse import clickhouse_service  # Disabled for MVP

logger = structlog.get_logger()


class KubernetesService:
    """Enhanced Kubernetes API service"""
    
    def __init__(self):
        self.api_client = None
        self.core_v1 = None
        self.apps_v1 = None
        self._cluster_configs = {}  # Cache cluster configs
    
    def _get_client_for_cluster(self, cluster_id: int) -> Tuple[client.CoreV1Api, client.AppsV1Api]:
        """Get Kubernetes clients for specific cluster"""
        if cluster_id not in self._cluster_configs:
            raise ValueError(f"Cluster {cluster_id} not configured")
        
        config_data = self._cluster_configs[cluster_id]
        
        # Configure client based on cluster config
        if config_data.get("kubeconfig"):
            kubeconfig_data = base64.b64decode(config_data["kubeconfig"]).decode('utf-8')
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_data)
                kubeconfig_path = f.name
            
            config.load_kube_config(config_file=kubeconfig_path)
            
        elif config_data.get("service_account_token"):
            configuration = client.Configuration()
            configuration.host = config_data["api_url"]
            configuration.api_key_prefix['authorization'] = 'Bearer'
            configuration.api_key['authorization'] = config_data["service_account_token"]
            
            # TLS verification - use CA cert if provided, otherwise respect skip_tls_verify flag
            if config_data.get("ca_cert"):
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.crt') as f:
                    f.write(config_data["ca_cert"])
                    configuration.ssl_ca_cert = f.name
                configuration.verify_ssl = True
            elif config_data.get("skip_tls_verify"):
                configuration.verify_ssl = False
                logger.warning("TLS verification disabled for cluster", 
                             api_url=config_data["api_url"],
                             security_warning="This is NOT recommended for production!")
            else:
                configuration.verify_ssl = True  # Default: verify TLS
            
            client.Configuration.set_default(configuration)
        else:
            # In-cluster config
            config.load_incluster_config()
        
        return client.CoreV1Api(), client.AppsV1Api()
    
    async def configure_cluster(self, cluster_id: int, api_url: str, kubeconfig: str = None, token: str = None):
        """Configure cluster connection"""
        self._cluster_configs[cluster_id] = {
            "api_url": api_url,
            "kubeconfig": kubeconfig,
            "service_account_token": token
        }
        
        logger.info("Cluster configured", cluster_id=cluster_id)
    
    async def test_cluster_connection(
        self, 
        api_url: str,
        kubeconfig: Optional[str] = None,
        service_account_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test connection to Kubernetes cluster"""
        try:
            # Temporarily configure client
            if kubeconfig:
                kubeconfig_data = base64.b64decode(kubeconfig).decode('utf-8')
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    f.write(kubeconfig_data)
                    kubeconfig_path = f.name
                
                config.load_kube_config(config_file=kubeconfig_path)
                
            elif service_account_token:
                configuration = client.Configuration()
                configuration.host = api_url
                configuration.api_key_prefix['authorization'] = 'Bearer'
                configuration.api_key['authorization'] = service_account_token
                # Note: For test_cluster_connection, TLS verification should be handled
                # by the caller passing CA cert or skip_tls_verify flag
                configuration.verify_ssl = True  # Default: secure
                
                client.Configuration.set_default(configuration)
            else:
                config.load_incluster_config()
            
            # Test connection
            core_v1 = client.CoreV1Api()
            
            # Get cluster version info
            version = await asyncio.get_event_loop().run_in_executor(
                None, core_v1.get_api_versions
            )
            
            # Get nodes to count
            nodes = await asyncio.get_event_loop().run_in_executor(
                None, core_v1.list_node
            )
            
            # Get namespaces to count
            namespaces = await asyncio.get_event_loop().run_in_executor(
                None, core_v1.list_namespace
            )
            
            return {
                "healthy": True,
                "version": version.versions[0] if version.versions else "unknown",
                "api_accessible": True,
                "node_count": len(nodes.items),
                "namespace_count": len(namespaces.items)
            }
            
        except Exception as e:
            logger.error("Cluster connection test failed", error=str(e), api_url=api_url)
            return {
                "healthy": False,
                "error": str(e),
                "api_accessible": False
            }
    
    async def discover_namespaces(self, cluster_id: int) -> List[Dict[str, Any]]:
        """Discover namespaces in cluster"""
        try:
            core_v1, _ = self._get_client_for_cluster(cluster_id)
            
            # Get namespaces
            namespaces = await asyncio.get_event_loop().run_in_executor(
                None, core_v1.list_namespace
            )
            
            discovered = []
            for ns in namespaces.items:
                discovered.append({
                    "name": ns.metadata.name,
                    "uid": ns.metadata.uid,
                    "labels": ns.metadata.labels or {},
                    "annotations": ns.metadata.annotations or {},
                    "status": ns.status.phase,
                    "created_at": ns.metadata.creation_timestamp
                })
            
            logger.info("Namespaces discovered", cluster_id=cluster_id, count=len(discovered))
            return discovered
            
        except Exception as e:
            logger.error("Namespace discovery failed", cluster_id=cluster_id, error=str(e))
            return []
    
    async def discover_pods(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover pods in cluster/namespace"""
        try:
            core_v1, _ = self._get_client_for_cluster(cluster_id)
            
            # Get pods
            if namespace:
                pods = await asyncio.get_event_loop().run_in_executor(
                    None, core_v1.list_namespaced_pod, namespace
                )
            else:
                pods = await asyncio.get_event_loop().run_in_executor(
                    None, core_v1.list_pod_for_all_namespaces
                )
            
            discovered = []
            for pod in pods.items:
                # Container info
                containers = []
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        containers.append({
                            "name": container.name,
                            "image": container.image,
                            "ports": [{"port": p.container_port, "protocol": p.protocol} for p in (container.ports or [])]
                        })
                
                discovered.append({
                    "workload_type": "pod",
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "uid": pod.metadata.uid,
                    "labels": pod.metadata.labels or {},
                    "annotations": pod.metadata.annotations or {},
                    "ip_address": pod.status.pod_ip,
                    "node_name": pod.spec.node_name,
                    "status": pod.status.phase,
                    "containers": containers,
                    "owner_references": [
                        {
                            "kind": ref.kind,
                            "name": ref.name,
                            "uid": ref.uid
                        } 
                        for ref in (pod.metadata.owner_references or [])
                    ],
                    "created_at": pod.metadata.creation_timestamp,
                    "restart_count": sum([cs.restart_count for cs in (pod.status.container_statuses or [])]),
                    "ready": all([cs.ready for cs in (pod.status.container_statuses or [])]) if pod.status.container_statuses else False
                })
            
            logger.info("Pods discovered", cluster_id=cluster_id, namespace=namespace, count=len(discovered))
            return discovered
            
        except Exception as e:
            logger.error("Pod discovery failed", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return []
    
    async def discover_deployments(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover deployments in cluster/namespace"""
        try:
            _, apps_v1 = self._get_client_for_cluster(cluster_id)
            
            # Get deployments
            if namespace:
                deployments = await asyncio.get_event_loop().run_in_executor(
                    None, apps_v1.list_namespaced_deployment, namespace
                )
            else:
                deployments = await asyncio.get_event_loop().run_in_executor(
                    None, apps_v1.list_deployment_for_all_namespaces
                )
            
            discovered = []
            for deployment in deployments.items:
                discovered.append({
                    "workload_type": "deployment",
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "uid": deployment.metadata.uid,
                    "labels": deployment.metadata.labels or {},
                    "annotations": deployment.metadata.annotations or {},
                    "replicas": deployment.spec.replicas,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "updated_replicas": deployment.status.updated_replicas or 0,
                    "selector": deployment.spec.selector.match_labels or {},
                    "strategy": deployment.spec.strategy.type if deployment.spec.strategy else "RollingUpdate",
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message
                        }
                        for condition in (deployment.status.conditions or [])
                    ],
                    "created_at": deployment.metadata.creation_timestamp
                })
            
            logger.info("Deployments discovered", cluster_id=cluster_id, namespace=namespace, count=len(discovered))
            return discovered
            
        except Exception as e:
            logger.error("Deployment discovery failed", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return []
    
    async def discover_services(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover services in cluster/namespace"""
        try:
            core_v1, _ = self._get_client_for_cluster(cluster_id)
            
            # Get services
            if namespace:
                services = await asyncio.get_event_loop().run_in_executor(
                    None, core_v1.list_namespaced_service, namespace
                )
            else:
                services = await asyncio.get_event_loop().run_in_executor(
                    None, core_v1.list_service_for_all_namespaces
                )
            
            discovered = []
            for service in services.items:
                # Port mappings
                ports = []
                if service.spec.ports:
                    for port in service.spec.ports:
                        ports.append({
                            "name": port.name,
                            "port": port.port,
                            "target_port": port.target_port,
                            "protocol": port.protocol
                        })
                
                discovered.append({
                    "workload_type": "service",
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "uid": service.metadata.uid,
                    "labels": service.metadata.labels or {},
                    "annotations": service.metadata.annotations or {},
                    "service_type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": service.spec.external_i_ps or [],
                    "ports": ports,
                    "selector": service.spec.selector or {},
                    "session_affinity": service.spec.session_affinity,
                    "created_at": service.metadata.creation_timestamp
                })
            
            logger.info("Services discovered", cluster_id=cluster_id, namespace=namespace, count=len(discovered))
            return discovered
            
        except Exception as e:
            logger.error("Service discovery failed", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return []
    
    async def discover_statefulsets(self, cluster_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover statefulsets in cluster/namespace"""
        try:
            _, apps_v1 = self._get_client_for_cluster(cluster_id)
            
            # Get statefulsets
            if namespace:
                statefulsets = await asyncio.get_event_loop().run_in_executor(
                    None, apps_v1.list_namespaced_stateful_set, namespace
                )
            else:
                statefulsets = await asyncio.get_event_loop().run_in_executor(
                    None, apps_v1.list_stateful_set_for_all_namespaces
                )
            
            discovered = []
            for sts in statefulsets.items:
                # Volume claim templates
                volume_claims = []
                if sts.spec.volume_claim_templates:
                    for vct in sts.spec.volume_claim_templates:
                        volume_claims.append({
                            "name": vct.metadata.name,
                            "storage": vct.spec.resources.requests.get("storage", "unknown"),
                            "access_modes": vct.spec.access_modes or []
                        })
                
                discovered.append({
                    "workload_type": "statefulset",
                    "name": sts.metadata.name,
                    "namespace": sts.metadata.namespace,
                    "uid": sts.metadata.uid,
                    "labels": sts.metadata.labels or {},
                    "annotations": sts.metadata.annotations or {},
                    "replicas": sts.spec.replicas,
                    "ready_replicas": sts.status.ready_replicas or 0,
                    "current_replicas": sts.status.current_replicas or 0,
                    "updated_replicas": sts.status.updated_replicas or 0,
                    "service_name": sts.spec.service_name,
                    "selector": sts.spec.selector.match_labels or {},
                    "update_strategy": sts.spec.update_strategy.type if sts.spec.update_strategy else "RollingUpdate",
                    "volume_claim_templates": volume_claims,
                    "created_at": sts.metadata.creation_timestamp
                })
            
            logger.info("StatefulSets discovered", cluster_id=cluster_id, namespace=namespace, count=len(discovered))
            return discovered
            
        except Exception as e:
            logger.error("StatefulSet discovery failed", cluster_id=cluster_id, namespace=namespace, error=str(e))
            return []
    
    async def full_cluster_discovery(self, cluster_id: int) -> Dict[str, int]:
        """Run full cluster discovery and store in database"""
        try:
            # Get cluster info from database
            cluster_query = "SELECT name, api_server_url, kubeconfig_encrypted, token_encrypted FROM clusters WHERE id = :cluster_id"
            cluster = await database.fetch_one(cluster_query, {"cluster_id": cluster_id})
            
            if not cluster:
                raise ValueError(f"Cluster {cluster_id} not found")
            
            # Configure cluster connection
            await self.configure_cluster(
                cluster_id,
                cluster["api_server_url"],
                cluster["kubeconfig_encrypted"],
                cluster["token_encrypted"]
            )
            
            # Start discovery
            logger.info("Starting full cluster discovery", cluster_id=cluster_id)
            
            # Discover namespaces
            namespaces = await self.discover_namespaces(cluster_id)
            
            # Store namespaces in database
            namespace_count = 0
            for ns in namespaces:
                await self._store_namespace(cluster_id, ns)
                namespace_count += 1
            
            # Discover all workloads
            workload_count = 0
            
            # Pods
            pods = await self.discover_pods(cluster_id)
            for pod in pods:
                await self._store_workload(cluster_id, pod)
                workload_count += 1
            
            # Deployments
            deployments = await self.discover_deployments(cluster_id)
            for deployment in deployments:
                await self._store_workload(cluster_id, deployment)
                workload_count += 1
            
            # Services
            services = await self.discover_services(cluster_id)
            for service in services:
                await self._store_workload(cluster_id, service)
                workload_count += 1
            
            # StatefulSets
            statefulsets = await self.discover_statefulsets(cluster_id)
            for sts in statefulsets:
                await self._store_workload(cluster_id, sts)
                workload_count += 1
            
            # Update cluster statistics
            await database.execute(
                """UPDATE clusters SET 
                   namespace_count = :ns_count,
                   workload_count = :wl_count,
                   last_sync_at = :now,
                   health_status = 'healthy'
                   WHERE id = :cluster_id""",
                {
                    "ns_count": namespace_count,
                    "wl_count": workload_count,
                    "now": datetime.utcnow(),
                    "cluster_id": cluster_id
                }
            )
            
            logger.info("Cluster discovery completed", 
                       cluster_id=cluster_id, 
                       namespaces=namespace_count,
                       workloads=workload_count)
            
            return {
                "namespaces": namespace_count,
                "workloads": workload_count,
                "pods": len(pods),
                "deployments": len(deployments),
                "services": len(services),
                "statefulsets": len(statefulsets)
            }
            
        except Exception as e:
            logger.error("Full cluster discovery failed", cluster_id=cluster_id, error=str(e))
            
            # Mark cluster as unhealthy
            await database.execute(
                "UPDATE clusters SET health_status = 'unhealthy', last_sync_at = :now WHERE id = :cluster_id",
                {"now": datetime.utcnow(), "cluster_id": cluster_id}
            )
            
            return {}
    
    async def _store_namespace(self, cluster_id: int, namespace_data: Dict[str, Any]):
        """Store namespace in database"""
        try:
            # Insert or update namespace
            await database.execute(
                """
                INSERT INTO namespaces (cluster_id, name, uid, labels, annotations, status)
                VALUES (:cluster_id, :name, :uid, :labels, :annotations, :status)
                ON CONFLICT (cluster_id, name) 
                DO UPDATE SET 
                    uid = EXCLUDED.uid,
                    labels = EXCLUDED.labels,
                    annotations = EXCLUDED.annotations,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                {
                    "cluster_id": cluster_id,
                    "name": namespace_data["name"],
                    "uid": namespace_data["uid"],
                    "labels": json.dumps(namespace_data["labels"]),
                    "annotations": json.dumps(namespace_data["annotations"]),
                    "status": namespace_data["status"]
                }
            )
            
        except Exception as e:
            logger.error("Failed to store namespace", error=str(e), namespace=namespace_data["name"])
    
    async def _store_workload(self, cluster_id: int, workload_data: Dict[str, Any]):
        """Store workload in database"""
        try:
            # Get namespace_id
            namespace_query = "SELECT id FROM namespaces WHERE cluster_id = :cluster_id AND name = :namespace"
            namespace_record = await database.fetch_one(namespace_query, {
                "cluster_id": cluster_id,
                "namespace": workload_data["namespace"]
            })
            
            if not namespace_record:
                logger.warning("Namespace not found for workload", 
                             workload=workload_data["name"], 
                             namespace=workload_data["namespace"])
                return
            
            namespace_id = namespace_record["id"]
            
            # Insert or update workload
            await database.execute(
                """
                INSERT INTO workloads (
                    cluster_id, namespace_id, workload_type, name, uid,
                    labels, annotations, ip_address, ports, replicas,
                    status, containers, node_name, first_seen, last_seen, is_active, metadata
                )
                VALUES (
                    :cluster_id, :namespace_id, :workload_type, :name, :uid,
                    :labels, :annotations, :ip_address, :ports, :replicas,
                    :status, :containers, :node_name, :now, :now, true, :metadata
                )
                ON CONFLICT (cluster_id, namespace_id, workload_type, name)
                DO UPDATE SET
                    uid = EXCLUDED.uid,
                    labels = EXCLUDED.labels,
                    annotations = EXCLUDED.annotations,
                    ip_address = EXCLUDED.ip_address,
                    ports = EXCLUDED.ports,
                    replicas = EXCLUDED.replicas,
                    status = EXCLUDED.status,
                    containers = EXCLUDED.containers,
                    node_name = EXCLUDED.node_name,
                    last_seen = EXCLUDED.last_seen,
                    is_active = true,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                {
                    "cluster_id": cluster_id,
                    "namespace_id": namespace_id,
                    "workload_type": workload_data["workload_type"],
                    "name": workload_data["name"],
                    "uid": workload_data["uid"],
                    "labels": json.dumps(workload_data["labels"]),
                    "annotations": json.dumps(workload_data["annotations"]),
                    "ip_address": workload_data.get("ip_address"),
                    "ports": json.dumps(workload_data.get("ports", [])),
                    "replicas": workload_data.get("replicas"),
                    "status": workload_data.get("status"),
                    "containers": json.dumps(workload_data.get("containers", [])),
                    "node_name": workload_data.get("node_name"),
                    "now": datetime.utcnow(),
                    "metadata": json.dumps(workload_data)
                }
            )
            
            # Store in Neo4j (currently disabled - uncomment neo4j import to enable)
            # await self._store_workload_in_graph(cluster_id, workload_data)
            
        except Exception as e:
            logger.error("Failed to store workload", error=str(e), workload=workload_data["name"])
    
    async def _store_workload_in_graph(self, cluster_id: int, workload_data: Dict[str, Any]):
        """Store workload in Neo4j graph database"""
        try:
            workload_id = f"{cluster_id}:{workload_data['namespace']}:{workload_data['name']}"
            
            # Insert vertex based on workload type
            if workload_data["workload_type"] == "pod":
                success = neo4j_service.insert_pod(
                    workload_id,
                    workload_data["name"],
                    workload_data["namespace"],
                    str(cluster_id),
                    workload_data.get("ip_address", ""),
                    workload_data.get("status", "Unknown")
                )
            else:
                # For non-pod workloads, use generic insertion
                # TODO: Implement specific methods for deployment, service, statefulset
                success = True
            
            if success:
                logger.debug("Workload stored in graph", workload=workload_data["name"])
            
        except Exception as e:
            logger.error("Failed to store workload in graph", error=str(e), workload=workload_data["name"])


# Global service instance
k8s_service = KubernetesService()