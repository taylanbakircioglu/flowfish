"""
Remote Token Connection Implementation

Uses cluster-manager gRPC gateway for ALL Kubernetes API access.
This provides centralized credential management and single egress point.

Gateway Pattern Benefits:
- Centralized K8s API access from single pod (cluster-manager)
- Unified credential management and decryption
- Better network security (single egress point)
- Connection pooling and caching in cluster-manager
"""

import re
from typing import List, Optional
import structlog

from .base import (
    ClusterConnection, ConnectionConfig, ClusterInfo, GadgetHealth,
    Namespace, Deployment, Pod, Service, StatefulSet, ConfigMap, Secret
)
from grpc_clients.cluster_manager_client import cluster_manager_client

logger = structlog.get_logger()


class RemoteTokenConnection(ClusterConnection):
    """
    Connection for remote clusters using ServiceAccount token.
    
    Routes ALL K8s API calls through cluster-manager gRPC gateway.
    The gateway handles:
    - Credential decryption
    - Client caching (TTL-based)
    - Connection pooling
    """
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._grpc_client = cluster_manager_client
        
        logger.info(
            "RemoteTokenConnection initialized (gateway mode)",
            cluster_id=config.cluster_id,
            cluster_name=config.name
        )
    
    async def _do_connect(self) -> None:
        """Verify we can connect to the remote cluster via gateway"""
        # Test connection by fetching cluster info via gateway
        try:
            result = await self._grpc_client.get_cluster_info(
                cluster_id=str(self.config.cluster_id)
            )
            if result.get("error"):
                raise ConnectionError(f"Failed to connect via gateway: {result['error']}")
        except Exception as e:
            raise ConnectionError(f"Gateway connection failed: {str(e)}")
    
    async def _do_disconnect(self) -> None:
        """No persistent connection to close (gateway manages connections)"""
        pass
    
    async def get_cluster_info(self) -> ClusterInfo:
        """Get cluster info via gateway"""
        self.mark_used()
        result = await self._grpc_client.get_cluster_info(
            cluster_id=str(self.config.cluster_id)
        )
        
        return ClusterInfo(
            k8s_version=result.get("k8s_version"),
            platform=result.get("platform"),
            total_nodes=result.get("total_nodes", 0),
            total_pods=result.get("total_pods", 0),
            total_namespaces=result.get("total_namespaces", 0),
            error=result.get("error")
        )
    
    async def check_gadget_health(self) -> GadgetHealth:
        """Check gadget health via gateway"""
        self.mark_used()
        
        gadget_namespace = self.config.gadget_namespace
        if not gadget_namespace:
            return GadgetHealth(
                health_status="unknown",
                error="gadget_namespace not configured for this cluster"
            )
        
        try:
            result = await self._grpc_client.check_gadget_health(
                cluster_id=str(self.config.cluster_id),
                gadget_namespace=gadget_namespace
            )
            
            return GadgetHealth(
                health_status=result.get("health_status", "unknown"),
                version=result.get("version"),
                pods_ready=result.get("pods_ready", 0),
                pods_total=result.get("pods_total", 0),
                error=result.get("error"),
                details={
                    "namespace": gadget_namespace,
                    "ebpf_capable": result.get("ebpf_capable", False),
                    "total_restarts": result.get("total_restarts", 0),
                    "issues": result.get("issues", [])
                }
            )
        except Exception as e:
            logger.error(
                "Failed to check gadget health via gateway",
                cluster_id=self.config.cluster_id,
                error=str(e)
            )
            return GadgetHealth(
                health_status="unknown",
                error=f"Gateway error: {str(e)}",
                pods_ready=0,
                pods_total=0
            )
    
    async def get_namespaces(self) -> List[Namespace]:
        """Get namespaces via gateway"""
        self.mark_used()
        
        try:
            result = await self._grpc_client.list_namespaces(
                cluster_id=str(self.config.cluster_id)
            )
            
            namespaces = []
            for ns in result:
                namespaces.append(Namespace(
                    name=ns.get("name", ""),
                    uid=ns.get("uid"),
                    status=ns.get("status", "Active"),
                    labels=ns.get("labels", {}),
                    created_at=ns.get("created_at")
                ))
            
            return namespaces
        except Exception as e:
            logger.error(
                "Failed to get namespaces via gateway",
                cluster_id=self.config.cluster_id,
                error=str(e)
            )
            return []
    
    async def get_deployments(self, namespace: Optional[str] = None) -> List[Deployment]:
        """Get deployments via gateway. Raises on error."""
        self.mark_used()
        result = await self._grpc_client.list_deployments(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )
        
        deployments = []
        for dep in result:
            deployments.append(Deployment(
                name=dep.get("name", ""),
                namespace=dep.get("namespace", ""),
                uid=dep.get("uid"),
                replicas=dep.get("replicas", 0),
                available_replicas=dep.get("available_replicas", 0),
                labels=dep.get("labels", {}),
                annotations=dep.get("annotations", {}),
                image=dep.get("image"),
                created_at=dep.get("created_at"),
                spec_hash=dep.get("spec_hash", ""),
                containers=dep.get("containers", []),
            ))
        
        return deployments
    
    async def get_pods(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Pod]:
        """Get pods via gateway"""
        self.mark_used()
        
        try:
            result = await self._grpc_client.list_pods(
                cluster_id=str(self.config.cluster_id),
                namespace=namespace or "",
                label_selector=label_selector or ""
            )
            
            pods = []
            for pod in result:
                pods.append(Pod(
                    name=pod.get("name", ""),
                    namespace=pod.get("namespace", ""),
                    uid=pod.get("uid"),
                    status=pod.get("status", "Unknown"),
                    node_name=pod.get("node_name"),
                    labels=pod.get("labels", {}),
                    ip=pod.get("ip"),
                    created_at=pod.get("created_at")
                ))
            
            return pods
        except Exception as e:
            logger.error(
                "Failed to get pods via gateway",
                cluster_id=self.config.cluster_id,
                error=str(e)
            )
            return []
    
    async def get_services(self, namespace: Optional[str] = None) -> List[Service]:
        """Get services via gateway. Raises on error."""
        self.mark_used()
        result = await self._grpc_client.list_services(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )
        
        services = []
        for svc in result:
            services.append(Service(
                name=svc.get("name", ""),
                namespace=svc.get("namespace", ""),
                uid=svc.get("uid"),
                type=svc.get("type", "ClusterIP"),
                cluster_ip=svc.get("cluster_ip"),
                ports=svc.get("ports", []),
                labels=svc.get("labels", {}),
                selector=svc.get("selector", {}),
                created_at=svc.get("created_at")
            ))
        
        return services
    
    async def get_configmaps(self, namespace: Optional[str] = None) -> List[ConfigMap]:
        """Get configmaps via gateway. Raises on error."""
        self.mark_used()
        result = await self._grpc_client.list_configmaps(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )
        return [ConfigMap(
            name=cm.get("name", ""),
            namespace=cm.get("namespace", ""),
            uid=cm.get("uid"),
            data_hash=cm.get("data_hash", "empty"),
            created_at=cm.get("created_at")
        ) for cm in result]

    async def get_secrets(self, namespace: Optional[str] = None) -> List[Secret]:
        """Get secrets via gateway. Raises on error."""
        self.mark_used()
        result = await self._grpc_client.list_secrets(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )
        return [Secret(
            name=sec.get("name", ""),
            namespace=sec.get("namespace", ""),
            uid=sec.get("uid"),
            data_hash=sec.get("data_hash", "empty"),
            type=sec.get("type", "Opaque"),
            created_at=sec.get("created_at")
        ) for sec in result]

    async def get_statefulsets(self, namespace: Optional[str] = None) -> List[StatefulSet]:
        """Get statefulsets via gateway. Raises on error."""
        self.mark_used()
        result = await self._grpc_client.list_statefulsets(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )

        statefulsets = []
        for sts in result:
            statefulsets.append(StatefulSet(
                name=sts.get("name", ""),
                namespace=sts.get("namespace", ""),
                uid=sts.get("uid"),
                replicas=sts.get("replicas", 0),
                ready_replicas=sts.get("ready_replicas", 0),
                labels=sts.get("labels", {}),
                annotations=sts.get("annotations", {}),
                image=sts.get("image"),
                created_at=sts.get("created_at"),
                spec_hash=sts.get("spec_hash", ""),
                containers=sts.get("containers", []),
            ))

        return statefulsets

    async def get_network_policies(self, namespace: Optional[str] = None) -> List:
        """Get network policies via gateway. Raises on error."""
        self.mark_used()
        return await self._grpc_client.list_network_policies(
            cluster_id=str(self.config.cluster_id), namespace=namespace or ""
        )

    async def get_ingresses(self, namespace: Optional[str] = None) -> List:
        """Get ingresses via gateway. Raises on error."""
        self.mark_used()
        return await self._grpc_client.list_ingresses(
            cluster_id=str(self.config.cluster_id), namespace=namespace or ""
        )

    async def get_routes(self, namespace: Optional[str] = None) -> List:
        """Get OpenShift routes via gateway. Raises on error."""
        self.mark_used()
        return await self._grpc_client.list_routes(
            cluster_id=str(self.config.cluster_id), namespace=namespace or ""
        )

    async def get_labels(self, namespace: Optional[str] = None) -> List[str]:
        """Get labels via gateway"""
        self.mark_used()
        
        try:
            result = await self._grpc_client.get_labels(
                cluster_id=str(self.config.cluster_id),
                namespace=namespace or ""
            )
            
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(
                "Failed to get labels via gateway",
                cluster_id=self.config.cluster_id,
                error=str(e)
            )
            return []
