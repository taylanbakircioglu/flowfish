"""
Pod Discovery - Collects pod IP to name mappings from Kubernetes

This module uses Cluster Manager gRPC API to build an IP -> Pod/Service mapping cache.
Used to enrich network flow events with destination pod/service information.

Safety:
- Fails gracefully if Cluster Manager is not available
- Falls back to kubectl if gRPC fails
- Returns empty cache on errors
- Does not affect main event collection flow
"""

import asyncio
import json
import subprocess
import shutil
import socket
import ipaddress
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass
from datetime import datetime
import structlog
import grpc

# Import Cluster Manager proto
try:
    from proto import cluster_manager_pb2
    from proto import cluster_manager_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False

logger = structlog.get_logger()


@dataclass
class PodInfo:
    """Pod metadata from Kubernetes"""
    name: str
    namespace: str
    ip: str
    node: str
    labels: Dict[str, str]
    owner_kind: str  # Deployment, ReplicaSet, DaemonSet, StatefulSet
    owner_name: str
    # Extended metadata
    uid: str = ''  # Pod UID
    host_ip: str = ''  # Node IP
    start_time: str = ''  # Pod start time
    phase: str = ''  # Running, Pending, Succeeded, Failed, Unknown
    container_name: str = ''  # Primary container name
    container_image: str = ''  # Container image
    service_account: str = ''  # Service account name
    restart_count: int = 0  # Total restarts
    annotations: Dict[str, str] = None  # Pod annotations
    
    def __post_init__(self):
        if self.annotations is None:
            self.annotations = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "pod_name": self.name,
            "namespace": self.namespace,
            "pod_ip": self.ip,
            "node_name": self.node,
            "labels": self.labels,
            "owner_kind": self.owner_kind,
            "owner_name": self.owner_name,
            # Extended metadata
            "pod_uid": self.uid,
            "host_ip": self.host_ip,
            "start_time": self.start_time,
            "phase": self.phase,
            "container_name": self.container_name,
            "container_image": self.container_image,
            "service_account": self.service_account,
            "restart_count": self.restart_count,
            "annotations": self.annotations
        }


@dataclass
class NodeInfo:
    """Kubernetes Node metadata"""
    name: str           # worker1.internal.corp
    internal_ip: str    # 10.180.143.26
    external_ip: str    # (optional)
    status: str         # Ready, NotReady
    labels: Dict[str, str]
    kubelet_version: str = ''
    os_image: str = ''
    container_runtime: str = ''
    architecture: str = ''


@dataclass
class ResolvedInfo:
    """
    General IP resolution result.
    Used for extended lookup that covers pod, service, node, DNS, and CIDR.
    """
    name: str
    ip: str
    source: str  # "pod", "service", "node", "dns", "cidr"
    namespace: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    owner_kind: Optional[str] = None
    owner_name: Optional[str] = None
    network_type: Optional[str] = None  # CIDR-based network category for grouping


class DNSCache:
    """
    In-memory cache for reverse DNS lookups.
    TTL-based expiration to handle dynamic DNS entries.
    """
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[Optional[str], datetime]] = {}  # ip -> (hostname, cached_at)
        self._ttl = ttl_seconds
        self._negative_ttl = 60  # Cache negative results for shorter time
    
    def lookup(self, ip: str) -> Tuple[Optional[str], bool]:
        """
        Lookup hostname by IP.
        
        Returns:
            (hostname, cache_hit) - hostname can be None if not resolved
        """
        if ip in self._cache:
            hostname, cached_at = self._cache[ip]
            age = (datetime.utcnow() - cached_at).total_seconds()
            ttl = self._negative_ttl if hostname is None else self._ttl
            
            if age < ttl:
                return (hostname, True)
            # Expired - remove from cache
            del self._cache[ip]
        
        return (None, False)
    
    def store(self, ip: str, hostname: Optional[str]):
        """Store DNS result (including negative results)"""
        self._cache[ip] = (hostname, datetime.utcnow())
    
    def stats(self) -> dict:
        """Return cache statistics"""
        valid_entries = sum(1 for h, _ in self._cache.values() if h is not None)
        return {
            "total_entries": len(self._cache),
            "resolved_entries": valid_entries,
            "unresolved_entries": len(self._cache) - valid_entries
        }


