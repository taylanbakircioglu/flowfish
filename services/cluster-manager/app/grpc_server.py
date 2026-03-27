"""
Cluster Manager gRPC Server

Gateway Pattern Architecture:
- This service acts as the SINGLE entry point for ALL Kubernetes API access
- Supports both in-cluster (default) and remote cluster connections
- Remote cluster credentials are fetched from PostgreSQL and decrypted
- Client instances are cached with TTL for performance
- Temp files (CA certs) written to /tmp emptyDir volume

Multi-Cluster Support:
- cluster_id="default" or "0" or empty -> in-cluster client
- cluster_id=<numeric_id> -> remote cluster (fetch credentials from DB)
"""

import grpc
import json
from concurrent import futures
import structlog
import asyncio
import os
import base64
from typing import Optional, Dict, Any

from app.config import settings
from app.kubernetes_client import kubernetes_client, KubernetesClient, KubernetesClientFactory
from app.database import db_manager

# Import generated proto files (will be generated during build)
try:
    from proto import cluster_manager_pb2
    from proto import cluster_manager_pb2_grpc
except ImportError:
    # Fallback for development
    import sys
    sys.path.insert(0, '/app')
    from proto import cluster_manager_pb2
    from proto import cluster_manager_pb2_grpc

# Encryption support - same as backend
try:
    from cryptography.fernet import Fernet, InvalidToken
    _ENCRYPTION_KEY = os.environ.get("FLOWFISH_ENCRYPTION_KEY")
    _cipher = Fernet(_ENCRYPTION_KEY.encode()) if _ENCRYPTION_KEY else None
except Exception:
    _cipher = None

logger = structlog.get_logger()


