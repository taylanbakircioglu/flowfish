"""
Cluster Manager gRPC Client
Backend uses this client to get cluster resources via cluster-manager service
"""

import grpc
import json
import structlog
from typing import List, Dict, Any, Optional
import asyncio

from config import settings

# Import generated proto files
try:
    from proto import cluster_manager_pb2
    from proto import cluster_manager_pb2_grpc
except ImportError:
    cluster_manager_pb2 = None
    cluster_manager_pb2_grpc = None

logger = structlog.get_logger()


class ClusterManagerClient:
    """
    gRPC client for Cluster Manager service.
    Provides access to cluster-wide resources via cluster-manager service.
    
    Note: grpc.aio channels are bound to specific event loops.
    We need to recreate the channel if the event loop changes.
    """
    
    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint or getattr(settings, 'CLUSTER_MANAGER_GRPC', 'cluster-manager:5001')
        self._channel = None
        self._stub = None
        self._loop = None  # Track which event loop the channel belongs to
    
    async def _ensure_connected(self):
        """Ensure gRPC channel is connected and belongs to current event loop"""
        current_loop = asyncio.get_running_loop()
        
        # Recreate channel if event loop changed or channel doesn't exist
        if self._channel is None or self._loop != current_loop:
            # Close old channel if exists
            if self._channel is not None:
                try:
                    await self._channel.close()
                except Exception:
                    pass  # Ignore errors when closing old channel
            
            self._channel = grpc.aio.insecure_channel(self.endpoint)
            self._stub = cluster_manager_pb2_grpc.ClusterManagerServiceStub(self._channel)
            self._loop = current_loop
            logger.info("Connected to cluster-manager", endpoint=self.endpoint)
    
    async def close(self):
        """Close gRPC channel"""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
    
    async def get_cluster_info(self, cluster_id: str = "") -> Dict[str, Any]:
        """Get basic cluster information"""
        if cluster_manager_pb2 is None:
            logger.warning("cluster_manager proto not available, returning mock data")
            return self._mock_cluster_info()
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.GetClusterInfoRequest(cluster_id=cluster_id)
            response = await self._stub.GetClusterInfo(request, timeout=30)
            
            return {
                "k8s_version": response.k8s_version,
                "total_nodes": response.total_nodes,
                "total_pods": response.total_pods,
                "total_namespaces": response.total_namespaces,
                "platform": response.platform,
                "error": response.error if response.error else None
            }
        except grpc.aio.AioRpcError as e:
            logger.error("GetClusterInfo gRPC error", code=e.code(), details=e.details())
            return {"error": f"gRPC error: {e.details()}"}
        except Exception as e:
            logger.error("GetClusterInfo failed", error=str(e))
            return {"error": str(e)}
    
    async def list_namespaces(self, cluster_id: str = "") -> List[Dict[str, Any]]:
        """List all namespaces"""
        if cluster_manager_pb2 is None:
            logger.warning("cluster_manager proto not available, returning mock data")
            return self._mock_namespaces()
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.ListNamespacesRequest(cluster_id=cluster_id)
            response = await self._stub.ListNamespaces(request, timeout=30)
            
            if response.error:
                logger.error("ListNamespaces error", error=response.error)
                return []
            
            return [
                {
                    "name": ns.name,
                    "uid": ns.uid,
                    "status": ns.status,
                    "labels": dict(ns.labels),
                    "created_at": ns.created_at
                }
                for ns in response.namespaces
            ]
        except grpc.aio.AioRpcError as e:
            logger.error("ListNamespaces gRPC error", code=e.code(), details=e.details())
            return []
        except Exception as e:
            logger.error("ListNamespaces failed", error=str(e))
            return []
    
    async def list_deployments(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List deployments. Raises on error so callers can detect fetch failures."""
        if cluster_manager_pb2 is None:
            return self._mock_deployments()
        
        await self._ensure_connected()
        request = cluster_manager_pb2.ListDeploymentsRequest(
            cluster_id=cluster_id,
            namespace=namespace or ""
        )
        response = await self._stub.ListDeployments(request, timeout=30)
        
        if response.error:
            raise RuntimeError(f"ListDeployments server error: {response.error}")
        
        result = []
        for dep in response.deployments:
            d = {
                "name": dep.name,
                "namespace": dep.namespace,
                "uid": dep.uid,
                "replicas": dep.replicas,
                "available_replicas": dep.available_replicas,
                "labels": dict(dep.labels),
                "annotations": dict(dep.annotations) if dep.annotations else {},
                "image": dep.image,
                "created_at": dep.created_at,
                "spec_hash": dep.spec_hash or "",
            }
            try:
                d["containers"] = json.loads(dep.containers_json) if dep.containers_json else []
            except Exception:
                d["containers"] = []
            result.append(d)
        return result
    
    async def list_pods(self, cluster_id: str = "", namespace: str = None, 
                       label_selector: str = None) -> List[Dict[str, Any]]:
        """List pods"""
        if cluster_manager_pb2 is None:
            return []
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.ListPodsRequest(
                cluster_id=cluster_id,
                namespace=namespace or "",
                label_selector=label_selector or ""
            )
            response = await self._stub.ListPods(request, timeout=30)
            
            if response.error:
                return []
            
            return [
                {
                    "name": pod.name,
                    "namespace": pod.namespace,
                    "uid": pod.uid,
                    "status": pod.status,
                    "node_name": pod.node_name,
                    "labels": dict(pod.labels),
                    "ip": pod.ip,
                    "created_at": pod.created_at
                }
                for pod in response.pods
            ]
        except Exception as e:
            logger.error("ListPods failed", error=str(e))
            return []
    
    async def list_services(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List services. Raises on error so callers can detect fetch failures."""
        if cluster_manager_pb2 is None:
            return []
        
        await self._ensure_connected()
        request = cluster_manager_pb2.ListServicesRequest(
            cluster_id=cluster_id,
            namespace=namespace or ""
        )
        response = await self._stub.ListServices(request, timeout=30)
        
        if response.error:
            raise RuntimeError(f"ListServices server error: {response.error}")
        
        return [
            {
                "name": svc.name,
                "namespace": svc.namespace,
                "uid": svc.uid,
                "type": svc.type,
                "cluster_ip": svc.cluster_ip,
                "ports": [
                    {"port": p.port, "protocol": p.protocol, "target_port": p.target_port,
                     "name": p.name or "", "app_protocol": getattr(p, 'app_protocol', '') or ""}
                    for p in svc.ports
                ],
                "labels": dict(svc.labels),
                "selector": dict(svc.selector),
                "created_at": svc.created_at
            }
            for svc in response.services
        ]
    
    async def list_network_policies(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List network policies with spec hash. Raises on error."""
        if cluster_manager_pb2 is None:
            return []
        await self._ensure_connected()
        request = cluster_manager_pb2.ListNetworkPoliciesRequest(cluster_id=cluster_id, namespace=namespace or "")
        response = await self._stub.ListNetworkPolicies(request, timeout=30)
        if response.error:
            raise RuntimeError(f"ListNetworkPolicies server error: {response.error}")
        return [{"name": np.name, "namespace": np.namespace, "uid": np.uid,
                 "spec_hash": np.spec_hash, "created_at": np.created_at}
                for np in response.network_policies]

    async def list_ingresses(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List ingresses with spec hash. Raises on error."""
        if cluster_manager_pb2 is None:
            return []
        await self._ensure_connected()
        request = cluster_manager_pb2.ListIngressesRequest(cluster_id=cluster_id, namespace=namespace or "")
        response = await self._stub.ListIngresses(request, timeout=30)
        if response.error:
            raise RuntimeError(f"ListIngresses server error: {response.error}")
        return [{"name": ing.name, "namespace": ing.namespace, "uid": ing.uid,
                 "spec_hash": ing.spec_hash, "hosts": list(ing.hosts), "created_at": ing.created_at}
                for ing in response.ingresses]

    async def list_routes(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List OpenShift routes with spec hash. Raises on error."""
        if cluster_manager_pb2 is None:
            return []
        await self._ensure_connected()
        request = cluster_manager_pb2.ListRoutesRequest(cluster_id=cluster_id, namespace=namespace or "")
        response = await self._stub.ListRoutes(request, timeout=30)
        if response.error:
            raise RuntimeError(f"ListRoutes server error: {response.error}")
        return [{"name": rt.name, "namespace": rt.namespace, "uid": rt.uid,
                 "spec_hash": rt.spec_hash, "host": rt.host, "created_at": rt.created_at}
                for rt in response.routes]

    async def list_configmaps(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List configmaps with data hash. Raises on error."""
        if cluster_manager_pb2 is None:
            return []

        await self._ensure_connected()
        request = cluster_manager_pb2.ListConfigMapsRequest(
            cluster_id=cluster_id,
            namespace=namespace or ""
        )
        response = await self._stub.ListConfigMaps(request, timeout=30)

        if response.error:
            raise RuntimeError(f"ListConfigMaps server error: {response.error}")

        return [
            {
                "name": cm.name,
                "namespace": cm.namespace,
                "uid": cm.uid,
                "data_hash": cm.data_hash,
                "created_at": cm.created_at
            }
            for cm in response.configmaps
        ]

    async def list_secrets(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List secrets with data hash. Raises on error."""
        if cluster_manager_pb2 is None:
            return []

        await self._ensure_connected()
        request = cluster_manager_pb2.ListSecretsRequest(
            cluster_id=cluster_id,
            namespace=namespace or ""
        )
        response = await self._stub.ListSecrets(request, timeout=30)

        if response.error:
            raise RuntimeError(f"ListSecrets server error: {response.error}")

        return [
            {
                "name": sec.name,
                "namespace": sec.namespace,
                "uid": sec.uid,
                "data_hash": sec.data_hash,
                "type": sec.type,
                "created_at": sec.created_at
            }
            for sec in response.secrets
        ]

    async def list_statefulsets(self, cluster_id: str = "", namespace: str = None) -> List[Dict[str, Any]]:
        """List statefulsets. Raises on error."""
        if cluster_manager_pb2 is None:
            return []

        await self._ensure_connected()
        request = cluster_manager_pb2.ListStatefulSetsRequest(
            cluster_id=cluster_id,
            namespace=namespace or ""
        )
        response = await self._stub.ListStatefulSets(request, timeout=30)

        if response.error:
            raise RuntimeError(f"ListStatefulSets server error: {response.error}")

        result = []
        for sts in response.statefulsets:
            d = {
                "name": sts.name,
                "namespace": sts.namespace,
                "uid": sts.uid,
                "replicas": sts.replicas,
                "ready_replicas": sts.ready_replicas,
                "labels": dict(sts.labels),
                "annotations": dict(sts.annotations) if sts.annotations else {},
                "image": sts.image,
                "created_at": sts.created_at,
                "spec_hash": sts.spec_hash or "",
            }
            try:
                d["containers"] = json.loads(sts.containers_json) if sts.containers_json else []
            except Exception:
                d["containers"] = []
            result.append(d)
        return result

    async def get_labels(self, cluster_id: str = "", resource_type: str = "pods", 
                        namespace: str = None) -> List[str]:
        """Get unique labels from resources"""
        if cluster_manager_pb2 is None:
            return ["app=frontend", "app=backend", "tier=web", "tier=database"]
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.GetLabelsRequest(
                cluster_id=cluster_id,
                resource_type=resource_type,
                namespace=namespace or ""
            )
            response = await self._stub.GetLabels(request, timeout=30)
            
            if response.error:
                return []
            
            return list(response.labels)
        except Exception as e:
            logger.error("GetLabels failed", error=str(e))
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Check cluster-manager health"""
        if cluster_manager_pb2 is None:
            return {"healthy": False, "message": "Proto not available"}
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.HealthCheckRequest()
            response = await self._stub.HealthCheck(request, timeout=10)
            
            return {
                "healthy": response.healthy,
                "message": response.message,
                "kubernetes_status": response.kubernetes_status
            }
        except Exception as e:
            return {"healthy": False, "message": str(e)}
    
    async def check_gadget_health(self, cluster_id: str = "", gadget_namespace: str = "") -> Dict[str, Any]:
        """
        Check Inspector Gadget DaemonSet health via cluster-manager.
        
        Args:
            cluster_id: Cluster identifier (for multi-cluster support)
            gadget_namespace: Namespace where Gadget is deployed
            
        Returns:
            {
                "health_status": "healthy" | "degraded" | "unhealthy" | "unknown",
                "version": str | None,
                "error": str | None,
                "pods_ready": int,
                "pods_total": int,
                "details": {...}
            }
        """
        if cluster_manager_pb2 is None:
            logger.warning("cluster_manager proto not available for gadget health check")
            return {
                "health_status": "unknown",
                "version": None,
                "error": "Proto not available",
                "pods_ready": 0,
                "pods_total": 0,
                "details": {"issues": ["Proto not available"]}
            }
        
        try:
            await self._ensure_connected()
            request = cluster_manager_pb2.CheckGadgetHealthRequest(
                cluster_id=cluster_id,
                gadget_namespace=gadget_namespace
            )
            response = await self._stub.CheckGadgetHealth(request, timeout=15)
            
            return {
                "health_status": response.health_status,
                "version": response.version if response.version else None,
                "error": response.error if response.error else None,
                "pods_ready": response.pods_ready,
                "pods_total": response.pods_total,
                "details": {
                    "ebpf_capable": response.ebpf_capable,
                    "total_restarts": response.total_restarts,
                    "issues": list(response.issues) if response.issues else []
                }
            }
        except grpc.aio.AioRpcError as e:
            logger.error("CheckGadgetHealth gRPC error", code=e.code(), details=e.details())
            return {
                "health_status": "unknown",
                "version": None,
                "error": f"gRPC error: {e.details()}",
                "pods_ready": 0,
                "pods_total": 0,
                "details": {"issues": [f"gRPC error: {e.details()}"]}
            }
        except Exception as e:
            logger.error("CheckGadgetHealth failed", error=str(e))
            return {
                "health_status": "unknown",
                "version": None,
                "error": str(e),
                "pods_ready": 0,
                "pods_total": 0,
                "details": {"issues": [str(e)]}
            }
    
    # Mock data for fallback when cluster-manager is not available
    def _mock_cluster_info(self):
        return {
            "k8s_version": "v1.28.0",
            "total_nodes": 3,
            "total_pods": 25,
            "total_namespaces": 8,
            "platform": "linux/amd64",
            "error": None
        }
    
    def _mock_namespaces(self):
        return [
            {"name": "default", "uid": "ns-1", "status": "Active", "labels": {}, "created_at": ""},
            {"name": "kube-system", "uid": "ns-2", "status": "Active", "labels": {}, "created_at": ""},
            {"name": "flowfish", "uid": "ns-3", "status": "Active", "labels": {}, "created_at": ""}
        ]
    
    def _mock_deployments(self):
        return [
            {"name": "backend", "namespace": "flowfish", "replicas": 1, "available_replicas": 1, "labels": {"app": "backend"}},
            {"name": "frontend", "namespace": "flowfish", "replicas": 1, "available_replicas": 1, "labels": {"app": "frontend"}}
        ]


# Singleton instance
cluster_manager_client = ClusterManagerClient()