class PodIPCache:
    """
    In-memory cache for IP -> Pod mappings
    
    Thread-safe for concurrent reads.
    Refresh updates the entire cache atomically.
    """
    
    def __init__(self):
        self._cache: Dict[str, PodInfo] = {}  # ip -> PodInfo
        self._last_refresh: Optional[datetime] = None
        self._refresh_count = 0
    
    def lookup(self, ip: str) -> Optional[PodInfo]:
        """
        Lookup pod info by IP address
        
        Returns None if IP is not in cache (graceful fallback)
        """
        return self._cache.get(ip)
    
    def get_pod_name(self, ip: str) -> Optional[str]:
        """Get just the pod name for an IP, or None"""
        info = self.lookup(ip)
        return info.name if info else None
    
    def get_namespace(self, ip: str) -> Optional[str]:
        """Get just the namespace for an IP, or None"""
        info = self.lookup(ip)
        return info.namespace if info else None
    
    def enrich_destination(self, ip: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Enrich destination with pod name and namespace
        
        Returns (namespace, pod_name) tuple, either can be None
        """
        info = self.lookup(ip)
        if info:
            return (info.namespace, info.name)
        return (None, None)
    
    def get_all_pods(self) -> List[PodInfo]:
        """Return all pods in cache"""
        return list(self._cache.values())
    
    def get_all_pods_as_dicts(self) -> List[Dict[str, Any]]:
        """Return all pods as dictionaries for serialization"""
        return [pod.to_dict() for pod in self._cache.values()]
    
    def update(self, pods: Dict[str, PodInfo]):
        """Atomically update the cache with new pod mappings"""
        self._cache = pods
        self._last_refresh = datetime.utcnow()
        self._refresh_count += 1
    
    def stats(self) -> dict:
        """Return cache statistics"""
        return {
            "pod_count": len(self._cache),
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "refresh_count": self._refresh_count
        }


class PodDiscovery:
    """
    Discovers pods and services in Kubernetes cluster
    
    Primary: Uses Cluster Manager gRPC API (recommended)
    Fallback: Uses kubectl if gRPC is unavailable
    
    Runs as a background task, refreshing the cache periodically.
    Designed to fail gracefully - never blocks main event collection.
    """
    
    def __init__(
        self,
        kubeconfig: Optional[str] = None,
        context: Optional[str] = None,
        refresh_interval_seconds: int = 30,
        cluster_manager_url: Optional[str] = None
    ):
        self.kubeconfig = kubeconfig
        self.context = context
        self.refresh_interval = refresh_interval_seconds
        self.cluster_manager_url = cluster_manager_url or "cluster-manager:5001"
        self.cache = PodIPCache()
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None
        self._grpc_channel: Optional[grpc.aio.Channel] = None
        self._grpc_stub = None
        # BUG FIX: Use self.cluster_manager_url (with default) instead of cluster_manager_url (parameter)
        self._use_grpc = GRPC_AVAILABLE and self.cluster_manager_url is not None
        
        # Extended discovery caches
        self._node_cache: Dict[str, NodeInfo] = {}  # internal_ip -> NodeInfo
        self._dns_cache = DNSCache(ttl_seconds=300)  # DNS cache with 5 min TTL
        
        # Service port protocol cache: "cluster_ip:port" -> {"app_protocol": "grpc", "name": "grpc-port"}
        self._service_port_protocols: Dict[str, Dict[str, str]] = {}
        
        # Known CIDR ranges for labeling (configurable)
        # Order matters: more specific ranges should come first
        # Stored as list of tuples for ordered checking
        # NOTE: Only include CONFIRMED pod/service network ranges
        # Unknown 10.x.x.x ranges could be datacenter IPs, not pod networks
        self._known_cidrs_ordered = [
            # OpenShift DEFAULT ranges (well-documented)
            ("10.128.0.0/14", "Pod-Network"),       # OpenShift default pod network
            ("172.30.0.0/16", "Service-Network"),   # OpenShift default service network
            
            # Custom OpenShift cluster ranges (configure if needed for your environment)
            ("10.194.0.0/16", "Pod-Network"),       # Custom pod network (cluster-1)
            ("10.208.0.0/16", "Pod-Network"),       # Custom pod network (cluster-2)
            ("10.196.0.0/16", "Service-Network"),   # Custom service CIDR
            
            # Common Kubernetes service CIDR ranges
            ("10.96.0.0/12", "Service-Network"),    # K8s default service-cluster-ip-range
            
            # Common pod network ranges (well-known defaults)
            ("10.244.0.0/16", "Pod-Network"),       # Flannel default
            ("10.42.0.0/16", "Pod-Network"),        # K3s/RKE default
            
            # Generic internal ranges (checked last)
            # These cover datacenter IPs and unknown pod networks
            ("10.0.0.0/8", "Internal-Network"),     # General internal (RFC 1918)
            ("192.168.0.0/16", "Private-Network"),  # Private network (RFC 1918)
            ("172.16.0.0/12", "Private-Network"),   # Private network (RFC 1918)
        ]
        
        # Legacy dict for backward compatibility
        self._known_cidrs = {cidr: label for cidr, label in self._known_cidrs_ordered}
    
    async def start(self, namespaces: Optional[list] = None):
        """
        Start pod discovery
        
        Args:
            namespaces: List of namespaces to discover. None = all namespaces.
        """
        self._running = True
        self._namespaces = namespaces
        self._cache_ready = False
        
        # Initialize gRPC connection to Cluster Manager
        if self._use_grpc:
            try:
                self._grpc_channel = grpc.aio.insecure_channel(self.cluster_manager_url)
                self._grpc_stub = cluster_manager_pb2_grpc.ClusterManagerServiceStub(self._grpc_channel)
                logger.info("Connected to Cluster Manager gRPC", url=self.cluster_manager_url)
            except Exception as e:
                logger.warning("Failed to connect to Cluster Manager, falling back to kubectl", error=str(e))
                self._use_grpc = False
        
        # Initial discovery with retry for robustness
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._refresh_cache()
                
                # Check if we got meaningful data
                service_count = sum(1 for v in self.cache._cache.values() 
                                   if hasattr(v, 'owner_kind') and v.owner_kind == 'Service')
                
                if service_count > 0 or len(self.cache._cache) > 0:
                    self._cache_ready = True
                    break
                elif attempt < max_retries - 1:
                    logger.warning("Cache refresh returned empty, retrying...", 
                                  attempt=attempt + 1, max_retries=max_retries)
                    await asyncio.sleep(2)  # Wait before retry
            except Exception as e:
                logger.warning("Cache refresh attempt failed", 
                              attempt=attempt + 1, error=str(e))
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
        
        # Start background refresh
        self._refresh_task = asyncio.create_task(self._background_refresh())
        
        # Detailed startup logging for debugging
        service_count = sum(1 for v in self.cache._cache.values() 
                           if hasattr(v, 'owner_kind') and v.owner_kind == 'Service')
        pod_count = len(self.cache._cache) - service_count
        
        logger.info("Pod discovery started",
                   pod_count=pod_count,
                   service_count=service_count,
                   total_cache=len(self.cache._cache),
                   cache_ready=self._cache_ready,
                   namespaces=namespaces,
                   method="grpc" if self._use_grpc else "kubectl")
    
    def is_cache_ready(self) -> bool:
        """Check if cache has been populated with at least some data"""
        return getattr(self, '_cache_ready', False)
    
    async def wait_for_cache(self, timeout: float = 10.0) -> bool:
        """
        Wait for cache to be ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if cache is ready, False if timeout
        """
        start = asyncio.get_event_loop().time()
        while not self.is_cache_ready():
            if asyncio.get_event_loop().time() - start > timeout:
                return False
            await asyncio.sleep(0.5)
        return True
    
    async def stop(self):
        """Stop pod discovery"""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        
        # Close gRPC channel
        if self._grpc_channel:
            await self._grpc_channel.close()
            self._grpc_channel = None
            self._grpc_stub = None
        
        logger.info("Pod discovery stopped", stats=self.cache.stats())
    
    async def _background_refresh(self):
        """Background task to refresh pod cache periodically with exponential backoff on errors"""
        from app.config import settings as _settings
        backoff_max = _settings.pod_discovery_error_backoff_max
        current_backoff = 0
        
        while self._running:
            try:
                sleep_time = max(self.refresh_interval, current_backoff)
                await asyncio.sleep(sleep_time)
                await self._refresh_cache()
                current_backoff = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                if current_backoff == 0:
                    current_backoff = self.refresh_interval
                else:
                    current_backoff = min(current_backoff * 2, backoff_max)
                logger.warning("Pod cache refresh failed, backing off",
                             error=str(e), next_retry_seconds=current_backoff)
    
    async def _refresh_cache(self):
        """Refresh the pod, service, and node cache from Kubernetes"""
        try:
            # Discover pods, services, and nodes in parallel
            # Use return_exceptions=True so one failure doesn't block the others
            pods_task = self._discover_pods()
            services_task = self._discover_services()
            nodes_task = self._discover_nodes()
            
            results = await asyncio.gather(pods_task, services_task, nodes_task, return_exceptions=True)
            
            # Handle results - each could be a dict or an exception
            pods = results[0] if isinstance(results[0], dict) else {}
            services = results[1] if isinstance(results[1], dict) else {}
            nodes = results[2] if isinstance(results[2], dict) else {}
            
            if isinstance(results[0], Exception):
                logger.warning("Pod discovery failed", error=str(results[0]))
            if isinstance(results[1], Exception):
                logger.warning("Service discovery failed", error=str(results[1]))
            if isinstance(results[2], Exception):
                logger.warning("Node discovery failed", error=str(results[2]))
            
            # Discover endpoints to map Pod IPs to Service protocols
            # This enables L7 protocol detection for direct Pod-to-Pod traffic
            try:
                await self._discover_endpoints()
            except Exception as e:
                logger.warning("Endpoint discovery failed", error=str(e))
            
            # Merge pods and services - pods take priority for overlapping IPs
            combined = {**services, **pods}  # Pods overwrite services if same IP
            
            self.cache.update(combined)
            self._node_cache = nodes  # Update node cache
            
            # Detailed logging for debugging IP resolution issues
            # Log namespace distribution for services
            service_namespaces = {}
            for ip, info in services.items():
                ns = info.namespace
                service_namespaces[ns] = service_namespaces.get(ns, 0) + 1
            
            # Sample some service ClusterIPs for debugging
            sample_service_ips = list(services.keys())[:10]
            sample_services = {ip: services[ip].name for ip in sample_service_ips} if sample_service_ips else {}
            
            logger.info("Pod/Service/Node cache refreshed", 
                        pod_count=len(pods), 
                        service_count=len(services),
                        node_count=len(nodes),
                        total=len(combined),
                        service_namespace_count=len(service_namespaces),
                        sample_service_ips=sample_services)
        except Exception as e:
            logger.warning("Failed to refresh pod cache", error=str(e))
            # Keep existing cache on error
    
    async def _discover_pods(self) -> Dict[str, PodInfo]:
        """
        Discover pods using kubectl for remote clusters, gRPC for local.
        After discovery, enriches pods with owner (Deployment/StatefulSet) annotations.
        
        Returns dict of ip -> PodInfo
        """
        pods: Dict[str, PodInfo] = {}

        if self.kubeconfig:
            logger.debug("Using kubectl for pod discovery (remote cluster)",
                        kubeconfig_prefix=self.kubeconfig[:50] if self.kubeconfig else None)
            pods = await self._discover_pods_via_kubectl()
        elif self._use_grpc and self._grpc_stub:
            try:
                pods = await self._discover_pods_via_grpc()
            except Exception as e:
                logger.warning("gRPC pod discovery failed, falling back to kubectl", error=str(e))
                pods = await self._discover_pods_via_kubectl()
        else:
            pods = await self._discover_pods_via_kubectl()

        try:
            await self._enrich_with_owner_annotations(pods)
        except Exception as e:
            logger.warning("Owner annotation enrichment failed (non-fatal)", error=str(e))

        return pods

    async def _enrich_with_owner_annotations(self, pods: Dict[str, PodInfo]):
        """Merge Deployment/StatefulSet annotations into their pods.
        Pod's own annotations always take priority over owner annotations.
        This enables deployment-level metadata (git-repo, team, etc.) to
        be visible on pods even when set only on the Deployment object."""
        if not pods:
            return

        owner_annotations: Dict[tuple, Dict[str, str]] = {}

        if not self.kubeconfig and self._use_grpc and self._grpc_stub:
            owner_annotations = await self._fetch_owner_annotations_grpc()
        else:
            owner_annotations = await self._fetch_owner_annotations_kubectl()

        if not owner_annotations:
            return

        merged_count = 0
        for pod_info in pods.values():
            deploy_name = self._resolve_owner_deployment_name(pod_info)
            if not deploy_name:
                continue

            key = (pod_info.namespace, deploy_name)
            owner_anns = owner_annotations.get(key)
            if owner_anns:
                merged = {**owner_anns, **pod_info.annotations}
                pod_info.annotations = merged
                merged_count += 1

        if merged_count:
            logger.info("Enriched pods with owner annotations",
                        merged_count=merged_count,
                        owner_count=len(owner_annotations))

    @staticmethod
    def _resolve_owner_deployment_name(pod_info: 'PodInfo') -> str:
        """Determine the owning Deployment/StatefulSet name for a pod.
        Strategy:
        1. Standard K8s labels (most reliable)
        2. For ReplicaSet-owned pods, strip the pod-template-hash suffix
        3. For StatefulSet/DaemonSet-owned pods, use owner_name directly
        4. Fallback to owner_name from labels
        """
        labels = pod_info.labels or {}

        name = labels.get('app.kubernetes.io/name') or labels.get('app')
        if name:
            return name

        if pod_info.owner_kind == 'ReplicaSet' and pod_info.owner_name:
            template_hash = labels.get('pod-template-hash', '')
            if template_hash and pod_info.owner_name.endswith(f'-{template_hash}'):
                return pod_info.owner_name[:-len(f'-{template_hash}')]
            parts = pod_info.owner_name.rsplit('-', 1)
            if len(parts) == 2 and len(parts[1]) >= 8 and parts[1].isalnum():
                return parts[0]

        if pod_info.owner_kind in ('StatefulSet', 'DaemonSet') and pod_info.owner_name:
            return pod_info.owner_name

        return pod_info.owner_name or ''

    async def _fetch_owner_annotations_grpc(self) -> Dict[tuple, Dict[str, str]]:
        """Fetch Deployment and StatefulSet annotations via gRPC.
        Returns {(namespace, name): filtered_annotations}."""
        result: Dict[tuple, Dict[str, str]] = {}
        namespaces_to_query = self._namespaces if self._namespaces else [None]

        for ns in namespaces_to_query:
            try:
                dep_req = cluster_manager_pb2.ListDeploymentsRequest(
                    cluster_id="", namespace=ns or ""
                )
                dep_resp = await self._grpc_stub.ListDeployments(dep_req, timeout=30)
                for dep in dep_resp.deployments:
                    anns = dict(dep.annotations) if dep.annotations else {}
                    if anns:
                        result[(dep.namespace, dep.name)] = anns
            except grpc.RpcError as e:
                logger.debug("gRPC ListDeployments failed for namespace",
                             namespace=ns, error=str(e))

            try:
                sts_req = cluster_manager_pb2.ListStatefulSetsRequest(
                    cluster_id="", namespace=ns or ""
                )
                sts_resp = await self._grpc_stub.ListStatefulSets(sts_req, timeout=30)
                for sts in sts_resp.statefulsets:
                    anns = dict(sts.annotations) if sts.annotations else {}
                    if anns:
                        result[(sts.namespace, sts.name)] = anns
            except grpc.RpcError as e:
                logger.debug("gRPC ListStatefulSets failed for namespace",
                             namespace=ns, error=str(e))

        logger.debug("Fetched owner annotations via gRPC", count=len(result))
        return result

    async def _fetch_owner_annotations_kubectl(self) -> Dict[tuple, Dict[str, str]]:
        """Fetch Deployment and StatefulSet annotations via kubectl.
        Returns {(namespace, name): filtered_annotations}."""
        result: Dict[tuple, Dict[str, str]] = {}
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            return result

        for resource_kind in ('deployments', 'statefulsets'):
            cmd = [kubectl_path, 'get', resource_kind, '-o', 'json']
            if self._namespaces:
                for ns in self._namespaces:
                    ns_result = await self._kubectl_get_owner_annotations(
                        kubectl_path, resource_kind, ns
                    )
                    result.update(ns_result)
                continue

            cmd.append('-A')
            if self.kubeconfig:
                cmd.extend(['--kubeconfig', self.kubeconfig])
            if self.context:
                cmd.extend(['--context', self.context])

            try:
                proc_result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda c=cmd: subprocess.run(c, capture_output=True, text=True, timeout=30)
                )
                if proc_result.returncode == 0:
                    result.update(self._parse_owner_annotations_json(proc_result.stdout))
            except Exception as e:
                logger.debug("kubectl owner annotation fetch failed",
                             resource=resource_kind, error=str(e))

        logger.debug("Fetched owner annotations via kubectl", count=len(result))
        return result

    async def _kubectl_get_owner_annotations(
        self, kubectl_path: str, resource_kind: str, namespace: str
    ) -> Dict[tuple, Dict[str, str]]:
        """Fetch annotations for a specific resource kind in a namespace."""
        cmd = [kubectl_path, 'get', resource_kind, '-n', namespace, '-o', 'json']
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])

        try:
            proc_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda c=cmd: subprocess.run(c, capture_output=True, text=True, timeout=30)
            )
            if proc_result.returncode == 0:
                return self._parse_owner_annotations_json(proc_result.stdout)
        except Exception as e:
            logger.debug("kubectl owner annotation fetch failed",
                         resource=resource_kind, namespace=namespace, error=str(e))
        return {}

    @staticmethod
    def _parse_owner_annotations_json(json_str: str) -> Dict[tuple, Dict[str, str]]:
        """Parse kubectl JSON output and extract filtered annotations.
        Applies the same filtering rules as cluster-manager (skip kubectl.kubernetes.io/,
        kubernetes.io/, openshift.io/ prefixes and values > 500 chars)."""
        result: Dict[tuple, Dict[str, str]] = {}
        try:
            data = json.loads(json_str)
            for item in data.get('items', []):
                metadata = item.get('metadata', {})
                name = metadata.get('name', '')
                namespace = metadata.get('namespace', '')
                raw_anns = metadata.get('annotations', {}) or {}
                filtered = {
                    k: v for k, v in raw_anns.items()
                    if not k.startswith('kubectl.kubernetes.io/')
                    and not k.startswith('kubernetes.io/')
                    and not k.startswith('openshift.io/')
                    and len(str(v)) < 500
                }
                if filtered:
                    result[(namespace, name)] = filtered
        except (json.JSONDecodeError, Exception):
            pass
        return result
    
    async def _discover_pods_via_grpc(self) -> Dict[str, PodInfo]:
        """Discover pods using Cluster Manager gRPC API"""
        pods: Dict[str, PodInfo] = {}
        
        # Query each namespace or all namespaces
        namespaces_to_query = self._namespaces if self._namespaces else [None]
        
        for ns in namespaces_to_query:
            try:
                request = cluster_manager_pb2.ListPodsRequest(
                    cluster_id="",  # Empty = current cluster (in-cluster)
                    namespace=ns or ""
                )
                response = await self._grpc_stub.ListPods(request, timeout=30)
                
                for pod in response.pods:
                    # Note: PodInfo message has 'ip' field (not 'pod_ip')
                    pod_ip = pod.ip
                    if pod_ip:
                        # Extract owner info from labels or use defaults
                        owner_kind = "Unknown"
                        owner_name = pod.name
                        
                        # Try to extract owner from common label patterns
                        labels = dict(pod.labels) if pod.labels else {}
                        annotations = dict(pod.annotations) if pod.annotations else {}
                        if 'app.kubernetes.io/name' in labels:
                            owner_name = labels['app.kubernetes.io/name']
                        elif 'app' in labels:
                            owner_name = labels['app']
                        
                        pod_info = PodInfo(
                            name=pod.name,
                            namespace=pod.namespace,
                            ip=pod_ip,
                            node=pod.node_name or '',
                            labels=labels,
                            owner_kind=owner_kind,
                            owner_name=owner_name,
                            phase=pod.status,
                            annotations=annotations
                        )
                        pods[pod_ip] = pod_info
                        
            except grpc.RpcError as e:
                logger.warning("gRPC ListPods failed for namespace", 
                             namespace=ns, error=str(e))
        
        logger.debug("Discovered pods via gRPC", count=len(pods))
        return pods
    
    async def _discover_pods_via_kubectl(self) -> Dict[str, PodInfo]:
        """Fallback: Discover pods using kubectl"""
        # Check if kubectl is available
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            logger.warning("kubectl not found, pod discovery disabled")
            return {}
        
        # Build command
        cmd = [kubectl_path, 'get', 'pods', '-o', 'json']
        
        # Add namespace filter
        if self._namespaces:
            # For specific namespaces, we need to query each
            all_pods = {}
            for ns in self._namespaces:
                ns_pods = await self._get_pods_in_namespace(kubectl_path, ns)
                all_pods.update(ns_pods)
            return all_pods
        else:
            # All namespaces
            cmd.extend(['-A'])
        
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])
        
        # Run kubectl
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            if result.returncode != 0:
                logger.warning("kubectl get pods failed",
                             stderr=result.stderr[:200] if result.stderr else None)
                return {}
            
            return self._parse_pods_json(result.stdout)
            
        except subprocess.TimeoutExpired:
            logger.warning("kubectl get pods timed out")
            return {}
        except Exception as e:
            logger.warning("kubectl get pods error", error=str(e))
            return {}
    
    async def _get_pods_in_namespace(self, kubectl_path: str, namespace: str) -> Dict[str, PodInfo]:
        """Get pods in a specific namespace"""
        cmd = [kubectl_path, 'get', 'pods', '-n', namespace, '-o', 'json']
        
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            if result.returncode != 0:
                return {}
            
            return self._parse_pods_json(result.stdout)
            
        except Exception as e:
            logger.warning("Failed to get pods in namespace", 
                          namespace=namespace, error=str(e))
            return {}
    
    def _parse_pods_json(self, json_str: str) -> Dict[str, PodInfo]:
        """Parse kubectl get pods -o json output"""
        try:
            data = json.loads(json_str)
            pods = {}
            
            items = data.get('items', [])
            for item in items:
                try:
                    metadata = item.get('metadata', {})
                    status = item.get('status', {})
                    spec = item.get('spec', {})
                    
                    pod_ip = status.get('podIP')
                    if not pod_ip:
                        continue  # Skip pods without IP
                    
                    # Extract owner reference
                    owner_refs = metadata.get('ownerReferences', [])
                    owner_kind = ''
                    owner_name = ''
                    if owner_refs:
                        owner_kind = owner_refs[0].get('kind', '')
                        owner_name = owner_refs[0].get('name', '')
                    
                    # Extract container info (primary container)
                    containers = spec.get('containers', [])
                    container_name = ''
                    container_image = ''
                    if containers:
                        container_name = containers[0].get('name', '')
                        container_image = containers[0].get('image', '')
                    
                    # Extract container status for restart count
                    container_statuses = status.get('containerStatuses', [])
                    restart_count = 0
                    for cs in container_statuses:
                        restart_count += cs.get('restartCount', 0)
                    
                    # Filter annotations - only keep useful ones, skip large/internal ones
                    raw_annotations = metadata.get('annotations', {}) or {}
                    annotations = {
                        k: v for k, v in raw_annotations.items()
                        if not k.startswith('kubectl.kubernetes.io/')
                        and not k.startswith('kubernetes.io/')
                        and not k.startswith('openshift.io/')
                        and len(str(v)) < 500  # Skip very large values
                    }
                    
                    pod_info = PodInfo(
                        name=metadata.get('name', ''),
                        namespace=metadata.get('namespace', ''),
                        ip=pod_ip,
                        node=spec.get('nodeName', ''),
                        labels=metadata.get('labels', {}) or {},
                        owner_kind=owner_kind,
                        owner_name=owner_name,
                        # Extended metadata
                        uid=metadata.get('uid', ''),
                        host_ip=status.get('hostIP', ''),
                        start_time=status.get('startTime', ''),
                        phase=status.get('phase', ''),
                        container_name=container_name,
                        container_image=container_image,
                        service_account=spec.get('serviceAccountName', ''),
                        restart_count=restart_count,
                        annotations=annotations
                    )
                    
                    pods[pod_ip] = pod_info
                    
                except Exception as e:
                    logger.debug("Failed to parse pod", error=str(e))
                    continue
            
            return pods
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse pods JSON", error=str(e))
            return {}
    
    async def _discover_services(self) -> Dict[str, PodInfo]:
        """
        Discover Kubernetes Services and their ClusterIPs
        
        For remote clusters (kubeconfig specified), we use kubectl directly
        because gRPC goes to local ClusterManager which doesn't have 
        remote cluster's service information.
        
        Returns dict of clusterIP -> PodInfo (using service info)
        This helps resolve Service IP -> Service Name for network flows
        """
        # Remote cluster: use kubectl with session kubeconfig
        # gRPC goes to local ClusterManager which doesn't have remote cluster services
        if self.kubeconfig:
            logger.info("Using kubectl for service discovery (remote cluster)",
                       kubeconfig_prefix=self.kubeconfig[:50] if self.kubeconfig else None)
            result = await self._discover_services_via_kubectl()
            logger.info("Service discovery via kubectl completed (remote)", service_count=len(result))
            return result
        
        # Local cluster: try gRPC first (Cluster Manager) with retry
        if self._use_grpc and self._grpc_stub:
            for attempt in range(2):  # Quick retry for transient failures
                try:
                    result = await self._discover_services_via_grpc()
                    if result:  # Got some services
                        logger.info("Service discovery via gRPC succeeded", 
                                   service_count=len(result), attempt=attempt + 1)
                        return result
                except Exception as e:
                    logger.warning("gRPC service discovery attempt failed", 
                                  attempt=attempt + 1, error=str(e), error_type=type(e).__name__)
                    if attempt == 0:
                        await asyncio.sleep(1)  # Brief wait before retry
        
        # Fallback to kubectl
        logger.info("Falling back to kubectl for service discovery")
        result = await self._discover_services_via_kubectl()
        logger.info("Service discovery via kubectl completed", service_count=len(result))
        return result
    
    async def _discover_services_via_grpc(self) -> Dict[str, PodInfo]:
        """Discover services using Cluster Manager gRPC API"""
        services: Dict[str, PodInfo] = {}
        
        try:
            request = cluster_manager_pb2.ListServicesRequest(
                cluster_id="",  # Empty = current cluster (in-cluster)
                namespace=""  # Empty = all namespaces
            )
            response = await self._grpc_stub.ListServices(request, timeout=30)
            
            for svc in response.services:
                cluster_ip = svc.cluster_ip
                if not cluster_ip or cluster_ip == 'None':
                    continue  # Skip headless services
                
                labels = dict(svc.labels) if svc.labels else {}
                
                # Store port protocol information for L7 protocol detection
                for port in svc.ports:
                    port_key = f"{cluster_ip}:{port.port}"
                    self._service_port_protocols[port_key] = {
                        "app_protocol": port.app_protocol or "",
                        "name": port.name or "",
                        "l4_protocol": port.protocol or "TCP"
                    }
                
                service_info = PodInfo(
                    name=svc.name,
                    namespace=svc.namespace,
                    ip=cluster_ip,
                    node='',  # Services don't have nodes
                    labels=labels,
                    owner_kind='Service',
                    owner_name=svc.name,
                    annotations={'service.type': svc.type or 'ClusterIP'}
                )
                
                services[cluster_ip] = service_info
                
        except grpc.RpcError as e:
            logger.warning("gRPC ListServices failed", error=str(e))
            raise
        
        logger.debug("Discovered services via gRPC", count=len(services), port_protocols=len(self._service_port_protocols))
        return services
    
    async def _discover_services_via_kubectl(self) -> Dict[str, PodInfo]:
        """Fallback: Discover services using kubectl"""
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            return {}
        
        cmd = [kubectl_path, 'get', 'services', '-A', '-o', 'json']
        
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            if result.returncode != 0:
                logger.warning("kubectl get services failed",
                             stderr=result.stderr[:200] if result.stderr else None)
                return {}
            
            return self._parse_services_json(result.stdout)
            
        except subprocess.TimeoutExpired:
            logger.warning("kubectl get services timed out")
            return {}
        except Exception as e:
            logger.warning("kubectl get services error", error=str(e))
            return {}
    
    def _parse_services_json(self, json_str: str) -> Dict[str, PodInfo]:
        """Parse kubectl get services -o json output"""
        try:
            data = json.loads(json_str)
            services = {}
            
            items = data.get('items', [])
            for item in items:
                try:
                    metadata = item.get('metadata', {})
                    spec = item.get('spec', {})
                    
                    cluster_ip = spec.get('clusterIP')
                    if not cluster_ip or cluster_ip == 'None':
                        continue  # Skip headless services
                    
                    service_name = metadata.get('name', '')
                    namespace = metadata.get('namespace', '')
                    
                    # Store port protocol information for L7 protocol detection
                    for port_info in spec.get('ports', []):
                        port_num = port_info.get('port')
                        if port_num:
                            port_key = f"{cluster_ip}:{port_num}"
                            self._service_port_protocols[port_key] = {
                                "app_protocol": port_info.get('appProtocol') or "",
                                "name": port_info.get('name') or "",
                                "l4_protocol": port_info.get('protocol') or "TCP"
                            }
                    
                    # Create a PodInfo for the service (using service metadata)
                    service_info = PodInfo(
                        name=service_name,
                        namespace=namespace,
                        ip=cluster_ip,
                        node='',  # Services don't have nodes
                        labels=metadata.get('labels', {}) or {},
                        owner_kind='Service',
                        owner_name=service_name,
                        # Service type info
                        annotations={'service.type': spec.get('type', 'ClusterIP')}
                    )
                    
                    services[cluster_ip] = service_info
                    
                    # Also map any external IPs
                    for ext_ip in spec.get('externalIPs', []):
                        if ext_ip:
                            services[ext_ip] = service_info
                    
                except Exception as e:
                    logger.debug("Failed to parse service", error=str(e))
                    continue
            
            logger.debug("Discovered services", count=len(services), port_protocols=len(self._service_port_protocols))
            return services
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse services JSON", error=str(e))
            return {}
    
    # =========================================================================
    # Endpoints Discovery (Pod IP -> Service Protocol Mapping)
    # =========================================================================
    
    async def _discover_endpoints(self) -> None:
        """
        Discover service endpoints to map Pod IPs to Service protocols.
        
        This enables L7 protocol detection for traffic going directly to Pod IPs
        instead of Service ClusterIPs.
        """
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            logger.debug("kubectl not found, skipping endpoints discovery")
            return
        
        cmd = [kubectl_path, 'get', 'endpoints', '-A', '-o', 'json']
        
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            if result.returncode != 0:
                logger.warning("kubectl get endpoints failed",
                             stderr=result.stderr[:200] if result.stderr else None)
                return
            
            data = json.loads(result.stdout)
            endpoint_count = 0
            
            for ep in data.get('items', []):
                metadata = ep.get('metadata', {})
                ep_name = metadata.get('name', '')
                ep_namespace = metadata.get('namespace', '')
                
                # Get port information from subsets
                for subset in ep.get('subsets', []):
                    ports = subset.get('ports', [])
                    addresses = subset.get('addresses', [])
                    
                    for port_info in ports:
                        port_num = port_info.get('port')
                        port_name = port_info.get('name', '')
                        port_protocol = port_info.get('protocol', 'TCP')  # L4 protocol
                        app_protocol = port_info.get('appProtocol', '')  # L7 protocol (K8s 1.20+)
                        
                        if not port_num:
                            continue
                        
                        # For each endpoint address (pod IP), cache the protocol
                        for addr in addresses:
                            pod_ip = addr.get('ip')
                            if not pod_ip:
                                continue
                            
                            port_key = f"{pod_ip}:{port_num}"
                            
                            # Check if we already have this from service discovery
                            if port_key not in self._service_port_protocols:
                                self._service_port_protocols[port_key] = {
                                    "app_protocol": app_protocol,
                                    "name": port_name,
                                    "l4_protocol": port_protocol,
                                    "source": "endpoint"  # Track that this came from endpoint discovery
                                }
                                endpoint_count += 1
            
            logger.info("Discovered endpoint protocols", 
                       endpoint_count=endpoint_count,
                       total_port_protocols=len(self._service_port_protocols))
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse endpoints JSON", error=str(e))
        except Exception as e:
            logger.warning("Endpoints discovery failed", error=str(e))
    
    # =========================================================================
    # Node Discovery
    # =========================================================================
    
    async def _discover_nodes(self) -> Dict[str, NodeInfo]:
        """
        Discover nodes using kubectl for remote clusters, gRPC for local
        
        For remote clusters (kubeconfig specified), we use kubectl directly
        because gRPC goes to local ClusterManager which doesn't have 
        remote cluster's node information.
        
        Returns dict of internal_ip -> NodeInfo
        """
        # Remote cluster: use kubectl with session kubeconfig
        # gRPC goes to local ClusterManager which doesn't have remote cluster nodes
        if self.kubeconfig:
            logger.debug("Using kubectl for node discovery (remote cluster)")
            return await self._discover_nodes_via_kubectl()
        
        # Local cluster: try gRPC first (faster, uses ClusterManager cache)
        if self._use_grpc and self._grpc_stub:
            try:
                return await self._discover_nodes_via_grpc()
            except Exception as e:
                logger.warning("gRPC node discovery failed, falling back to kubectl", error=str(e))
        
        # Fallback to kubectl
        return await self._discover_nodes_via_kubectl()
    
    async def _discover_nodes_via_grpc(self) -> Dict[str, NodeInfo]:
        """Discover nodes using Cluster Manager gRPC API"""
        nodes: Dict[str, NodeInfo] = {}
        
        try:
            request = cluster_manager_pb2.ListNodesRequest(cluster_id="")
            response = await self._grpc_stub.ListNodes(request)
            
            if response.error:
                logger.warning("ListNodes returned error", error=response.error)
                return {}
            
            for node in response.nodes:
                internal_ip = node.internal_ip
                if not internal_ip:
                    continue
                
                node_info = NodeInfo(
                    name=node.name,
                    internal_ip=internal_ip,
                    external_ip=node.external_ip or '',
                    status=node.status or 'Unknown',
                    labels=dict(node.labels) if node.labels else {},
                    kubelet_version=node.kubelet_version or '',
                    os_image=node.os_image or '',
                    container_runtime=node.container_runtime or '',
                    architecture=node.architecture or ''
                )
                
                nodes[internal_ip] = node_info
                
                # Also map external IP if available
                if node.external_ip:
                    nodes[node.external_ip] = node_info
            
            logger.debug("Discovered nodes via gRPC", count=len(nodes))
            return nodes
            
        except Exception as e:
            logger.warning("gRPC node discovery error", error=str(e))
            raise
    
    async def _discover_nodes_via_kubectl(self) -> Dict[str, NodeInfo]:
        """Fallback: Discover nodes using kubectl"""
        kubectl_path = shutil.which('kubectl')
        if not kubectl_path:
            return {}
        
        cmd = [kubectl_path, 'get', 'nodes', '-o', 'json']
        
        if self.kubeconfig:
            cmd.extend(['--kubeconfig', self.kubeconfig])
        if self.context:
            cmd.extend(['--context', self.context])
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            if result.returncode != 0:
                logger.warning("kubectl get nodes failed",
                             stderr=result.stderr[:200] if result.stderr else None)
                return {}
            
            return self._parse_nodes_json(result.stdout)
            
        except subprocess.TimeoutExpired:
            logger.warning("kubectl get nodes timed out")
            return {}
        except Exception as e:
            logger.warning("kubectl get nodes error", error=str(e))
            return {}
    
    def _parse_nodes_json(self, json_str: str) -> Dict[str, NodeInfo]:
        """Parse kubectl get nodes -o json output"""
        try:
            data = json.loads(json_str)
            nodes = {}
            
            items = data.get('items', [])
            for item in items:
                try:
                    metadata = item.get('metadata', {})
                    status = item.get('status', {})
                    node_info_data = status.get('nodeInfo', {})
                    
                    # Extract IPs from addresses
                    internal_ip = ''
                    external_ip = ''
                    for addr in status.get('addresses', []):
                        addr_type = addr.get('type', '')
                        addr_value = addr.get('address', '')
                        if addr_type == 'InternalIP':
                            internal_ip = addr_value
                        elif addr_type == 'ExternalIP':
                            external_ip = addr_value
                    
                    if not internal_ip:
                        continue
                    
                    # Get node status from conditions
                    node_status = 'Unknown'
                    for condition in status.get('conditions', []):
                        if condition.get('type') == 'Ready':
                            node_status = 'Ready' if condition.get('status') == 'True' else 'NotReady'
                            break
                    
                    node = NodeInfo(
                        name=metadata.get('name', ''),
                        internal_ip=internal_ip,
                        external_ip=external_ip,
                        status=node_status,
                        labels=metadata.get('labels', {}) or {},
                        kubelet_version=node_info_data.get('kubeletVersion', ''),
                        os_image=node_info_data.get('osImage', ''),
                        container_runtime=node_info_data.get('containerRuntimeVersion', ''),
                        architecture=node_info_data.get('architecture', '')
                    )
                    
                    nodes[internal_ip] = node
                    
                    # Also map external IP if available
                    if external_ip:
                        nodes[external_ip] = node
                    
                except Exception as e:
                    logger.debug("Failed to parse node", error=str(e))
                    continue
            
            logger.debug("Discovered nodes via kubectl", count=len(nodes))
            return nodes
            
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse nodes JSON", error=str(e))
            return {}
    
    # =========================================================================
    # Extended Lookup - Hybrid Resolution
    # =========================================================================
    
    async def lookup_extended(self, ip: str) -> Optional[ResolvedInfo]:
        """
        Hybrid IP resolution with multiple sources.
        
        Priority order:
        1. Pod cache (fastest, K8s pod IPs)
        2. Service cache (K8s service ClusterIPs)  
        3. Node cache (K8s node internal IPs)
        4. Reverse DNS (PTR lookup, cached)
        5. CIDR labeling (last resort - uses IP as name, adds network_type metadata)
        
        Args:
            ip: IP address to resolve
            
        Returns:
            ResolvedInfo if resolved, None otherwise
            
        IMPORTANT: When CIDR resolution is used, the IP address itself becomes the
        node name (not the CIDR label). This ensures each destination IP gets its
        own unique node in the graph. The CIDR label is stored in network_type
        field for UI grouping/display purposes.
        """
        if not ip:
            return None
        
        # 1. Pod/Service cache (combined in self.cache)
        pod_info = self.cache.lookup(ip)
        if pod_info:
            return ResolvedInfo(
                name=pod_info.name,
                ip=ip,
                source="pod" if pod_info.owner_kind != "Service" else "service",
                namespace=pod_info.namespace,
                labels=pod_info.labels,
                owner_kind=pod_info.owner_kind,
                owner_name=pod_info.owner_name,
                network_type=self._get_cidr_label(ip)  # Add network type for all resolutions
            )
        
        # 2. Node cache
        node_info = self._node_cache.get(ip)
        if node_info:
            return ResolvedInfo(
                name=node_info.name,
                ip=ip,
                source="node",
                namespace="kube-system",  # Nodes are cluster-level
                labels=node_info.labels,
                network_type="Node-Network"
            )
        
        # 3. Reverse DNS (with caching)
        hostname = await self._resolve_via_dns(ip)
        if hostname:
            return ResolvedInfo(
                name=hostname,
                ip=ip,
                source="dns",
                network_type=self._get_cidr_label(ip) or "External"
            )
        
        # 4. CIDR labeling - CRITICAL FIX:
        # Use IP address as node name (unique identifier)
        # Use CIDR label as network_type metadata (for grouping/display)
        # This prevents ALL internal traffic from consolidating into ONE "Internal-Network" node
        label = self._get_cidr_label(ip)
        if label:
            # Log cache miss for potential Service ClusterIPs (helps debug)
            # Only log occasionally to avoid log spam
            if label == "Service-Network" and not hasattr(self, '_logged_service_misses'):
                self._logged_service_misses = set()
            
            if label == "Service-Network" and ip not in getattr(self, '_logged_service_misses', set()):
                logger.debug("Service ClusterIP not found in cache (will show as IP)", 
                            ip=ip, 
                            cache_size=len(self.cache._cache) if hasattr(self.cache, '_cache') else 'N/A',
                            service_count=sum(1 for v in self.cache._cache.values() 
                                             if hasattr(v, 'owner_kind') and v.owner_kind == 'Service') 
                                         if hasattr(self.cache, '_cache') else 'N/A')
                if len(getattr(self, '_logged_service_misses', set())) < 20:
                    self._logged_service_misses.add(ip)
            
            return ResolvedInfo(
                name=ip,  # CHANGED: Use actual IP, not CIDR label, as unique identifier
                ip=ip,
                source="cidr",
                namespace=self._get_cidr_namespace(label),  # Derive namespace from network type
                network_type=label  # Store CIDR label as metadata for frontend grouping
            )
        
        # 5. Unknown IP - still create unique node per IP
        return ResolvedInfo(
            name=ip,
            ip=ip,
            source="unknown",
            namespace="external",
            network_type="Unknown"
        )
    
    async def _resolve_via_dns(self, ip: str) -> Optional[str]:
        """
        Reverse DNS lookup with caching.
        
        Uses socket.gethostbyaddr() with timeout protection.
        Results (including negative) are cached.
        """
        # Check cache first
        cached_hostname, cache_hit = self._dns_cache.lookup(ip)
        if cache_hit:
            return cached_hostname
        
        # Perform DNS lookup (async with timeout)
        try:
            loop = asyncio.get_event_loop()
            
            def do_lookup():
                try:
                    hostname, _, _ = socket.gethostbyaddr(ip)
                    return hostname
                except socket.herror:
                    return None
                except socket.gaierror:
                    return None
            
            hostname = await asyncio.wait_for(
                loop.run_in_executor(None, do_lookup),
                timeout=2.0  # 2 second timeout for DNS
            )
            
            # Cache result (including None for negative caching)
            self._dns_cache.store(ip, hostname)
            
            if hostname:
                logger.debug("DNS resolved", ip=ip, hostname=hostname)
            
            return hostname
            
        except asyncio.TimeoutError:
            # Cache negative result on timeout
            self._dns_cache.store(ip, None)
            logger.debug("DNS lookup timed out", ip=ip)
            return None
        except Exception as e:
            # Cache negative result on error
            self._dns_cache.store(ip, None)
            logger.debug("DNS lookup failed", ip=ip, error=str(e))
            return None
    
    def _get_cidr_label(self, ip: str) -> Optional[str]:
        """
        Get a human-readable label based on IP's CIDR range.
        
        This is used for network_type metadata field, NOT for node naming.
        Labels indicate the network type (e.g., "Pod-Network", "Service-Network").
        
        Special handling for SDN gateway IPs (only in CONFIRMED pod networks):
        - *.*.*.1 addresses: Subnet gateway (first IP of subnet)
        - *.*.*.2 addresses: SDN gateway (OpenShift OVN)
        
        IMPORTANT: Ordered list is used so more specific ranges are checked first.
        E.g., 10.194.0.0/16 (Pod-Network) is checked before 10.0.0.0/8 (Internal-Network)
        """
        try:
            addr = ipaddress.ip_address(ip)
            ip_parts = ip.split('.')
            
            if len(ip_parts) == 4:
                last_octet = ip_parts[3]
                
                # SDN Gateway detection ONLY for CONFIRMED pod network ranges
                # .1 addresses are typically subnet gateways (first usable IP)
                # .2 addresses are typically SDN/OVN gateway (secondary)
                if last_octet in ('1', '2'):
                    # Only check CONFIRMED pod network ranges (not datacenter IPs)
                    confirmed_pod_ranges = [
                        "10.128.0.0/14",  # OpenShift default
                        "10.194.0.0/16",  # Custom cluster-1
                        "10.208.0.0/16",  # Custom cluster-2
                        "10.244.0.0/16",  # Flannel
                        "10.42.0.0/16",   # K3s/RKE
                    ]
                    for cidr in confirmed_pod_ranges:
                        try:
                            if addr in ipaddress.ip_network(cidr, strict=False):
                                return "SDN-Gateway"
                        except ValueError:
                            continue
            
            # Check against known CIDR ranges (ordered - more specific first)
            for cidr, label in self._known_cidrs_ordered:
                try:
                    if addr in ipaddress.ip_network(cidr, strict=False):
                        return label
                except ValueError:
                    continue
            
            # Check if it's a private IP (but not in known ranges)
            if addr.is_private:
                return "Private-Network"
            
            # Public IP
            if addr.is_global:
                return "External-Network"
            
        except ValueError:
            pass
        
        return None
    
    def _get_cidr_namespace(self, network_type: str) -> str:
        """
        Derive a logical namespace based on network type.
        
        This helps with frontend filtering and visualization:
        - Pod-Network, Service-Network -> 'cluster-network' (internal K8s traffic)
        - Internal-Network, Private-Network -> 'internal-network' (datacenter traffic)
        - SDN-Gateway -> 'sdn-infrastructure' (network infrastructure)
        - External-Network -> 'external' (internet traffic)
        """
        if network_type in ('Pod-Network', 'Service-Network'):
            return 'cluster-network'
        elif network_type in ('Internal-Network', 'Private-Network'):
            return 'internal-network'
        elif network_type == 'SDN-Gateway':
            return 'sdn-infrastructure'
        elif network_type in ('External-Network', 'External-IP'):
            return 'external'
        else:
            return 'external'
    
    def get_extended_stats(self) -> dict:
        """Return extended statistics including all caches"""
        return {
            "pod_service_cache": self.cache.stats(),
            "node_cache": {
                "count": len(self._node_cache),
                "nodes": [n.name for n in self._node_cache.values()]
            },
            "dns_cache": self._dns_cache.stats(),
            "port_protocols_cache": {
                "count": len(self._service_port_protocols)
            }
        }
    
    # =========================================================================
    # L7 Protocol Detection
    # =========================================================================
    
    def determine_app_protocol(self, dest_ip: str, dest_port: int) -> str:
        """
        Determine the application-layer (L7) protocol for a connection.
        
        Uses a priority-based approach:
        1. Kubernetes Service appProtocol field (most reliable)
        2. Service port name convention (Istio-style: grpc, http, https, etc.)
        3. Well-known port mapping (fallback)
        
        Args:
            dest_ip: Destination IP address
            dest_port: Destination port number
            
        Returns:
            Protocol string (e.g., "GRPC", "HTTP", "HTTPS", "TCP")
        """
        # 1. Check service port protocols cache (appProtocol or port name)
        port_key = f"{dest_ip}:{dest_port}"
        port_info = self._service_port_protocols.get(port_key)
        
        if port_info:
            # Priority 1: appProtocol field (Kubernetes 1.20+)
            app_protocol = port_info.get("app_protocol", "")
            if app_protocol:
                return self._normalize_protocol(app_protocol)
            
            # Priority 2: port name convention (Istio-style)
            port_name = port_info.get("name", "")
            if port_name:
                detected = self._detect_protocol_from_name(port_name)
                if detected:
                    return detected
        
        # Priority 3: Well-known port mapping (fallback)
        return self._infer_protocol_from_port(dest_port)
    
    def _normalize_protocol(self, protocol: str) -> str:
        """Normalize protocol string to uppercase standard format"""
        if not protocol:
            return "TCP"
        
        protocol_lower = protocol.lower()
        
        # Handle kubernetes.io/ prefixed protocols
        if protocol_lower.startswith("kubernetes.io/"):
            protocol_lower = protocol_lower.replace("kubernetes.io/", "")
        
        # Normalize common variations
        protocol_map = {
            "grpc": "GRPC",
            "grpc-web": "GRPC-WEB",
            "http": "HTTP",
            "http2": "HTTP2",
            "h2": "HTTP2",
            "h2c": "HTTP2",  # HTTP/2 cleartext
            "https": "HTTPS",
            "tls": "TLS",
            "tcp": "TCP",
            "udp": "UDP",
            "mongo": "MONGODB",
            "mysql": "MYSQL",
            "redis": "REDIS",
            "kafka": "KAFKA",
            "amqp": "AMQP",
        }
        
        return protocol_map.get(protocol_lower, protocol.upper())
    
    def _detect_protocol_from_name(self, port_name: str) -> Optional[str]:
        """
        Detect protocol from service port name (Istio convention).
        
        Convention: <protocol>[-<suffix>] e.g., grpc, grpc-web, http-metrics, https
        """
        if not port_name:
            return None
        
        name_lower = port_name.lower()
        
        # Check for protocol prefixes
        if name_lower.startswith("grpc"):
            return "GRPC"
        elif name_lower.startswith("http2") or name_lower.startswith("h2"):
            return "HTTP2"
        elif name_lower.startswith("https"):
            return "HTTPS"
        elif name_lower.startswith("http"):
            return "HTTP"
        elif name_lower.startswith("tcp"):
            return "TCP"
        elif name_lower.startswith("udp"):
            return "UDP"
        elif name_lower.startswith("mongo"):
            return "MONGODB"
        elif name_lower.startswith("mysql"):
            return "MYSQL"
        elif name_lower.startswith("redis"):
            return "REDIS"
        elif name_lower.startswith("kafka"):
            return "KAFKA"
        elif name_lower.startswith("amqp"):
            return "AMQP"
        elif name_lower.startswith("tls"):
            return "TLS"
        
        return None
    
    def _infer_protocol_from_port(self, port: int) -> str:
        """
        Infer protocol from well-known port number (last resort fallback).
        
        This is the least reliable method - only used when service metadata
        is not available.
        """
        # Well-known ports mapping
        port_protocols = {
            # Web protocols
            80: "HTTP",
            443: "HTTPS",
            8080: "HTTP",
            8443: "HTTPS",
            
            # gRPC common ports
            9090: "GRPC",  # Common gRPC port
            50051: "GRPC",  # Default gRPC port
            
            # Databases
            3306: "MYSQL",
            5432: "POSTGRESQL",
            27017: "MONGODB",
            6379: "REDIS",
            
            # Message queues
            5672: "AMQP",
            9092: "KAFKA",
            
            # Other
            22: "SSH",
            25: "SMTP",
            53: "DNS",
            110: "POP3",
            143: "IMAP",
        }
        
        return port_protocols.get(port, "TCP")