def _decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted string.
    Falls back to returning the original value if decryption fails.
    """
    if not ciphertext:
        return ""
    
    # Check if value looks like it could be Fernet encrypted
    if not ciphertext.startswith('gAAAAA'):
        return ciphertext
    
    if not _cipher:
        logger.warning("Encryption not configured, returning value as-is")
        return ciphertext
    
    try:
        decrypted = _cipher.decrypt(ciphertext.encode('utf-8'))
        return decrypted.decode('utf-8')
    except (InvalidToken, Exception) as e:
        logger.warning("Decryption failed, returning value as-is", error=str(e))
        return ciphertext


class ClusterManagerServicer(cluster_manager_pb2_grpc.ClusterManagerServiceServicer):
    """
    gRPC Servicer for Cluster Manager
    
    Gateway Pattern:
    - Default: Uses in-cluster ServiceAccount with ClusterRole
    - Remote: Fetches credentials from PostgreSQL and creates appropriate client
    
    Multi-Cluster Support:
    - cluster_id="default" or "0" or empty -> in-cluster client
    - cluster_id=<numeric_id> -> remote cluster (credentials from DB)
    """
    
    def __init__(self):
        # Default in-cluster client (backward compatible)
        self.k8s_client = kubernetes_client
        self._db = db_manager
        logger.info("ClusterManagerServicer initialized with gateway pattern support")
    
    async def _get_k8s_client(self, cluster_id: str) -> KubernetesClient:
        """
        Get appropriate Kubernetes client based on cluster_id.
        
        Gateway Pattern Implementation:
        - Default/empty/"0" cluster_id -> in-cluster client
        - Numeric cluster_id -> fetch credentials from DB and create remote client
        
        For remote clusters, errors are raised instead of silently falling back
        to the in-cluster client, so callers can report meaningful errors.
        
        Args:
            cluster_id: Cluster identifier from gRPC request
            
        Returns:
            KubernetesClient instance (from cache or newly created)
            
        Raises:
            ValueError: If cluster_id is invalid, cluster not found, or credentials missing
            Exception: If client creation fails for any reason
        """
        if not cluster_id or cluster_id == "default" or cluster_id == "0":
            logger.debug("Using in-cluster client", cluster_id=cluster_id)
            return self.k8s_client
        
        try:
            cluster_id_int = int(cluster_id)
        except ValueError:
            raise ValueError(f"Invalid cluster_id format: {cluster_id}")
        
        cluster = await self._db.get_cluster_credentials(cluster_id_int)
        
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found in database or not active")
        
        connection_type = cluster.get("connection_type", "in-cluster")
        
        if connection_type == "in-cluster":
            logger.debug("Cluster configured as in-cluster", cluster_id=cluster_id)
            return self.k8s_client
        
        token = _decrypt_value(cluster.get("token_encrypted") or "")
        ca_cert = _decrypt_value(cluster.get("ca_cert_encrypted") or "")
        kubeconfig = _decrypt_value(cluster.get("kubeconfig_encrypted") or "")
        
        api_server_url = cluster.get("api_server_url")
        skip_tls_verify = cluster.get("skip_tls_verify") or False
        
        logger.info("Creating remote cluster client",
                    cluster_id=cluster_id,
                    cluster_name=cluster.get("name"),
                    connection_type=connection_type,
                    api_server_url=api_server_url,
                    has_token=bool(token),
                    has_ca_cert=bool(ca_cert),
                    skip_tls_verify=skip_tls_verify)
        
        try:
            if connection_type == "token":
                if not api_server_url or not token:
                    raise ValueError(
                        f"Cluster {cluster_id}: missing api_server_url or token for token connection"
                    )
                
                return KubernetesClientFactory.get_client(
                    cluster_id=cluster_id,
                    connection_type="token",
                    api_server_url=api_server_url,
                    token=token,
                    ca_cert=base64.b64encode(ca_cert.encode()).decode() if ca_cert else None,
                    skip_tls_verify=skip_tls_verify
                )
            
            elif connection_type == "kubeconfig":
                if not kubeconfig:
                    raise ValueError(
                        f"Cluster {cluster_id}: missing kubeconfig content for kubeconfig connection"
                    )
                
                return KubernetesClientFactory.get_client(
                    cluster_id=cluster_id,
                    connection_type="kubeconfig",
                    kubeconfig_content=base64.b64encode(kubeconfig.encode()).decode()
                )
            
            else:
                raise ValueError(
                    f"Cluster {cluster_id}: unsupported connection type '{connection_type}'"
                )
        except Exception as e:
            KubernetesClientFactory.invalidate(cluster_id)
            raise
    
    async def GetClusterInfo(self, request, context):
        """Get basic cluster information"""
        cluster_id = request.cluster_id or "default"
        logger.info("GetClusterInfo called", cluster_id=cluster_id)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            info = await k8s_client.get_cluster_info()
            
            return cluster_manager_pb2.ClusterInfoResponse(
                k8s_version=info.get("k8s_version") or "",
                total_nodes=info.get("total_nodes", 0),
                total_pods=info.get("total_pods", 0),
                total_namespaces=info.get("total_namespaces", 0),
                platform=info.get("platform") or "",
                error=info.get("error") or ""
            )
        except Exception as e:
            logger.error("GetClusterInfo failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ClusterInfoResponse(error=str(e))
    
    async def ListNamespaces(self, request, context):
        """List all namespaces"""
        cluster_id = request.cluster_id or "default"
        logger.info("ListNamespaces called", cluster_id=cluster_id)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            namespaces = await k8s_client.list_namespaces()
            
            ns_infos = [
                cluster_manager_pb2.NamespaceInfo(
                    name=ns["name"],
                    uid=ns.get("uid") or "",
                    status=ns.get("status") or "",
                    labels=ns.get("labels") or {},
                    created_at=ns.get("created_at") or ""
                )
                for ns in namespaces
            ]
            
            return cluster_manager_pb2.ListNamespacesResponse(
                namespaces=ns_infos,
                count=len(ns_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListNamespaces failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListNamespacesResponse(error=str(e))
    
    async def ListDeployments(self, request, context):
        """List deployments"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        logger.info("ListDeployments called", cluster_id=cluster_id, namespace=namespace)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            deployments = await k8s_client.list_deployments(namespace)
            
            dep_infos = [
                cluster_manager_pb2.DeploymentInfo(
                    name=dep["name"],
                    namespace=dep["namespace"],
                    uid=dep.get("uid") or "",
                    replicas=dep.get("replicas") or 0,
                    available_replicas=dep.get("available_replicas") or 0,
                    labels=dep.get("labels") or {},
                    annotations=self._filter_annotations(dep.get("annotations")),
                    image=dep.get("image") or "",
                    created_at=dep.get("created_at") or "",
                    spec_hash=dep.get("spec_hash") or "",
                    containers_json=json.dumps(dep.get("containers") or [], default=str)
                )
                for dep in deployments
            ]
            
            return cluster_manager_pb2.ListDeploymentsResponse(
                deployments=dep_infos,
                count=len(dep_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListDeployments failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListDeploymentsResponse(error=str(e))
    
    _NOISE_ANNOTATION_PREFIXES = (
        'kubectl.kubernetes.io/',
        'kubernetes.io/',
        'openshift.io/',
        'k8s.v1.cni.cncf.io/',
        'k8s.ovn.org/',
        'seccomp.security.alpha.kubernetes.io/',
    )

    @classmethod
    def _filter_annotations(cls, raw_annotations: dict) -> dict:
        """Filter out internal/large annotations, keep user-defined ones"""
        if not raw_annotations:
            return {}
        return {
            k: v for k, v in raw_annotations.items()
            if not any(k.startswith(p) for p in cls._NOISE_ANNOTATION_PREFIXES)
            and len(str(v)) < 500
        }

    async def ListPods(self, request, context):
        """List pods"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        label_selector = request.label_selector if request.label_selector else None
        logger.info("ListPods called", cluster_id=cluster_id, namespace=namespace, label_selector=label_selector)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            pods = await k8s_client.list_pods(namespace, label_selector)
            
            pod_infos = [
                cluster_manager_pb2.PodInfo(
                    name=pod["name"],
                    namespace=pod["namespace"],
                    uid=pod.get("uid") or "",
                    status=pod.get("status") or "",
                    node_name=pod.get("node_name") or "",
                    labels=pod.get("labels") or {},
                    annotations=self._filter_annotations(pod.get("annotations")),
                    ip=pod.get("ip") or "",
                    created_at=pod.get("created_at") or ""
                )
                for pod in pods
            ]
            
            return cluster_manager_pb2.ListPodsResponse(
                pods=pod_infos,
                count=len(pod_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListPods failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListPodsResponse(error=str(e))
    
    async def ListServices(self, request, context):
        """List services"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        logger.info("ListServices called", cluster_id=cluster_id, namespace=namespace)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            services = await k8s_client.list_services(namespace)
            
            svc_infos = [
                cluster_manager_pb2.ServiceInfo(
                    name=svc["name"],
                    namespace=svc["namespace"],
                    uid=svc.get("uid") or "",
                    type=svc.get("type") or "",
                    cluster_ip=svc.get("cluster_ip") or "",
                    ports=[
                        cluster_manager_pb2.ServicePort(
                            port=p["port"],
                            protocol=p["protocol"],
                            target_port=p["target_port"],
                            name=p.get("name") or "",
                            app_protocol=p.get("app_protocol") or ""
                        )
                        for p in svc.get("ports", [])
                    ],
                    labels=svc.get("labels") or {},
                    selector=svc.get("selector") or {},
                    created_at=svc.get("created_at") or ""
                )
                for svc in services
            ]
            
            return cluster_manager_pb2.ListServicesResponse(
                services=svc_infos,
                count=len(svc_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListServices failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListServicesResponse(error=str(e))
    
    async def ListStatefulSets(self, request, context):
        """List statefulsets"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        logger.info("ListStatefulSets called", cluster_id=cluster_id, namespace=namespace)

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            statefulsets = await k8s_client.list_statefulsets(namespace)

            sts_infos = [
                cluster_manager_pb2.StatefulSetInfo(
                    name=sts["name"],
                    namespace=sts["namespace"],
                    uid=sts.get("uid") or "",
                    replicas=sts.get("replicas") or 0,
                    ready_replicas=sts.get("ready_replicas") or 0,
                    labels=sts.get("labels") or {},
                    annotations=self._filter_annotations(sts.get("annotations")),
                    image=sts.get("image") or "",
                    created_at=sts.get("created_at") or "",
                    spec_hash=sts.get("spec_hash") or "",
                    containers_json=json.dumps(sts.get("containers") or [], default=str)
                )
                for sts in statefulsets
            ]

            return cluster_manager_pb2.ListStatefulSetsResponse(
                statefulsets=sts_infos,
                count=len(sts_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListStatefulSets failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListStatefulSetsResponse(error=str(e))

    async def ListConfigMaps(self, request, context):
        """List configmaps with data hash"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        logger.info("ListConfigMaps called", cluster_id=cluster_id, namespace=namespace)

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            configmaps = await k8s_client.list_configmaps(namespace)

            cm_infos = [
                cluster_manager_pb2.ConfigMapInfo(
                    name=cm["name"],
                    namespace=cm["namespace"],
                    uid=cm.get("uid") or "",
                    data_hash=cm.get("data_hash") or "empty",
                    created_at=cm.get("created_at") or ""
                )
                for cm in configmaps
            ]

            return cluster_manager_pb2.ListConfigMapsResponse(
                configmaps=cm_infos,
                count=len(cm_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListConfigMaps failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListConfigMapsResponse(error=str(e))

    async def ListSecrets(self, request, context):
        """List secrets with data hash"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None
        logger.info("ListSecrets called", cluster_id=cluster_id, namespace=namespace)

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            secrets = await k8s_client.list_secrets(namespace)

            sec_infos = [
                cluster_manager_pb2.SecretInfo(
                    name=sec["name"],
                    namespace=sec["namespace"],
                    uid=sec.get("uid") or "",
                    data_hash=sec.get("data_hash") or "empty",
                    type=sec.get("type") or "Opaque",
                    created_at=sec.get("created_at") or ""
                )
                for sec in secrets
            ]

            return cluster_manager_pb2.ListSecretsResponse(
                secrets=sec_infos,
                count=len(sec_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListSecrets failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListSecretsResponse(error=str(e))

    async def ListNetworkPolicies(self, request, context):
        """List network policies with spec hash"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            netpols = await k8s_client.list_network_policies(namespace)
            infos = [
                cluster_manager_pb2.NetworkPolicyInfo(
                    name=np["name"], namespace=np["namespace"],
                    uid=np.get("uid") or "", spec_hash=np.get("spec_hash") or "",
                    created_at=np.get("created_at") or ""
                ) for np in netpols
            ]
            return cluster_manager_pb2.ListNetworkPoliciesResponse(network_policies=infos, count=len(infos), error="")
        except Exception as e:
            logger.error("ListNetworkPolicies failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListNetworkPoliciesResponse(error=str(e))

    async def ListIngresses(self, request, context):
        """List ingresses with spec hash"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            ingresses = await k8s_client.list_ingresses(namespace)
            infos = [
                cluster_manager_pb2.IngressInfo(
                    name=ing["name"], namespace=ing["namespace"],
                    uid=ing.get("uid") or "", spec_hash=ing.get("spec_hash") or "",
                    hosts=ing.get("hosts") or [],
                    created_at=ing.get("created_at") or ""
                ) for ing in ingresses
            ]
            return cluster_manager_pb2.ListIngressesResponse(ingresses=infos, count=len(infos), error="")
        except Exception as e:
            logger.error("ListIngresses failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListIngressesResponse(error=str(e))

    async def ListRoutes(self, request, context):
        """List OpenShift routes with spec hash"""
        cluster_id = request.cluster_id or "default"
        namespace = request.namespace if request.namespace else None

        try:
            k8s_client = await self._get_k8s_client(cluster_id)
            routes = await k8s_client.list_routes(namespace)
            infos = [
                cluster_manager_pb2.RouteInfo(
                    name=rt["name"], namespace=rt["namespace"],
                    uid=rt.get("uid") or "", spec_hash=rt.get("spec_hash") or "",
                    host=rt.get("host") or "",
                    created_at=rt.get("created_at") or ""
                ) for rt in routes
            ]
            return cluster_manager_pb2.ListRoutesResponse(routes=infos, count=len(infos), error="")
        except Exception as e:
            logger.error("ListRoutes failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListRoutesResponse(error=str(e))

    async def ListNodes(self, request, context):
        """List cluster nodes with their IPs"""
        cluster_id = request.cluster_id or "default"
        logger.info("ListNodes called", cluster_id=cluster_id)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            nodes = await k8s_client.list_nodes()
            
            node_infos = [
                cluster_manager_pb2.NodeInfo(
                    name=node["name"],
                    uid=node.get("uid") or "",
                    internal_ip=node.get("internal_ip") or "",
                    external_ip=node.get("external_ip") or "",
                    status=node.get("status") or "",
                    labels=node.get("labels") or {},
                    kubelet_version=node.get("kubelet_version") or "",
                    os_image=node.get("os_image") or "",
                    container_runtime=node.get("container_runtime") or "",
                    architecture=node.get("architecture") or "",
                    created_at=node.get("created_at") or ""
                )
                for node in nodes
            ]
            
            return cluster_manager_pb2.ListNodesResponse(
                nodes=node_infos,
                count=len(node_infos),
                error=""
            )
        except Exception as e:
            logger.error("ListNodes failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.ListNodesResponse(error=str(e))
    
    async def GetLabels(self, request, context):
        """Get unique labels from resources"""
        cluster_id = request.cluster_id or "default"
        resource_type = request.resource_type or "pods"
        namespace = request.namespace if request.namespace else None
        logger.info("GetLabels called", cluster_id=cluster_id, resource_type=resource_type, namespace=namespace)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            labels = await k8s_client.get_labels(resource_type, namespace)
            
            return cluster_manager_pb2.GetLabelsResponse(
                labels=labels,
                count=len(labels),
                error=""
            )
        except Exception as e:
            logger.error("GetLabels failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.GetLabelsResponse(error=str(e))
    
    async def HealthCheck(self, request, context):
        """Health check - uses default in-cluster client"""
        # Note: HealthCheckRequest proto doesn't have cluster_id field
        # This endpoint is for checking cluster-manager service health, not remote clusters
        try:
            # Use default in-cluster client for health check
            info = await self.k8s_client.get_cluster_info()
            healthy = info.get("error") is None
            
            return cluster_manager_pb2.HealthCheckResponse(
                healthy=healthy,
                message="OK" if healthy else info.get("error", "Unknown error"),
                kubernetes_status="connected" if healthy else "disconnected"
            )
        except Exception as e:
            logger.error("HealthCheck failed", error=str(e))
            return cluster_manager_pb2.HealthCheckResponse(
                healthy=False,
                message=str(e),
                kubernetes_status="disconnected"
            )
    
    async def CheckGadgetHealth(self, request, context):
        """Check Inspector Gadget DaemonSet health"""
        cluster_id = request.cluster_id or "default"
        gadget_namespace = request.gadget_namespace
        
        if not gadget_namespace:
            logger.error("gadget_namespace is required but not provided")
            return cluster_manager_pb2.GadgetHealthResponse(
                health_status="unknown",
                error="gadget_namespace is required",
                pods_ready=0,
                pods_total=0
            )
        logger.info("CheckGadgetHealth called", cluster_id=cluster_id, gadget_namespace=gadget_namespace)
        
        try:
            # Get appropriate client for the cluster
            k8s_client = await self._get_k8s_client(cluster_id)
            health = await k8s_client.check_gadget_health(gadget_namespace)
            
            return cluster_manager_pb2.GadgetHealthResponse(
                health_status=health.get("health_status", "unknown"),
                version=health.get("version") or "",
                error=health.get("error") or "",
                pods_ready=health.get("pods_ready", 0),
                pods_total=health.get("pods_total", 0),
                ebpf_capable=health.get("details", {}).get("ebpf_capable", False),
                total_restarts=health.get("details", {}).get("total_restarts", 0),
                issues=health.get("details", {}).get("issues", [])
            )
        except Exception as e:
            logger.error("CheckGadgetHealth failed", cluster_id=cluster_id, error=str(e))
            return cluster_manager_pb2.GadgetHealthResponse(
                health_status="unknown",
                error=str(e),
                pods_ready=0,
                pods_total=0
            )


async def serve():
    """Start gRPC server"""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )
    
    cluster_manager_pb2_grpc.add_ClusterManagerServiceServicer_to_server(
        ClusterManagerServicer(), server
    )
    
    listen_addr = f"0.0.0.0:{settings.GRPC_PORT}"
    server.add_insecure_port(listen_addr)
    
    logger.info("Starting Cluster Manager gRPC server", address=listen_addr)
    
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Cluster Manager server")
        await server.stop(5)


if __name__ == "__main__":
    asyncio.run(serve())
