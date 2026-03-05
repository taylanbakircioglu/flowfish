"""
Kubernetes Client - Multi-cluster resource discovery
Supports: In-Cluster, Kubeconfig, Token-based connections
"""

import json
import structlog
from typing import List, Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import asyncio
import base64
import tempfile
import os
from datetime import datetime

logger = structlog.get_logger()


class KubernetesClient:
    """
    Kubernetes client supporting multiple connection types:
    
    1. In-Cluster: Uses ServiceAccount mounted in pod (default for cluster-manager)
    2. Kubeconfig: Uses kubeconfig file/content for external clusters
    3. Token: Uses bearer token + API URL for external clusters
    
    Usage:
        # In-cluster (default)
        client = KubernetesClient()
        
        # External with kubeconfig
        client = KubernetesClient(
            connection_type="kubeconfig",
            kubeconfig_content="base64_encoded_kubeconfig"
        )
        
        # External with token
        client = KubernetesClient(
            connection_type="token",
            api_server_url="https://api.cluster.example.com:6443",
            token="bearer_token",
            skip_tls_verify=True
        )
    """
    
    def __init__(
        self,
        connection_type: str = "in-cluster",
        api_server_url: Optional[str] = None,
        kubeconfig_content: Optional[str] = None,
        token: Optional[str] = None,
        ca_cert: Optional[str] = None,
        skip_tls_verify: bool = False,
        cluster_id: Optional[str] = None
    ):
        """
        Initialize Kubernetes client.
        
        Args:
            connection_type: "in-cluster", "kubeconfig", or "token"
            api_server_url: Kubernetes API server URL (for token auth)
            kubeconfig_content: Base64 encoded kubeconfig content
            token: Bearer token for authentication
            ca_cert: Base64 encoded CA certificate
            skip_tls_verify: Skip TLS verification
            cluster_id: Identifier for logging/debugging
        """
        self.connection_type = connection_type.lower().replace("_", "-")
        self.api_server_url = api_server_url
        self.kubeconfig_content = kubeconfig_content
        self.token = token
        self.ca_cert = ca_cert
        self.skip_tls_verify = skip_tls_verify
        self.cluster_id = cluster_id or "default"
        
        self._initialized = False
        self._core_v1 = None
        self._apps_v1 = None
        self._networking_v1 = None
        self._custom_objects = None
        self._version_api = None
        self._api_client = None
        self._temp_files = []  # Track temp files for cleanup
    
    def _init_client(self):
        """Initialize Kubernetes client based on connection type"""
        if self._initialized:
            return
        
        try:
            if self.connection_type == "in-cluster":
                self._init_in_cluster()
            elif self.connection_type == "kubeconfig":
                self._init_kubeconfig()
            elif self.connection_type == "token":
                self._init_token()
            else:
                # Fallback: try in-cluster, then kubeconfig
                try:
                    self._init_in_cluster()
                except config.ConfigException:
                    self._init_kubeconfig()
            
            self._core_v1 = client.CoreV1Api(self._api_client)
            self._apps_v1 = client.AppsV1Api(self._api_client)
            self._networking_v1 = client.NetworkingV1Api(self._api_client)
            self._custom_objects = client.CustomObjectsApi(self._api_client)
            self._version_api = client.VersionApi(self._api_client)
            self._initialized = True
            
            logger.info("Kubernetes client initialized",
                       connection_type=self.connection_type,
                       cluster_id=self.cluster_id)
                       
        except Exception as e:
            logger.error("Failed to initialize Kubernetes client",
                        connection_type=self.connection_type,
                        cluster_id=self.cluster_id,
                        error=str(e))
            raise
    
    def _init_in_cluster(self):
        """Initialize using in-cluster config (ServiceAccount)"""
        config.load_incluster_config()
        self._api_client = client.ApiClient()
        logger.info("Loaded in-cluster Kubernetes config")
    
    def _init_kubeconfig(self):
        """Initialize using kubeconfig file/content"""
        if self.kubeconfig_content:
            # Decode base64 and write to temp file
            kubeconfig_data = base64.b64decode(self.kubeconfig_content).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.kubeconfig') as f:
                f.write(kubeconfig_data)
                kubeconfig_path = f.name
                self._temp_files.append(kubeconfig_path)
            
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            # Use default kubeconfig location
            config.load_kube_config()
        
        self._api_client = client.ApiClient()
        logger.info("Loaded kubeconfig")
    
    def _init_token(self):
        """Initialize using bearer token"""
        if not self.api_server_url or not self.token:
            raise ValueError("api_server_url and token required for token auth")
        
        configuration = client.Configuration()
        configuration.host = self.api_server_url
        configuration.api_key = {"authorization": f"Bearer {self.token}"}
        
        if self.skip_tls_verify:
            configuration.verify_ssl = False
        elif self.ca_cert:
            # Write CA cert to temp file
            ca_data = base64.b64decode(self.ca_cert).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.crt') as f:
                f.write(ca_data)
                configuration.ssl_ca_cert = f.name
                self._temp_files.append(f.name)
        
        self._api_client = client.ApiClient(configuration)
        logger.info("Initialized with bearer token", api_server=self.api_server_url)
    
    def close(self):
        """Close client and cleanup temp files"""
        if self._api_client:
            self._api_client.close()
        
        for temp_file in self._temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
        self._temp_files = []
        self._initialized = False
    
    # =========================================================================
    # Cluster Info
    # =========================================================================
    
    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get basic cluster information"""
        return await asyncio.to_thread(self._get_cluster_info_sync)
    
    def _get_cluster_info_sync(self) -> Dict[str, Any]:
        self._init_client()
        try:
            # Get version info
            version = self._version_api.get_code()
            
            # Get counts - use limit=1 with remaining_item_count for efficiency
            # Falls back to full list if remaining_item_count not available
            node_count = self._get_resource_count(
                lambda: self._core_v1.list_node(limit=1),
                lambda: self._core_v1.list_node()
            )
            
            # For pods, same approach but for all namespaces
            pod_count = self._get_resource_count(
                lambda: self._core_v1.list_pod_for_all_namespaces(limit=1),
                lambda: self._core_v1.list_pod_for_all_namespaces()
            )
            
            ns_count = self._get_resource_count(
                lambda: self._core_v1.list_namespace(limit=1),
                lambda: self._core_v1.list_namespace()
            )
            
            return {
                "k8s_version": version.git_version,
                "total_nodes": node_count,
                "total_pods": pod_count,
                "total_namespaces": ns_count,
                "platform": version.platform,
                "error": None
            }
        except ApiException as e:
            logger.error("Failed to get cluster info", status=e.status, reason=e.reason)
            return {
                "error": f"API Error: {e.reason}",
                "k8s_version": None,
                "total_nodes": 0,
                "total_pods": 0,
                "total_namespaces": 0
            }
        except Exception as e:
            logger.error("Failed to get cluster info", error=str(e))
            return {"error": str(e)}
    
    def _get_resource_count(self, quick_fetch, full_fetch) -> int:
        """
        Get resource count efficiently.
        First tries limit=1 with remaining_item_count, falls back to full list.
        """
        try:
            result = quick_fetch()
            remaining = getattr(result.metadata, 'remaining_item_count', None)
            if remaining is not None:
                return int(remaining) + len(result.items)
            else:
                # remaining_item_count not available, fall back to full list
                full_result = full_fetch()
                return len(full_result.items)
        except Exception as e:
            logger.warning("Failed to get resource count", error=str(e))
            return 0
    
    # =========================================================================
    # Namespaces
    # =========================================================================
    
    async def list_namespaces(self) -> List[Dict[str, Any]]:
        """List all namespaces"""
        return await asyncio.to_thread(self._list_namespaces_sync)
    
    def _list_namespaces_sync(self) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            namespaces = self._core_v1.list_namespace()
            return [
                {
                    "name": ns.metadata.name,
                    "uid": ns.metadata.uid,
                    "status": ns.status.phase,
                    "labels": ns.metadata.labels or {},
                    "annotations": ns.metadata.annotations or {},
                    "created_at": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
                }
                for ns in namespaces.items
            ]
        except ApiException as e:
            logger.error("Failed to list namespaces", status=e.status, reason=e.reason)
            return []
    
    # =========================================================================
    # Deployments
    # =========================================================================
    
    async def list_deployments(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List deployments (optionally filtered by namespace)"""
        return await asyncio.to_thread(self._list_deployments_sync, namespace)
    
    def _list_deployments_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                deployments = self._apps_v1.list_namespaced_deployment(namespace)
            else:
                deployments = self._apps_v1.list_deployment_for_all_namespaces()
            
            result = []
            for dep in deployments.items:
                try:
                    result.append(self._format_workload(dep, "deployment"))
                except Exception as e:
                    logger.warning("Failed to format deployment",
                                   name=getattr(dep.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list deployments", namespace=namespace, status=e.status, reason=e.reason)
            return []

    def _format_workload(self, workload, workload_type: str) -> Dict[str, Any]:
        """Format deployment/statefulset with container details and spec_hash.
        Defensively handles missing spec/template/containers."""
        import hashlib
        containers_info = []
        spec_hash = ""

        pod_spec = None
        try:
            if workload.spec and workload.spec.template and workload.spec.template.spec:
                pod_spec = workload.spec.template.spec
        except AttributeError:
            pass

        if pod_spec:
            for c in (pod_spec.containers or []):
                try:
                    env_list = c.env or []
                    env_str = json.dumps([
                        {"name": e.name, "value": e.value,
                         "value_from": str(e.value_from) if e.value_from else None}
                        for e in env_list
                    ], sort_keys=True, default=str)
                    env_hash = hashlib.sha256(env_str.encode()).hexdigest()[:16]
                except Exception:
                    env_hash = ""

                resources = {}
                try:
                    if c.resources:
                        if c.resources.requests:
                            resources["requests"] = {k: str(v) for k, v in c.resources.requests.items()}
                        if c.resources.limits:
                            resources["limits"] = {k: str(v) for k, v in c.resources.limits.items()}
                except Exception:
                    pass

                containers_info.append({
                    "name": c.name or "",
                    "image": c.image or "",
                    "resources": resources,
                    "env_hash": env_hash
                })

            try:
                spec_dict = pod_spec.to_dict()
                spec_hash = hashlib.sha256(
                    json.dumps(spec_dict, sort_keys=True, default=str).encode()
                ).hexdigest()[:16]
            except Exception:
                spec_hash = ""

        replicas = (workload.spec.replicas or 0) if workload.spec else 0
        if workload_type == "deployment":
            ready = (workload.status.available_replicas or 0) if workload.status else 0
        else:
            ready = (workload.status.ready_replicas or 0) if workload.status else 0

        first_image = None
        if pod_spec and pod_spec.containers:
            first_image = pod_spec.containers[0].image

        return {
            "name": workload.metadata.name,
            "namespace": workload.metadata.namespace,
            "uid": workload.metadata.uid,
            "replicas": replicas,
            "available_replicas": ready,
            "ready_replicas": ready,
            "labels": workload.metadata.labels or {},
            "image": first_image,
            "containers": containers_info,
            "spec_hash": spec_hash,
            "workload_type": workload_type,
            "created_at": workload.metadata.creation_timestamp.isoformat() if workload.metadata.creation_timestamp else None
        }
    
    # =========================================================================
    # Pods
    # =========================================================================
    
    async def list_pods(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """List pods (optionally filtered by namespace and/or labels)"""
        return await asyncio.to_thread(self._list_pods_sync, namespace, label_selector)
    
    def _list_pods_sync(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            kwargs = {}
            if label_selector:
                kwargs['label_selector'] = label_selector
            
            if namespace:
                pods = self._core_v1.list_namespaced_pod(namespace, **kwargs)
            else:
                pods = self._core_v1.list_pod_for_all_namespaces(**kwargs)
            
            return [
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "uid": pod.metadata.uid,
                    "status": pod.status.phase,
                    "node_name": pod.spec.node_name,
                    "labels": pod.metadata.labels or {},
                    "ip": pod.status.pod_ip,
                    "created_at": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                }
                for pod in pods.items
            ]
        except ApiException as e:
            logger.error("Failed to list pods", namespace=namespace, status=e.status, reason=e.reason)
            return []
    
    # =========================================================================
    # Services
    # =========================================================================
    
    async def list_services(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List services"""
        return await asyncio.to_thread(self._list_services_sync, namespace)
    
    def _list_services_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                services = self._core_v1.list_namespaced_service(namespace)
            else:
                services = self._core_v1.list_service_for_all_namespaces()
            
            result = []
            for svc in services.items:
                try:
                    result.append({
                        "name": svc.metadata.name,
                        "namespace": svc.metadata.namespace,
                        "uid": svc.metadata.uid,
                        "type": svc.spec.type if svc.spec else "ClusterIP",
                        "cluster_ip": svc.spec.cluster_ip if svc.spec else None,
                        "ports": [
                            {
                                "port": p.port, 
                                "protocol": p.protocol, 
                                "target_port": str(p.target_port) if p.target_port is not None else str(p.port) if p.port is not None else "",
                                "name": p.name or "",
                                "app_protocol": getattr(p, 'app_protocol', None) or ""
                            }
                            for p in (svc.spec.ports or [])
                        ] if svc.spec else [],
                        "labels": svc.metadata.labels or {},
                        "selector": (svc.spec.selector or {}) if svc.spec else {},
                        "created_at": svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else None
                    })
                except Exception as e:
                    logger.warning("Failed to format service",
                                   name=getattr(svc.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list services", namespace=namespace, status=e.status, reason=e.reason)
            return []
    
    # =========================================================================
    # ConfigMaps
    # =========================================================================

    async def list_configmaps(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List configmaps with data hash (not raw data) for change detection"""
        return await asyncio.to_thread(self._list_configmaps_sync, namespace)

    def _list_configmaps_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                configmaps = self._core_v1.list_namespaced_config_map(namespace)
            else:
                configmaps = self._core_v1.list_config_map_for_all_namespaces()

            result = []
            for cm in configmaps.items:
                try:
                    result.append({
                        "name": cm.metadata.name,
                        "namespace": cm.metadata.namespace,
                        "uid": cm.metadata.uid,
                        "data_hash": self._compute_data_hash(cm.data),
                        "workload_type": "configmap",
                        "created_at": cm.metadata.creation_timestamp.isoformat() if cm.metadata.creation_timestamp else None
                    })
                except Exception as e:
                    logger.warning("Failed to format configmap",
                                   name=getattr(cm.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list configmaps", namespace=namespace, status=e.status, reason=e.reason)
            return []

    # =========================================================================
    # Secrets
    # =========================================================================

    async def list_secrets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List secrets with data hash (not raw data) for change detection"""
        return await asyncio.to_thread(self._list_secrets_sync, namespace)

    def _list_secrets_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                secrets = self._core_v1.list_namespaced_secret(namespace)
            else:
                secrets = self._core_v1.list_secret_for_all_namespaces()

            result = []
            for sec in secrets.items:
                try:
                    if sec.type in ('kubernetes.io/service-account-token',):
                        continue
                    result.append({
                        "name": sec.metadata.name,
                        "namespace": sec.metadata.namespace,
                        "uid": sec.metadata.uid,
                        "data_hash": self._compute_data_hash(sec.data),
                        "type": sec.type or "Opaque",
                        "workload_type": "secret",
                        "created_at": sec.metadata.creation_timestamp.isoformat() if sec.metadata.creation_timestamp else None
                    })
                except Exception as e:
                    logger.warning("Failed to format secret",
                                   name=getattr(sec.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list secrets", namespace=namespace, status=e.status, reason=e.reason)
            return []

    @staticmethod
    def _compute_data_hash(data: Optional[dict]) -> str:
        """Hash only the .data field - ignores metadata/status/managedFields.
        OpenShift timestamp updates do not affect this hash."""
        import hashlib
        if not data:
            return "empty"
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    # =========================================================================
    # NetworkPolicies
    # =========================================================================

    async def list_network_policies(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List network policies with spec hash"""
        return await asyncio.to_thread(self._list_network_policies_sync, namespace)

    def _list_network_policies_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                netpols = self._networking_v1.list_namespaced_network_policy(namespace)
            else:
                netpols = self._networking_v1.list_network_policy_for_all_namespaces()

            import hashlib
            result = []
            for np in netpols.items:
                try:
                    spec_dict = np.spec.to_dict() if np.spec else {}
                    spec_hash = hashlib.sha256(
                        json.dumps(spec_dict, sort_keys=True, default=str).encode()
                    ).hexdigest()[:16]
                    result.append({
                        "name": np.metadata.name,
                        "namespace": np.metadata.namespace,
                        "uid": np.metadata.uid,
                        "spec_hash": spec_hash,
                        "workload_type": "networkpolicy",
                        "created_at": np.metadata.creation_timestamp.isoformat() if np.metadata.creation_timestamp else None
                    })
                except Exception as e:
                    logger.warning("Failed to format network policy",
                                   name=getattr(np.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list network policies", namespace=namespace, status=e.status, reason=e.reason)
            return []

    # =========================================================================
    # Ingress
    # =========================================================================

    async def list_ingresses(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List ingresses with spec hash (status/LB IP excluded)"""
        return await asyncio.to_thread(self._list_ingresses_sync, namespace)

    def _list_ingresses_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                ingresses = self._networking_v1.list_namespaced_ingress(namespace)
            else:
                ingresses = self._networking_v1.list_ingress_for_all_namespaces()

            import hashlib
            result = []
            for ing in ingresses.items:
                try:
                    spec_dict = ing.spec.to_dict() if ing.spec else {}
                    spec_hash = hashlib.sha256(
                        json.dumps(spec_dict, sort_keys=True, default=str).encode()
                    ).hexdigest()[:16]

                    hosts = []
                    if ing.spec and ing.spec.rules:
                        hosts = [r.host for r in ing.spec.rules if r.host]

                    result.append({
                        "name": ing.metadata.name,
                        "namespace": ing.metadata.namespace,
                        "uid": ing.metadata.uid,
                        "spec_hash": spec_hash,
                        "hosts": hosts,
                        "workload_type": "ingress",
                        "created_at": ing.metadata.creation_timestamp.isoformat() if ing.metadata.creation_timestamp else None
                    })
                except Exception as e:
                    logger.warning("Failed to format ingress",
                                   name=getattr(ing.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list ingresses", namespace=namespace, status=e.status, reason=e.reason)
            return []

    # =========================================================================
    # OpenShift Routes
    # =========================================================================

    async def list_routes(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List OpenShift routes (graceful fail on non-OpenShift clusters)"""
        return await asyncio.to_thread(self._list_routes_sync, namespace)

    def _list_routes_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            import hashlib
            if namespace:
                routes_resp = self._custom_objects.list_namespaced_custom_object(
                    group="route.openshift.io", version="v1",
                    namespace=namespace, plural="routes"
                )
            else:
                routes_resp = self._custom_objects.list_cluster_custom_object(
                    group="route.openshift.io", version="v1", plural="routes"
                )

            result = []
            for route in routes_resp.get("items", []):
                metadata = route.get("metadata", {})
                spec = route.get("spec", {})
                spec_hash = hashlib.sha256(
                    json.dumps(spec, sort_keys=True, default=str).encode()
                ).hexdigest()[:16]

                result.append({
                    "name": metadata.get("name", ""),
                    "namespace": metadata.get("namespace", ""),
                    "uid": metadata.get("uid", ""),
                    "spec_hash": spec_hash,
                    "host": spec.get("host", ""),
                    "workload_type": "route",
                    "created_at": metadata.get("creationTimestamp")
                })
            return result
        except ApiException as e:
            if e.status == 404:
                logger.debug("Route API not available (non-OpenShift cluster)")
            else:
                logger.error("Failed to list routes", namespace=namespace, status=e.status, reason=e.reason)
            return []
        except Exception:
            logger.debug("Route API not available")
            return []

    # =========================================================================
    # StatefulSets
    # =========================================================================

    async def list_statefulsets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List statefulsets (optionally filtered by namespace)"""
        return await asyncio.to_thread(self._list_statefulsets_sync, namespace)

    def _list_statefulsets_sync(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            if namespace:
                statefulsets = self._apps_v1.list_namespaced_stateful_set(namespace)
            else:
                statefulsets = self._apps_v1.list_stateful_set_for_all_namespaces()

            result = []
            for sts in statefulsets.items:
                try:
                    result.append(self._format_workload(sts, "statefulset"))
                except Exception as e:
                    logger.warning("Failed to format statefulset",
                                   name=getattr(sts.metadata, 'name', '?'), error=str(e))
            return result
        except ApiException as e:
            logger.error("Failed to list statefulsets", namespace=namespace, status=e.status, reason=e.reason)
            return []

    # =========================================================================
    # Nodes
    # =========================================================================
    
    async def list_nodes(self) -> List[Dict[str, Any]]:
        """List all cluster nodes with their IPs"""
        return await asyncio.to_thread(self._list_nodes_sync)
    
    def _list_nodes_sync(self) -> List[Dict[str, Any]]:
        self._init_client()
        try:
            nodes = self._core_v1.list_node()
            
            result = []
            for node in nodes.items:
                # Extract IP addresses from node status
                internal_ip = ""
                external_ip = ""
                
                if node.status and node.status.addresses:
                    for addr in node.status.addresses:
                        if addr.type == "InternalIP":
                            internal_ip = addr.address
                        elif addr.type == "ExternalIP":
                            external_ip = addr.address
                
                # Get node info from status
                node_info = node.status.node_info if node.status else None
                
                result.append({
                    "name": node.metadata.name,
                    "uid": node.metadata.uid,
                    "internal_ip": internal_ip,
                    "external_ip": external_ip,
                    "status": self._get_node_status(node),
                    "labels": node.metadata.labels or {},
                    "kubelet_version": node_info.kubelet_version if node_info else "",
                    "os_image": node_info.os_image if node_info else "",
                    "container_runtime": node_info.container_runtime_version if node_info else "",
                    "architecture": node_info.architecture if node_info else "",
                    "created_at": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None
                })
            
            return result
        except ApiException as e:
            logger.error("Failed to list nodes", status=e.status, reason=e.reason)
            return []
    
    def _get_node_status(self, node) -> str:
        """Extract node status from conditions"""
        if not node.status or not node.status.conditions:
            return "Unknown"
        
        for condition in node.status.conditions:
            if condition.type == "Ready":
                return "Ready" if condition.status == "True" else "NotReady"
        
        return "Unknown"
    
    # =========================================================================
    # Labels
    # =========================================================================
    
    async def get_labels(self, resource_type: str = "pods", namespace: Optional[str] = None) -> List[str]:
        """Get unique labels from resources"""
        return await asyncio.to_thread(self._get_labels_sync, resource_type, namespace)
    
    def _get_labels_sync(self, resource_type: str, namespace: Optional[str]) -> List[str]:
        self._init_client()
        labels_set = set()
        
        try:
            if resource_type == "pods":
                if namespace:
                    items = self._core_v1.list_namespaced_pod(namespace).items
                else:
                    items = self._core_v1.list_pod_for_all_namespaces().items
            elif resource_type == "deployments":
                if namespace:
                    items = self._apps_v1.list_namespaced_deployment(namespace).items
                else:
                    items = self._apps_v1.list_deployment_for_all_namespaces().items
            else:
                return []
            
            for item in items:
                if item.metadata.labels:
                    for key, value in item.metadata.labels.items():
                        labels_set.add(f"{key}={value}")
            
            return sorted(list(labels_set))
        except ApiException as e:
            logger.error("Failed to get labels", resource_type=resource_type, status=e.status)
            return []
    
    # =========================================================================
    # Inspector Gadget Health Check
    # =========================================================================
    
    async def check_gadget_health(self, gadget_namespace: str) -> Dict[str, Any]:
        """
        Check Inspector Gadget DaemonSet health.
        
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
        return await asyncio.to_thread(self._check_gadget_health_sync, gadget_namespace)
    
    def _check_gadget_health_sync(self, gadget_namespace: str) -> Dict[str, Any]:
        self._init_client()
        
        issues = []
        total_restarts = 0
        ebpf_capable = True
        version = None
        
        try:
            # 1. Check DaemonSet status
            ds = self._apps_v1.read_namespaced_daemon_set(
                name="inspektor-gadget",
                namespace=gadget_namespace
            )
            
            desired = ds.status.desired_number_scheduled or 0
            ready = ds.status.number_ready or 0
            
            # Get version from container image
            if ds.spec.template.spec.containers:
                image = ds.spec.template.spec.containers[0].image
                if ':' in image:
                    version = image.split(':')[-1]
            
            if desired == 0:
                issues.append("No nodes scheduled for DaemonSet")
            elif ready < desired:
                issues.append(f"Only {ready}/{desired} pods ready")
            
            # 2. Check individual pods for restarts
            pods = self._core_v1.list_namespaced_pod(
                namespace=gadget_namespace,
                label_selector="app=inspektor-gadget"
            )
            
            has_active_errors = False
            for pod in pods.items:
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        total_restarts += cs.restart_count
                        
                        if cs.state.waiting:
                            reason = cs.state.waiting.reason
                            if reason in ['CrashLoopBackOff', 'Error', 'ImagePullBackOff']:
                                issues.append(f"Pod {pod.metadata.name}: {reason}")
                                ebpf_capable = False
                                has_active_errors = True
            
            # High restart count indicates instability, but only affects status if very high
            # Use pod_count * 10 as threshold (allows for normal restarts over time)
            # Only mark as issue, don't disable ebpf_capable if pods are currently running
            if total_restarts > len(pods.items) * 10:
                issues.append(f"High restart count: {total_restarts}")
                # Only disable ebpf if there are also active errors
                if has_active_errors:
                    ebpf_capable = False
            
            # 3. Check pod logs for eBPF indicators
            if pods.items and not issues:
                try:
                    logs = self._core_v1.read_namespaced_pod_log(
                        name=pods.items[0].metadata.name,
                        namespace=gadget_namespace,
                        tail_lines=50
                    )
                    
                    logs_lower = logs.lower()
                    if 'gadget tracer manager' in logs_lower and 'starting' in logs_lower:
                        ebpf_capable = True
                    
                    error_indicators = ['permission denied', 'operation not permitted', 'failed to load']
                    for indicator in error_indicators:
                        if indicator in logs_lower:
                            issues.append(f"eBPF issue: {indicator}")
                            ebpf_capable = False
                            break
                except Exception:
                    pass  # Log reading is optional
            
            # Determine health status
            # Priority: All pods running and no active errors = healthy (even with past restarts)
            if desired == 0:
                health_status = "unknown"
            elif ready == desired and not has_active_errors:
                # All pods running, no active errors - healthy even if there were past restarts
                if issues:
                    health_status = "degraded"  # Has warnings but functional
                else:
                    health_status = "healthy"
            elif ready == desired and ebpf_capable:
                health_status = "degraded"
            elif ready > 0 and ebpf_capable:
                health_status = "degraded"
            elif ready > 0 and not ebpf_capable:
                health_status = "unhealthy"
            else:
                health_status = "unhealthy"
            
            logger.info("Gadget health check completed",
                       health_status=health_status,
                       pods_ready=ready,
                       pods_total=desired,
                       version=version)
            
            return {
                "health_status": health_status,
                "version": version,
                "error": "; ".join(issues) if issues else None,
                "pods_ready": ready,
                "pods_total": desired,
                "details": {
                    "total_restarts": total_restarts,
                    "ebpf_capable": ebpf_capable,
                    "issues": issues
                }
            }
            
        except ApiException as e:
            if e.status == 404:
                return {
                    "health_status": "unknown",
                    "version": None,
                    "error": "DaemonSet not found",
                    "pods_ready": 0,
                    "pods_total": 0,
                    "details": {"issues": ["DaemonSet not found"]}
                }
            logger.error("Gadget health check API error", status=e.status, reason=e.reason)
            return {
                "health_status": "unknown",
                "version": None,
                "error": f"API error: {e.reason}",
                "pods_ready": 0,
                "pods_total": 0,
                "details": {"issues": [f"API error: {e.reason}"]}
            }
        except Exception as e:
            logger.error("Gadget health check failed", error=str(e))
            return {
                "health_status": "unknown",
                "version": None,
                "error": str(e),
                "pods_ready": 0,
                "pods_total": 0,
                "details": {"issues": [str(e)]}
            }


# =========================================================================
# Client Factory with TTL-based Caching
# =========================================================================

class KubernetesClientFactory:
    """
    Factory for creating Kubernetes clients.
    Manages client instances for different clusters with TTL-based caching.
    
    Features:
    - Singleton pattern for default in-cluster client
    - TTL-based cache for remote cluster clients
    - Thread-safe client creation
    - Automatic cleanup of expired clients
    """
    
    _clients: Dict[str, KubernetesClient] = {}
    _client_timestamps: Dict[str, datetime] = {}
    _default_client: Optional[KubernetesClient] = None
    _lock = None  # Will be initialized on first use
    
    # Cache TTL (seconds) - clients older than this will be recreated
    CLIENT_TTL = 300  # 5 minutes
    
    @classmethod
    def _get_lock(cls):
        """Get or create the asyncio lock (lazy initialization)"""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()
        return cls._lock
    
    @classmethod
    def get_client(
        cls,
        cluster_id: str = "default",
        connection_type: str = "in-cluster",
        **kwargs
    ) -> KubernetesClient:
        """
        Get or create a Kubernetes client for a cluster.
        
        Thread-safe with TTL-based cache invalidation for remote clusters.
        
        Args:
            cluster_id: Unique identifier for the cluster
            connection_type: "in-cluster", "kubeconfig", or "token"
            **kwargs: Additional connection parameters (api_server_url, token, ca_cert, etc.)
            
        Returns:
            KubernetesClient instance
        """
        with cls._get_lock():
            # Return singleton for default in-cluster
            if cluster_id == "default" and connection_type == "in-cluster":
                if cls._default_client is None:
                    cls._default_client = KubernetesClient(
                        connection_type="in-cluster",
                        cluster_id="default"
                    )
                return cls._default_client
            
            # Check if cached client exists and is still valid
            if cluster_id in cls._clients:
                created_at = cls._client_timestamps.get(cluster_id)
                now = datetime.utcnow()
                
                if created_at and (now - created_at).total_seconds() < cls.CLIENT_TTL:
                    # Cache hit - return existing client
                    logger.debug("Returning cached K8s client",
                                cluster_id=cluster_id,
                                age_seconds=(now - created_at).total_seconds())
                    return cls._clients[cluster_id]
                else:
                    # TTL expired - close old client and create new one
                    logger.info("K8s client cache expired, recreating",
                               cluster_id=cluster_id)
                    try:
                        cls._clients[cluster_id].close()
                    except Exception as e:
                        logger.warning("Error closing expired client",
                                      cluster_id=cluster_id, error=str(e))
                    del cls._clients[cluster_id]
                    if cluster_id in cls._client_timestamps:
                        del cls._client_timestamps[cluster_id]
            
            # Create new client
            logger.info("Creating new K8s client",
                       cluster_id=cluster_id,
                       connection_type=connection_type)
            
            new_client = KubernetesClient(
                connection_type=connection_type,
                cluster_id=cluster_id,
                **kwargs
            )
            
            # Cache the client
            cls._clients[cluster_id] = new_client
            cls._client_timestamps[cluster_id] = datetime.utcnow()
            
            return new_client
    
    @classmethod
    def invalidate(cls, cluster_id: str) -> bool:
        """
        Invalidate and close cached client for a specific cluster.
        
        Use when cluster credentials change or on connection errors.
        
        Args:
            cluster_id: Cluster ID to invalidate
            
        Returns:
            True if client was found and invalidated, False otherwise
        """
        with cls._get_lock():
            if cluster_id in cls._clients:
                try:
                    cls._clients[cluster_id].close()
                except Exception as e:
                    logger.warning("Error closing client during invalidation",
                                  cluster_id=cluster_id, error=str(e))
                
                del cls._clients[cluster_id]
                if cluster_id in cls._client_timestamps:
                    del cls._client_timestamps[cluster_id]
                
                logger.info("K8s client invalidated", cluster_id=cluster_id)
                return True
            return False
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """
        Get statistics about cached clients.
        
        Returns:
            Dict with cache statistics
        """
        with cls._get_lock():
            now = datetime.utcnow()
            clients_info = {}
            
            for cluster_id, created_at in cls._client_timestamps.items():
                age = (now - created_at).total_seconds()
                clients_info[cluster_id] = {
                    "age_seconds": age,
                    "expires_in_seconds": max(0, cls.CLIENT_TTL - age)
                }
            
            return {
                "total_cached_clients": len(cls._clients),
                "has_default_client": cls._default_client is not None,
                "ttl_seconds": cls.CLIENT_TTL,
                "clients": clients_info
            }
    
    @classmethod
    def close_all(cls):
        """Close all client connections and clear cache"""
        with cls._get_lock():
            for cluster_id, client in cls._clients.items():
                try:
                    client.close()
                except Exception as e:
                    logger.warning("Error closing client",
                                  cluster_id=cluster_id, error=str(e))
            
            cls._clients = {}
            cls._client_timestamps = {}
            
            if cls._default_client:
                try:
                    cls._default_client.close()
                except Exception as e:
                    logger.warning("Error closing default client", error=str(e))
                cls._default_client = None
            
            logger.info("All K8s clients closed")


# Default singleton instance for in-cluster usage
kubernetes_client = KubernetesClient(connection_type="in-cluster", cluster_id="default")
