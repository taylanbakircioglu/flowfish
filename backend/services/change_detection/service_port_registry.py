"""
Service Port Registry Module

Provides intelligent service port detection by leveraging Kubernetes Service definitions.
This eliminates ephemeral port noise from change detection.

Key Features:
- Caches Kubernetes Service ports from PostgreSQL
- Maps Pod names to their parent Services
- Maps ClusterIPs to Services
- Resolves raw connections to service-level connections
- Provides fallback for external/unknown connections

Usage:
    registry = ServicePortRegistry()
    await registry.refresh(cluster_id, namespaces=['default', 'prod'])
    
    # Check if a port is a known service port
    if registry.is_service_port('default', 8000):
        # This is a real service port
        
    # Resolve a connection to service level
    conn = registry.resolve_connection('pod-a', 'pod-b', 8000)
    if conn:
        # conn.dest_service = 'my-service'
"""

from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass
import re
import structlog

logger = structlog.get_logger(__name__)


# Minimal well-known service ports - only fundamental protocols
# Other ports should come from Kubernetes Service definitions
# This list is intentionally minimal to avoid product-specific assumptions
WELL_KNOWN_SERVICE_PORTS = {
    53,     # DNS - fundamental for service discovery
    80,     # HTTP - standard web protocol
    443,    # HTTPS - standard secure web protocol
}

# Ephemeral port range - ports in this range are NEVER service ports
EPHEMERAL_PORT_START = 32768
EPHEMERAL_PORT_END = 65535

# Maximum port to consider as potential service port for unknown destinations
MAX_FALLBACK_SERVICE_PORT = 32767


@dataclass(frozen=True)
class ServiceConnection:
    """
    Represents a service-level connection (not raw TCP flow).
    
    This aggregates multiple TCP connections between the same
    source workload and destination service into a single logical connection.
    """
    source_workload: str      # Deployment/StatefulSet name (not pod)
    source_namespace: str
    dest_service: str         # Service name or external endpoint
    dest_namespace: str
    dest_port: int            # Service port (not ephemeral)
    protocol: str = "TCP"
    
    def __hash__(self):
        return hash((
            self.source_workload, 
            self.dest_service, 
            self.dest_port, 
            self.protocol
        ))
    
    def __eq__(self, other):
        if not isinstance(other, ServiceConnection):
            return False
        return (
            self.source_workload == other.source_workload and
            self.dest_service == other.dest_service and
            self.dest_port == other.dest_port and
            self.protocol == other.protocol
        )


class ServicePortRegistry:
    """
    Kubernetes Service port registry for intelligent connection filtering.
    
    Caches Service definitions from PostgreSQL to determine:
    1. Which ports are actual service ports (not ephemeral)
    2. Which Services own which Pods
    3. Which ClusterIPs map to which Services
    
    This enables change detection to work at the SERVICE level
    instead of raw TCP flow level, eliminating ephemeral port noise.
    """
    
    def __init__(self):
        # namespace/service -> set of ports
        self._service_ports: Dict[str, Set[int]] = {}
        
        # namespace/pod -> namespace/service (or workload name)
        self._pod_to_workload: Dict[str, str] = {}
        
        # IP address -> namespace/service
        self._ip_to_service: Dict[str, str] = {}
        
        # All known service ports across all namespaces
        self._all_service_ports: Set[int] = set()
        
        # Track which cluster/namespaces we've loaded
        self._loaded_scope: Optional[Tuple[int, tuple]] = None
        
        self._database = None
    
    @property
    def database(self):
        """Lazy-load database connection"""
        if self._database is None:
            from database.postgresql import database
            self._database = database
        return self._database
    
    async def refresh(
        self, 
        cluster_id: int, 
        namespaces: Optional[List[str]] = None
    ) -> None:
        """
        Refresh the registry from PostgreSQL.
        
        Loads:
        1. All Services and their ports
        2. All Pods/Deployments and their ownership
        3. ClusterIP to Service mappings
        
        Args:
            cluster_id: Cluster to load services from
            namespaces: Optional list of namespaces to filter by
        """
        # Check if we already have this scope loaded
        scope_key = (cluster_id, tuple(sorted(namespaces or [])))
        if self._loaded_scope == scope_key:
            logger.debug("ServicePortRegistry already loaded for scope", 
                        cluster_id=cluster_id, namespaces=namespaces)
            return
        
        # Clear existing data
        self._service_ports.clear()
        self._pod_to_workload.clear()
        self._ip_to_service.clear()
        self._all_service_ports = set(WELL_KNOWN_SERVICE_PORTS)
        
        try:
            # 1. Load Services with their ports
            await self._load_services(cluster_id, namespaces)
            
            # 2. Load Pods/Deployments for workload mapping
            await self._load_workloads(cluster_id, namespaces)
            
            self._loaded_scope = scope_key
            
            logger.info(
                "ServicePortRegistry refreshed",
                cluster_id=cluster_id,
                namespaces=namespaces,
                service_count=len(self._service_ports),
                total_service_ports=len(self._all_service_ports),
                workload_mappings=len(self._pod_to_workload),
                ip_mappings=len(self._ip_to_service)
            )
            
        except Exception as e:
            logger.error("Failed to refresh ServicePortRegistry", error=str(e))
            # Keep well-known ports as fallback
            self._all_service_ports = set(WELL_KNOWN_SERVICE_PORTS)
    
    async def _load_services(
        self, 
        cluster_id: int, 
        namespaces: Optional[List[str]]
    ) -> None:
        """Load Kubernetes Services from workloads table."""
        
        namespace_filter = ""
        params = {"cluster_id": cluster_id}
        
        if namespaces:
            namespace_filter = "AND n.name = ANY(:namespaces)"
            params["namespaces"] = list(namespaces)
        
        query = f"""
            SELECT 
                w.name,
                n.name as namespace,
                w.metadata,
                w.ip_address
            FROM workloads w
            JOIN namespaces n ON w.namespace_id = n.id
            WHERE w.cluster_id = :cluster_id
              AND w.workload_type = 'service'
              AND w.is_active = true
              {namespace_filter}
        """
        
        try:
            services = await self.database.fetch_all(query, params)
            
            for svc in services:
                namespace = svc["namespace"]
                name = svc["name"]
                metadata = svc.get("metadata") or {}
                ports_raw = metadata.get("ports") if isinstance(metadata, dict) else None
                ip_address = svc.get("ip_address")
                
                # Parse ports from JSONB
                ports = self._parse_ports(ports_raw)
                
                if ports:
                    key = f"{namespace}/{name}"
                    self._service_ports[key] = ports
                    self._all_service_ports.update(ports)
                    
                    # Map ClusterIP to service
                    if ip_address:
                        ip_str = str(ip_address)
                        self._ip_to_service[ip_str] = key
                        
        except Exception as e:
            logger.error("Failed to load services", error=str(e))
    
    async def _load_workloads(
        self, 
        cluster_id: int, 
        namespaces: Optional[List[str]]
    ) -> None:
        """Load Pods and Deployments for workload mapping."""
        
        namespace_filter = ""
        params = {"cluster_id": cluster_id}
        
        if namespaces:
            namespace_filter = "AND n.name = ANY(:namespaces)"
            params["namespaces"] = list(namespaces)
        
        query = f"""
            SELECT 
                w.name,
                n.name as namespace,
                w.workload_type,
                w.owner_name,
                w.owner_kind,
                w.ip_address
            FROM workloads w
            JOIN namespaces n ON w.namespace_id = n.id
            WHERE w.cluster_id = :cluster_id
              AND w.is_active = true
              AND w.workload_type IN ('pod', 'deployment', 'statefulset', 'daemonset')
              {namespace_filter}
        """
        
        try:
            workloads = await self.database.fetch_all(query, params)
            
            for wl in workloads:
                namespace = wl["namespace"]
                name = wl["name"]
                wl_type = wl["workload_type"]
                owner_name = wl.get("owner_name")
                ip_address = wl.get("ip_address")
                
                # Determine the workload name (prefer owner for pods)
                if wl_type == "pod" and owner_name:
                    workload_name = owner_name
                else:
                    workload_name = self._extract_workload_name(name, wl_type)
                
                key = f"{namespace}/{name}"
                self._pod_to_workload[key] = workload_name
                
                # Map pod IP to workload
                if ip_address:
                    ip_str = str(ip_address)
                    # Prefer service mapping, only use workload if no service
                    if ip_str not in self._ip_to_service:
                        self._ip_to_service[ip_str] = f"{namespace}/{workload_name}"
                        
        except Exception as e:
            logger.error("Failed to load workloads", error=str(e))
    
    def _parse_ports(self, ports_raw) -> Set[int]:
        """Parse ports from JSONB field."""
        ports = set()
        
        if not ports_raw:
            return ports
            
        # Handle different formats
        if isinstance(ports_raw, str):
            import json
            try:
                ports_raw = json.loads(ports_raw)
            except:
                return ports
        
        if isinstance(ports_raw, list):
            for p in ports_raw:
                if isinstance(p, dict):
                    port = p.get("port") or p.get("target_port")
                    if port and isinstance(port, int):
                        ports.add(port)
                    elif port and isinstance(port, str) and port.isdigit():
                        ports.add(int(port))
                elif isinstance(p, int):
                    ports.add(p)
        
        return ports
    
    def _extract_workload_name(self, pod_name: str, workload_type: str) -> str:
        """
        Extract workload name from pod name.
        
        Examples:
        - backend-7b56fbb98c-26wjd -> backend
        - redis-0 -> redis
        - centos-6448f7b947-jlc88 -> centos
        """
        if workload_type in ("deployment", "statefulset", "daemonset"):
            return pod_name
        
        # For pods, try to extract the deployment name
        # Deployment pods: name-<replicaset-hash>-<pod-hash>
        # StatefulSet pods: name-<ordinal>
        
        # Try deployment pattern first (two suffixes)
        match = re.match(r'^(.+)-[a-z0-9]+-[a-z0-9]+$', pod_name)
        if match:
            return match.group(1)
        
        # Try statefulset pattern (single numeric suffix)
        match = re.match(r'^(.+)-\d+$', pod_name)
        if match:
            return match.group(1)
        
        # Fallback: return as-is
        return pod_name
    
    def is_service_port(self, namespace: str, port: int) -> bool:
        """
        Check if a port is a known service port in the given namespace.
        
        Port Classification (GLOBAL - not product-specific):
        1. port >= 32768 → Ephemeral (Linux default range)
        2. port in loaded K8s Service ports → Definitely service port
        3. port < 32768 → Likely service port (general rule)
        
        Args:
            namespace: Kubernetes namespace
            port: Port number to check
            
        Returns:
            True if this is a known service port
        """
        # Ephemeral ports (32768-65535) are NEVER service ports
        # This is based on Linux kernel defaults, not product-specific
        if port >= EPHEMERAL_PORT_START:
            return False
        
        # If we have loaded service ports from K8s, check there first
        if port in self._all_service_ports:
            return True
        
        # Fallback: any port below ephemeral range is likely a service port
        # This is a GENERAL rule that works for any product/service
        return True
    
    def get_all_service_ports(
        self, 
        namespaces: Optional[List[str]] = None
    ) -> Set[int]:
        """
        Get all known service ports.
        
        Args:
            namespaces: Optional filter by namespaces
            
        Returns:
            Set of known service port numbers
        """
        if not namespaces:
            return self._all_service_ports.copy()
        
        # Filter by namespaces
        ports = set(WELL_KNOWN_SERVICE_PORTS)
        for key, svc_ports in self._service_ports.items():
            ns = key.split("/")[0]
            if ns in namespaces:
                ports.update(svc_ports)
        
        return ports
    
    def resolve_to_workload(self, namespace: str, pod_name: str) -> str:
        """
        Resolve a pod name to its parent workload name.
        
        Args:
            namespace: Pod namespace
            pod_name: Pod name
            
        Returns:
            Workload name (deployment/statefulset name)
        """
        key = f"{namespace}/{pod_name}"
        
        if key in self._pod_to_workload:
            return self._pod_to_workload[key]
        
        # Fallback: extract from pod name
        return self._extract_workload_name(pod_name, "pod")
    
    def resolve_ip_to_service(self, ip_address: str) -> Optional[str]:
        """
        Resolve an IP address to a service or workload name.
        
        Args:
            ip_address: IP address to resolve
            
        Returns:
            "namespace/service" or "namespace/workload" or None
        """
        return self._ip_to_service.get(ip_address)
    
    def resolve_connection(
        self,
        src_namespace: str,
        src_pod: str,
        dst_namespace: str,
        dst_pod_or_ip: str,
        dst_port: int,
        protocol: str = "TCP"
    ) -> Optional[ServiceConnection]:
        """
        Resolve a raw connection to a service-level connection.
        
        This is the main entry point for converting raw TCP flows
        into meaningful service connections.
        
        Args:
            src_namespace: Source pod namespace
            src_pod: Source pod name
            dst_namespace: Destination namespace (may be empty for IPs)
            dst_pod_or_ip: Destination pod name or IP address
            dst_port: Destination port
            protocol: Protocol (TCP/UDP)
            
        Returns:
            ServiceConnection if this is a valid service connection,
            None if it should be ignored (ephemeral port, etc.)
        """
        # 1. Filter ephemeral ports
        if dst_port >= EPHEMERAL_PORT_START:
            return None
        
        # 2. Resolve source workload
        source_workload = self.resolve_to_workload(src_namespace, src_pod)
        
        # 3. Resolve destination
        dest_service = None
        dest_ns = dst_namespace
        
        # Check if dst_pod_or_ip is an IP address
        is_ip = self._is_ip_address(dst_pod_or_ip)
        
        if is_ip:
            # Try to resolve IP to service/workload
            resolved = self.resolve_ip_to_service(dst_pod_or_ip)
            if resolved:
                dest_ns, dest_service = resolved.split("/", 1)
            else:
                # External IP - use IP as service name
                dest_service = dst_pod_or_ip
                dest_ns = "external"
                
                # For external IPs, only accept ports < MAX_FALLBACK_SERVICE_PORT
                if dst_port >= MAX_FALLBACK_SERVICE_PORT:
                    return None
        else:
            # It's a pod name - resolve to workload
            dest_service = self.resolve_to_workload(dst_namespace or src_namespace, dst_pod_or_ip)
            dest_ns = dst_namespace or src_namespace
        
        # 4. Validate port is a service port
        if not self.is_service_port(dest_ns, dst_port):
            # Check if it's at least a reasonable port
            if dst_port >= MAX_FALLBACK_SERVICE_PORT:
                return None
        
        return ServiceConnection(
            source_workload=source_workload,
            source_namespace=src_namespace,
            dest_service=dest_service,
            dest_namespace=dest_ns,
            dest_port=dst_port,
            protocol=protocol
        )
    
    def _is_ip_address(self, value: str) -> bool:
        """Check if a string is an IP address."""
        if not value:
            return False
        
        # Simple check for IPv4
        parts = value.split(".")
        if len(parts) == 4:
            try:
                return all(0 <= int(p) <= 255 for p in parts)
            except ValueError:
                pass
        
        # IPv6 check
        if ":" in value:
            return True
        
        return False
    
    def get_stats(self) -> Dict:
        """Get registry statistics for debugging."""
        return {
            "service_count": len(self._service_ports),
            "total_service_ports": len(self._all_service_ports),
            "workload_mappings": len(self._pod_to_workload),
            "ip_mappings": len(self._ip_to_service),
            "loaded_scope": self._loaded_scope,
            "service_ports_sample": list(self._all_service_ports)[:20]
        }


# Singleton instance
_registry_instance: Optional[ServicePortRegistry] = None


def get_service_port_registry() -> ServicePortRegistry:
    """Get singleton instance of ServicePortRegistry."""
    global _registry_instance
    
    if _registry_instance is None:
        _registry_instance = ServicePortRegistry()
    
    return _registry_instance
