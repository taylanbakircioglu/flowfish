"""Graph Builder - Converts events to graph entities

Version: 2.1.0 - Added network_type support for CIDR-based node classification
"""

import logging
import json
import re
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


def _get_primitive_value(data: Dict, key: str, default: Any = "") -> Any:
    """
    Safely get a primitive value from dict.
    If value is a dict/list, try to extract relevant info or convert to string.
    """
    value = data.get(key, default)
    return _to_primitive(value, default)


def _to_primitive(value: Any, default: Any = "") -> Any:
    """Convert any value to a primitive type suitable for Neo4j"""
    if value is None:
        return default
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # For IP addresses that might be nested objects (trace_tcp format)
        if 'addr' in value:
            return str(value.get('addr', default))
        if 'ip' in value:
            return str(value.get('ip', default))
        if 'address' in value:
            return str(value.get('address', default))
        # For k8s pod info
        if 'name' in value and 'namespace' in value:
            return str(value.get('name', default))
        # For destination that is just an IP string in a wrapper
        if len(value) == 1 and 'dst_ip' in value:
            return _to_primitive(value['dst_ip'], default)
        # Default: return default, don't create giant JSON strings for IDs
        return default
    if isinstance(value, list):
        if len(value) > 0 and isinstance(value[0], str):
            return value[0]  # Return first item if list of strings
        return default
    return str(value)


def get_total_bytes(data: Dict, event: Dict = None) -> int:
    """
    Extract total bytes transferred from event data.
    
    Checks multiple field names for compatibility:
    - bytes_sent + bytes_received (from top_tcp gadget)
    - bytes_transferred (pre-calculated)
    - bytes (legacy)
    
    Args:
        data: The 'data' dict from event (normalized event data)
        event: The full event dict (fallback)
    
    Returns:
        Total bytes as integer (0 if not found)
    """
    if event is None:
        event = {}
    
    # Try bytes_sent + bytes_received first (top_tcp gadget format)
    bytes_sent = data.get('bytes_sent', 0) or event.get('bytes_sent', 0) or 0
    bytes_received = data.get('bytes_received', 0) or event.get('bytes_received', 0) or 0
    
    if bytes_sent or bytes_received:
        try:
            return int(bytes_sent) + int(bytes_received)
        except (ValueError, TypeError):
            pass
    
    # Try pre-calculated bytes_transferred
    bytes_transferred = data.get('bytes_transferred', 0) or event.get('bytes_transferred', 0)
    if bytes_transferred:
        try:
            return int(bytes_transferred)
        except (ValueError, TypeError):
            pass
    
    # Try legacy 'bytes' field
    bytes_val = data.get('bytes', 0) or event.get('bytes', 0)
    if bytes_val:
        try:
            return int(bytes_val)
        except (ValueError, TypeError):
            pass
    
    return 0


class GraphBuilder:
    """Builds graph entities from network events
    
    VID Format (v2.0 - Full Isolation):
    All vertex IDs include analysis_id as prefix for complete isolation between analyses.
    Format: {analysis_id}:{cluster_id}:{namespace}:{workload_name}
    
    This ensures:
    - Each analysis has its own isolated graph
    - Deleting an analysis doesn't affect other analyses
    - No orphan node accumulation issues
    """
    
    # IP addresses to filter out (not useful for dependency mapping)
    FILTERED_IPS = {
        '127.0.0.1',      # IPv4 localhost
        '::1',            # IPv6 localhost
        '0.0.0.0',        # Bind all interfaces
        '255.255.255.255', # Broadcast
    }
    
    # IP prefixes to filter (loopback, link-local)
    FILTERED_IP_PREFIXES = (
        '127.',           # Loopback range
        '169.254.',       # Link-local
    )
    
    def __init__(self):
        self.vertex_cache = {}  # Cache to avoid duplicate vertex creation
        self.edge_cache = {}    # Cache to aggregate edge updates
    
    def _make_vid(self, analysis_id: Any, cluster_id: Any, namespace: str, workload: str) -> str:
        """
        Create a vertex ID with analysis_id prefix for full isolation.
        
        Format: {analysis_id}:{cluster_id}:{namespace}:{workload}
        
        Args:
            analysis_id: Analysis identifier (required for isolation)
            cluster_id: Cluster identifier
            namespace: Kubernetes namespace
            workload: Workload/pod name
            
        Returns:
            Fully qualified vertex ID
        """
        aid = str(analysis_id) if analysis_id else '0'
        cid = str(cluster_id) if cluster_id else 'default'
        ns = str(namespace) if namespace else 'unknown'
        wl = str(workload) if workload else 'unknown'
        return f"{aid}:{cid}:{ns}:{wl}"
    
    def _classify_ip_network_type(self, ip: str) -> str:
        """
        Classify IP address into network type for visualization.
        
        IMPORTANT: This MUST be consistent with ingestion-service/pod_discovery.py!
        The CIDR ranges and labels must match exactly.
        
        This is critical for frontend to distinguish:
        - PUBLIC: Real internet IPs (External-Network) → Public filter
        - DATACENTER: Private IPs outside cluster (Internal-Network, Private-Network) → DataCenter filter
        - CLUSTER: Cluster-internal IPs (Pod-Network, Service-Network) → Neither filter
        
        Args:
            ip: IP address to classify
            
        Returns:
            Network type string matching ingestion-service classification
        """
        if not ip:
            return ''
        
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return ''
            
            parts = [int(p) for p in parts]
            if any(p < 0 or p > 255 for p in parts):
                return ''
            
            # =============================================================
            # CIDR Classification - MUST match pod_discovery.py exactly!
            # Order matters: more specific ranges checked first
            # =============================================================
            
            # --- 10.x.x.x ranges ---
            if parts[0] == 10:
                # OpenShift default pod network: 10.128.0.0/14 (10.128-10.131)
                if 128 <= parts[1] <= 131:
                    return 'Pod-Network'
                
                # Custom OpenShift cluster ranges (configure via CUSTOM_POD_CIDRS env var if needed)
                if parts[1] == 244:  # 10.244.0.0/16 - Custom pod network
                    return 'Pod-Network'
                if parts[1] == 208:  # 10.208.0.0/16 - Custom pod network
                    return 'Pod-Network'
                if parts[1] == 196:  # 10.196.0.0/16 - Custom service CIDR
                    return 'Service-Network'
                
                # Kubernetes default service network: 10.96.0.0/12 (10.96-10.111)
                if 96 <= parts[1] < 112:
                    return 'Service-Network'
                
                # Common pod network ranges
                if parts[1] == 244:  # 10.244.0.0/16 - Flannel default
                    return 'Pod-Network'
                if parts[1] == 42:   # 10.42.0.0/16 - K3s/RKE default
                    return 'Pod-Network'
                if parts[1] == 43:   # 10.43.0.0/16 - K3s service network
                    return 'Service-Network'
                
                # Everything else in 10.x.x.x is datacenter (Internal-Network)
                return 'Internal-Network'
            
            # --- 172.x.x.x ranges ---
            if parts[0] == 172:
                if 16 <= parts[1] <= 31:  # 172.16.0.0/12 (RFC 1918)
                    # OpenShift default service network: 172.30.0.0/16
                    if parts[1] == 30:
                        return 'Service-Network'
                    # Other 172.16-31.x.x is datacenter
                    return 'Private-Network'
            
            # --- 192.168.x.x range ---
            if parts[0] == 192 and parts[1] == 168:  # 192.168.0.0/16
                return 'Private-Network'
            
            # --- Reserved/Special ranges ---
            if parts[0] == 127:  # 127.0.0.0/8 - Loopback
                return 'Internal-Network'
            if parts[0] == 169 and parts[1] == 254:  # 169.254.0.0/16 - Link-local
                return 'Internal-Network'
            if parts[0] == 0:  # 0.0.0.0/8
                return 'Internal-Network'
            if parts[0] >= 224:  # 224.0.0.0+ - Multicast & Reserved
                return 'Internal-Network'
            
            # --- CGNAT range (not real public) ---
            if parts[0] == 100 and 64 <= parts[1] <= 127:  # 100.64.0.0/10
                return 'Internal-Network'
            
            # If not in any private/reserved range, it's public internet
            return 'External-Network'
            
        except (ValueError, IndexError):
            pass
        
        return ''
    
    def _should_filter_ip(self, ip: str) -> bool:
        """Check if an IP should be filtered out"""
        if not ip:
            return False
        ip = str(ip).strip()
        if ip in self.FILTERED_IPS:
            return True
        if ip.startswith(self.FILTERED_IP_PREFIXES):
            return True
        return False
    
    def _get_namespace_for_network_type(self, network_type: str) -> str:
        """
        Derive a consistent namespace based on network type.
        
        IMPORTANT: This ensures the same IP always gets the same namespace,
        preventing duplicate nodes for the same IP in different namespaces.
        
        Must be consistent with ingestion-service/pod_discovery.py!
        
        Args:
            network_type: Network type from _classify_ip_network_type()
            
        Returns:
            Namespace string for the IP
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
    
    def _extract_ip(self, ip_value) -> str:
        """Extract IP address from various formats (string, dict, etc.)"""
        if not ip_value:
            return ''
        if isinstance(ip_value, dict):
            return ip_value.get('addr', ip_value.get('ip', ''))
        return str(ip_value) if ip_value else ''
    
    def _normalize_dns_name(self, name: str) -> str:
        """
        Normalize DNS name to prevent duplicate nodes for the same host.
        
        Handles:
        - Trailing dots: 'host.domain.com.' → 'host.domain.com'
        - Cluster local suffix: 'host.domain.com.cluster.local' → 'host.domain.com'
        - Kubernetes service DNS: '10-128-1-1.svc.cluster.local' → keep as is (pod IP)
        
        Args:
            name: DNS name to normalize
            
        Returns:
            Normalized DNS name
        """
        if not name:
            return name
        
        # Remove trailing dot (FQDN format)
        name = name.rstrip('.')
        
        # Remove .cluster.local suffix for external DNS names
        # But keep it for actual K8s service DNS (contains IP pattern or 'svc')
        if name.endswith('.cluster.local'):
            # Check if this is a real K8s service DNS
            base = name[:-14]  # Remove '.cluster.local'
            # K8s service DNS looks like: service-name.namespace.svc
            # or pod DNS: 10-128-1-1.service.namespace.svc
            if '.svc' in name or self._looks_like_ip_dns(base):
                # Keep as is - it's a real K8s internal DNS
                pass
            else:
                # External DNS with .cluster.local appended (DNS search domain)
                name = base
        
        return name
    
    def _looks_like_ip_dns(self, name: str) -> bool:
        """Check if name looks like an IP-based DNS name (e.g., 10-128-1-1.service...)"""
        return bool(re.match(r'^\d+-\d+-\d+-\d+\.', name))
    
    def _is_internal_domain(self, name: str) -> bool:
        """
        Check if a DNS name belongs to internal/datacenter domains.
        
        These should be classified as DataCenter, not Public.
        
        Detection methods:
        1. Standard internal TLDs (.local, .internal, .corp, .lan, .intranet, .private, .home, .localdomain)
        2. Kubernetes internal domains (.svc.cluster.local, .pod.cluster.local)
        3. Environment variable for custom internal domains (INTERNAL_DOMAINS)
        
        NOTE: Public gTLDs like .bank, .app, .dev are NOT treated as internal.
        Use INTERNAL_DOMAINS env var for organization-specific domains.
        
        Args:
            name: DNS name to check
            
        Returns:
            True if internal domain, False otherwise
        """
        if not name:
            return False
        
        name_lower = name.lower()
        
        # Standard internal/private TLDs (RFC 6762, common enterprise patterns)
        internal_tlds = (
            '.local',              # RFC 6762 - mDNS/Bonjour
            '.internal',           # Common internal TLD
            '.corp',               # Corporate domains
            '.lan',                # LAN domains
            '.intranet',           # Intranet domains
            '.private',            # Private domains
            '.home',               # Home networks
            '.localdomain',        # Linux default
        )
        
        # Check standard internal TLDs
        for tld in internal_tlds:
            if name_lower.endswith(tld):
                return True
        
        # Kubernetes internal domains (should stay in cluster-network, not datacenter)
        # But we check these to NOT classify them as public
        if '.svc.cluster.local' in name_lower or '.pod.cluster.local' in name_lower:
            return True
        
        # Check custom internal domains from environment variable
        # Format: comma-separated list of domain suffixes
        # Example: INTERNAL_DOMAINS=".mycompany.com,.partner.org"
        custom_domains = os.environ.get('INTERNAL_DOMAINS', '')
        if custom_domains:
            for domain in custom_domains.split(','):
                domain = domain.strip().lower()
                if domain and name_lower.endswith(domain):
                    return True
        
        # NOTE: We do NOT include these TLDs as "internal":
        # - .bank - This is a PUBLIC gTLD (chase.bank, barclays.bank, etc.)
        # - .test, .example, .invalid - RFC 2606 reserved for testing/docs, not internal
        # - .localhost - RFC 6761 reserved but not a DNS domain
        #
        # If your organization uses custom internal domains, configure them via
        # the INTERNAL_DOMAINS environment variable.
        
        return False
    
    def _classify_dns_endpoint(self, name: str) -> str:
        """
        Classify a DNS endpoint for proper filtering.
        
        Returns:
            'internal-dns' for internal/datacenter domains
            'external-dns' for public internet domains
        """
        if self._is_internal_domain(name):
            return 'internal-dns'
        return 'external-dns'
    
    def process_network_flow(self, event: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """
        Process network flow event and return vertices and edges
        
        Returns:
            Tuple of (vertices, edges)
        """
        vertices = []
        edges = []
        
        try:
            # Extract analysis and cluster context
            analysis_id = event.get('analysis_id')
            cluster_id = event.get('cluster_id', 'default')
            
            # Extract source and destination from data field
            # Field names from event_transformer: namespace, pod_name, dst_namespace, dst_pod
            data = event.get('data', {})
            
            # Source: use namespace/pod_name or fallback to src_namespace/src_pod
            # Use _to_primitive to handle dict values properly
            src_namespace = _to_primitive(data.get('namespace')) or _to_primitive(data.get('src_namespace')) or 'unknown'
            src_workload = _to_primitive(data.get('pod_name')) or _to_primitive(data.get('pod')) or \
                          _to_primitive(data.get('src_pod')) or _to_primitive(data.get('src_workload')) or 'unknown'
            
            # Destination: dst_namespace/dst_pod or derive from IP
            # For dst_workload, try to get pod name first, then IP as string
            dst_pod = _to_primitive(data.get('dst_pod')) or _to_primitive(data.get('dst_workload'))
            dst_ip_raw = ''
            dst_workload = dst_pod
            is_dns_endpoint = False  # Track if destination is a DNS name (not IP or pod)
            
            if not dst_workload:
                # Try to extract IP as the destination identifier
                dst_ip_val = data.get('dst_ip', '')
                if isinstance(dst_ip_val, dict):
                    dst_workload = dst_ip_val.get('addr', dst_ip_val.get('ip', 'unknown'))
                    dst_ip_raw = dst_workload
                elif isinstance(dst_ip_val, str) and dst_ip_val:
                    dst_workload = dst_ip_val
                    dst_ip_raw = dst_ip_val
                else:
                    dst_workload = 'unknown'
            
            # Normalize DNS names to prevent duplicates
            # (handles trailing dots, .cluster.local suffix for external DNS)
            if dst_workload and not dst_pod:
                # Check if this looks like a DNS name (contains dots but not an IP)
                is_ip = bool(re.match(r'^(\d{1,3}\.){3}\d{1,3}$', dst_workload))
                if not is_ip and '.' in dst_workload:
                    is_dns_endpoint = True
                    dst_workload = self._normalize_dns_name(dst_workload)
            
            # Determine namespace based on endpoint type
            if dst_pod:
                # Resolved pod - use the provided namespace (from enrichment)
                dst_namespace = _to_primitive(data.get('dst_namespace')) or 'external'
            elif is_dns_endpoint:
                # DNS endpoint - check if internal domain (DataCenter) or external (Public)
                if self._is_internal_domain(dst_workload):
                    dst_namespace = 'datacenter'  # Internal/corporate DNS → DataCenter filter
                else:
                    dst_namespace = 'external'  # Public internet DNS → Public filter
            else:
                # Unresolved IP - derive namespace from IP classification for CONSISTENCY
                # This prevents the same IP from appearing as multiple nodes with different namespaces
                network_type = self._classify_ip_network_type(dst_ip_raw or dst_workload)
                if network_type:
                    dst_namespace = self._get_namespace_for_network_type(network_type)
                else:
                    dst_namespace = _to_primitive(data.get('dst_namespace')) or 'external'
            
            # Filter out localhost/loopback traffic if enabled (default: disabled, frontend handles it)
            if settings.filter_localhost:
                if self._should_filter_ip(dst_ip_raw) or self._should_filter_ip(dst_workload):
                    logger.debug(f"Filtering localhost traffic to {dst_workload}")
                    return vertices, []
                
                # Also filter if source is localhost (internal pod traffic)
                src_ip_check = _to_primitive(data.get('src_ip', ''))
                if self._should_filter_ip(src_ip_check):
                    logger.debug(f"Filtering localhost traffic from {src_ip_check}")
                    return vertices, []
            
            # Ensure all are strings
            src_namespace = str(src_namespace) if src_namespace else 'unknown'
            src_workload = str(src_workload) if src_workload else 'unknown'
            dst_namespace = str(dst_namespace) if dst_namespace else 'external'
            dst_workload = str(dst_workload) if dst_workload else 'unknown'
            
            # Create source vertex ID with analysis_id prefix for isolation
            src_vid = self._make_vid(analysis_id, cluster_id, src_namespace, src_workload)
            
            # Create source vertex (if not cached)
            if src_vid not in self.vertex_cache:
                # Extract source IP properly
                src_ip_raw = data.get('src_ip', '')
                if isinstance(src_ip_raw, dict):
                    src_ip = src_ip_raw.get('addr', src_ip_raw.get('ip', ''))
                else:
                    src_ip = str(src_ip_raw) if src_ip_raw else ''
                
                # Get labels from event (enriched by pod discovery)
                src_labels = data.get('labels', {})
                if isinstance(src_labels, dict):
                    src_labels_str = json.dumps(src_labels)
                else:
                    src_labels_str = '{}'
                
                vertices.append({
                    'vid': src_vid,
                    'tag': 'Pod',
                    'labels': ['Workload'],
                    'properties': {
                        'name': src_workload,
                        'namespace': src_namespace,
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': src_ip,
                        'node': _to_primitive(data.get('src_node', '')) or _to_primitive(data.get('node', '')),
                        'labels': src_labels_str,
                        'owner_kind': _to_primitive(data.get('owner_kind', '')) or _to_primitive(data.get('src_owner_kind', '')),
                        'owner_name': _to_primitive(data.get('owner_name', '')) or _to_primitive(data.get('src_owner_name', '')),
                        # Extended metadata
                        'pod_uid': _to_primitive(data.get('src_pod_uid', '')),
                        'host_ip': _to_primitive(data.get('src_host_ip', '')),
                        'container': _to_primitive(data.get('src_container', '')) or _to_primitive(data.get('container', '')),
                        'image': _to_primitive(data.get('src_image', '')),
                        'service_account': _to_primitive(data.get('src_service_account', '')),
                        'phase': _to_primitive(data.get('src_phase', '')),
                        'created_at': int(datetime.utcnow().timestamp()),
                        'status': 'running',
                        'is_active': True
                    }
                })
                self.vertex_cache[src_vid] = True
            
            # Create destination vertex ID with analysis_id prefix for isolation
            dst_vid = self._make_vid(analysis_id, cluster_id, dst_namespace, dst_workload)
            
            # Create destination vertex (if not cached)
            if dst_vid not in self.vertex_cache:
                # Extract destination IP properly
                dst_ip_raw = data.get('dst_ip', '')
                if isinstance(dst_ip_raw, dict):
                    dst_ip = dst_ip_raw.get('addr', dst_ip_raw.get('ip', ''))
                else:
                    dst_ip = str(dst_ip_raw) if dst_ip_raw else ''
                
                # Determine if this is an external endpoint
                is_external = dst_namespace == 'external'
                
                # Get destination labels from event (enriched by pod discovery)
                dst_labels = data.get('dst_labels', {})
                if isinstance(dst_labels, dict):
                    dst_labels_str = json.dumps(dst_labels)
                else:
                    dst_labels_str = '{}'
                
                # Get network_type for grouping in visualization
                # This enables "Internal-Network", "External-Network" etc. as categories
                # while keeping each destination IP as a unique node
                dst_network_type = _to_primitive(data.get('dst_network_type', ''))
                dst_resolution_source = _to_primitive(data.get('dst_resolution_source', ''))
                
                vertices.append({
                    'vid': dst_vid,
                    'tag': 'ExternalEndpoint' if is_external else 'Pod',
                    'labels': ['ExternalEndpoint'] if is_external else ['Workload'],
                    'properties': {
                        'name': dst_workload,
                        'namespace': dst_namespace,
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': dst_ip or dst_workload,  # Use workload as IP if it's an IP address
                        'node': _to_primitive(data.get('dst_node', '')),
                        'labels': dst_labels_str,
                        'owner_kind': _to_primitive(data.get('dst_owner_kind', '')),
                        'owner_name': _to_primitive(data.get('dst_owner_name', '')),
                        # Extended metadata
                        'pod_uid': _to_primitive(data.get('dst_pod_uid', '')),
                        'host_ip': _to_primitive(data.get('dst_host_ip', '')),
                        'container': _to_primitive(data.get('dst_container', '')),
                        'image': _to_primitive(data.get('dst_image', '')),
                        'service_account': _to_primitive(data.get('dst_service_account', '')),
                        'phase': _to_primitive(data.get('dst_phase', '')),
                        'created_at': int(datetime.utcnow().timestamp()),
                        'status': 'running',
                        'is_active': True,
                        'is_external': is_external,
                        # Network type for visualization grouping
                        # Enables frontend to show "Internal-Network" category while 
                        # maintaining unique destination nodes per IP
                        'network_type': dst_network_type,
                        'resolution_source': dst_resolution_source
                    }
                })
                self.vertex_cache[dst_vid] = True
            
            # Create edge
            edge_key = f"{src_vid}->{dst_vid}"
            
            # Extract port as primitive (might be nested in some event formats)
            dst_port = _get_primitive_value(data, 'dst_port', 0) or _get_primitive_value(event, 'dst_port', 0)
            if isinstance(dst_port, str) and dst_port.isdigit():
                dst_port = int(dst_port)
            elif not isinstance(dst_port, int):
                dst_port = 0
            
            # Calculate total bytes from bytes_sent + bytes_received (or fallback to bytes field)
            def get_total_bytes(d, e):
                # Try bytes_sent + bytes_received first (from ingestion service)
                bytes_sent = _get_primitive_value(d, 'bytes_sent', 0) or _get_primitive_value(e, 'bytes_sent', 0) or 0
                bytes_recv = _get_primitive_value(d, 'bytes_received', 0) or _get_primitive_value(e, 'bytes_received', 0) or 0
                if bytes_sent or bytes_recv:
                    return int(bytes_sent) + int(bytes_recv)
                # Fallback to bytes field
                bytes_val = _get_primitive_value(d, 'bytes', 0) or _get_primitive_value(e, 'bytes', 0)
                return int(bytes_val) if isinstance(bytes_val, (int, float)) else 0
            
            # Extract error metrics
            error_count = int(data.get('error_count', 0) or event.get('error_count', 0) or 0)
            retransmit_count = int(data.get('retransmit_count', 0) or data.get('retransmits', 0) or event.get('retransmit_count', 0) or 0)
            error_type = data.get('error_type', '') or event.get('error_type', '') or ''
            
            # Aggregate edge properties
            if edge_key in self.edge_cache:
                # Update existing edge
                self.edge_cache[edge_key]['properties']['request_count'] += 1
                self.edge_cache[edge_key]['properties']['last_seen'] = int(datetime.utcnow().timestamp())
                self.edge_cache[edge_key]['properties']['bytes_transferred'] += get_total_bytes(data, event)
                # Aggregate error metrics
                self.edge_cache[edge_key]['properties']['error_count'] = self.edge_cache[edge_key]['properties'].get('error_count', 0) + error_count
                self.edge_cache[edge_key]['properties']['retransmit_count'] = self.edge_cache[edge_key]['properties'].get('retransmit_count', 0) + retransmit_count
                # Keep track of last error type if there was an error
                if error_type:
                    self.edge_cache[edge_key]['properties']['last_error_type'] = error_type
                
                # CRITICAL: Update IP fields if available and not already set
                # This ensures IP is captured even if first event didn't have it
                new_dst_ip = self._extract_ip(data.get('dst_ip', ''))
                if new_dst_ip and not self.edge_cache[edge_key].get('dst_ip'):
                    self.edge_cache[edge_key]['dst_ip'] = new_dst_ip
                new_src_ip = self._extract_ip(data.get('src_ip', ''))
                if new_src_ip and not self.edge_cache[edge_key].get('src_ip'):
                    self.edge_cache[edge_key]['src_ip'] = new_src_ip
            else:
                # New edge - use protocol from gadget event directly
                protocol_val = _get_primitive_value(data, 'protocol', 'TCP') or _get_primitive_value(event, 'protocol', 'TCP')
                # L7 application protocol (GRPC, HTTP, etc.) - enriched by trace_manager
                app_protocol_val = _get_primitive_value(data, 'app_protocol', '') or _get_primitive_value(event, 'app_protocol', '')
                bytes_val = get_total_bytes(data, event)
                latency_val = _get_primitive_value(data, 'latency_ms', 0.0) or _get_primitive_value(event, 'latency_ms', 0.0)
                risk_val = _get_primitive_value(data, 'risk_score', 0) or _get_primitive_value(event, 'risk_score', 0)
                
                # Get labels as JSON strings for edge cache
                src_labels_for_edge = data.get('labels', {})
                if isinstance(src_labels_for_edge, dict):
                    src_labels_for_edge = json.dumps(src_labels_for_edge)
                elif not isinstance(src_labels_for_edge, str):
                    src_labels_for_edge = '{}'
                    
                dst_labels_for_edge = data.get('dst_labels', {})
                if isinstance(dst_labels_for_edge, dict):
                    dst_labels_for_edge = json.dumps(dst_labels_for_edge)
                elif not isinstance(dst_labels_for_edge, str):
                    dst_labels_for_edge = '{}'
                
                self.edge_cache[edge_key] = {
                    'src_vid': src_vid,
                    'dst_vid': dst_vid,
                    'edge_type': 'COMMUNICATES_WITH',
                    # Include node metadata for upsert_edge to set on nodes
                    # Labels (JSON strings)
                    'src_labels': src_labels_for_edge,
                    'dst_labels': dst_labels_for_edge,
                    # Owner info
                    'src_owner_kind': _to_primitive(data.get('owner_kind', '')) or _to_primitive(data.get('src_owner_kind', '')),
                    'src_owner_name': _to_primitive(data.get('owner_name', '')) or _to_primitive(data.get('src_owner_name', '')),
                    'dst_owner_kind': _to_primitive(data.get('dst_owner_kind', '')),
                    'dst_owner_name': _to_primitive(data.get('dst_owner_name', '')),
                    # Extended metadata - source
                    'src_pod_uid': _to_primitive(data.get('src_pod_uid', '')),
                    'src_ip': self._extract_ip(data.get('src_ip', '')),  # Pod IP address
                    'src_host_ip': _to_primitive(data.get('src_host_ip', '')),
                    'src_container': _to_primitive(data.get('src_container', '')) or _to_primitive(data.get('container', '')),
                    'src_image': _to_primitive(data.get('src_image', '')),
                    'src_service_account': _to_primitive(data.get('src_service_account', '')),
                    'src_phase': _to_primitive(data.get('src_phase', '')),
                    # Extended metadata - destination
                    'dst_pod_uid': _to_primitive(data.get('dst_pod_uid', '')),
                    'dst_ip': self._extract_ip(data.get('dst_ip', '')),  # Pod IP address
                    'dst_host_ip': _to_primitive(data.get('dst_host_ip', '')),
                    'dst_container': _to_primitive(data.get('dst_container', '')),
                    'dst_image': _to_primitive(data.get('dst_image', '')),
                    'dst_service_account': _to_primitive(data.get('dst_service_account', '')),
                    'dst_phase': _to_primitive(data.get('dst_phase', '')),
                    'properties': {
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'cluster_id': str(cluster_id),
                        'port': dst_port,
                        'protocol': str(protocol_val),
                        'app_protocol': str(app_protocol_val) if app_protocol_val else str(protocol_val),  # L7 protocol (GRPC, HTTP, etc.)
                        'destination_port': dst_port,
                        'first_seen': int(datetime.utcnow().timestamp()),
                        'last_seen': int(datetime.utcnow().timestamp()),
                        'request_count': 1,
                        'bytes_transferred': int(bytes_val) if isinstance(bytes_val, (int, float)) else 0,
                        'avg_latency_ms': float(latency_val) if isinstance(latency_val, (int, float)) else 0.0,
                        'risk_score': int(risk_val) if isinstance(risk_val, (int, float)) else 0,
                        # Error metrics
                        'error_count': error_count,
                        'retransmit_count': retransmit_count,
                        'last_error_type': str(error_type) if error_type else '',
                        'is_active': True
                    }
                }
            
        except Exception as e:
            logger.error(f"Failed to process network flow: {e}")
        
        return vertices, []
    
    def flush_edges(self) -> List[Dict]:
        """Flush cached edges for batch insert"""
        edges = list(self.edge_cache.values())
        self.edge_cache = {}
        return edges
    
    def process_dns_query(self, event: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """
        Process DNS query event to identify external dependencies.
        Creates edges from pods to external DNS names.
        """
        vertices = []
        
        try:
            analysis_id = event.get('analysis_id')
            cluster_id = event.get('cluster_id', 'default')
            data = event.get('data', {})
            
            # Source: the pod making the DNS query
            src_namespace = data.get('namespace') or 'unknown'
            src_pod = data.get('pod_name') or data.get('pod') or 'unknown'
            query_name = data.get('query_name') or data.get('name') or ''
            
            # Skip internal Kubernetes DNS queries
            if not query_name or query_name.endswith('.svc.cluster.local') or query_name.endswith('.pod.cluster.local'):
                return vertices, []
            
            # Source vertex with analysis_id prefix for isolation
            src_vid = self._make_vid(analysis_id, cluster_id, src_namespace, src_pod)
            src_ip = data.get('src_ip') or data.get('pod_ip') or ''
            if src_vid not in self.vertex_cache:
                vertices.append({
                    'vid': src_vid,
                    'tag': 'Pod',
                    'labels': ['Workload'],
                    'properties': {
                        'name': str(src_pod),
                        'namespace': str(src_namespace),
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(src_ip) if src_ip else '',  # Pod IP
                        'created_at': int(datetime.utcnow().timestamp()),
                        'status': 'running',
                        'is_active': True
                    }
                })
                self.vertex_cache[src_vid] = True
            
            # Destination: external DNS name with analysis_id prefix
            dst_vid = self._make_vid(analysis_id, cluster_id, 'external', query_name)
            # Get resolved IP if available (from DNS response)
            # 
            # CRITICAL: DO NOT use dst_ip for DNS events!
            # In DNS query events, dst_ip = DNS Server IP (e.g., 172.30.0.10 for CoreDNS)
            # The actual resolved destination IPs are in response_ips/answers fields!
            #
            # Field priority: response_ips > answers > resolved_ip > answer
            # NOTE: response_ips contains the actual resolved IPs from DNS response,
            # NOT the DNS server IP. DNS server IP is in dst_ip which we intentionally ignore.
            resolved_ip = ''
            response_ips = data.get('response_ips') or data.get('answers') or []
            if isinstance(response_ips, list) and len(response_ips) > 0:
                # Take first resolved IP from DNS response
                resolved_ip = str(response_ips[0]) if response_ips[0] else ''
            else:
                resolved_ip = data.get('resolved_ip') or data.get('answer') or ''
            if dst_vid not in self.vertex_cache:
                # Determine network_type based on resolved IP
                # This is critical for frontend to distinguish PUBLIC vs DATACENTER
                network_type = ''
                if resolved_ip:
                    network_type = self._classify_ip_network_type(resolved_ip)
                
                vertices.append({
                    'vid': dst_vid,
                    'tag': 'ExternalEndpoint',
                    'labels': ['ExternalEndpoint', 'DNS'],
                    'properties': {
                        'name': str(query_name),
                        'namespace': 'external',
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(resolved_ip) if resolved_ip else '',  # IP from DNS resolution
                        'dns_name': str(query_name),
                        'network_type': network_type,  # For PUBLIC vs DATACENTER classification
                        'resolution_source': 'dns',
                        'created_at': int(datetime.utcnow().timestamp()),
                        'is_external': True,
                        'is_active': True
                    }
                })
                self.vertex_cache[dst_vid] = True
            
            # Create edge for DNS query
            edge_key = f"{src_vid}->DNS->{dst_vid}"
            if edge_key not in self.edge_cache:
                self.edge_cache[edge_key] = {
                    'src_vid': src_vid,
                    'dst_vid': dst_vid,
                    'edge_type': 'QUERIES_DNS',
                    'properties': {
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'cluster_id': str(cluster_id),
                        'query_type': str(data.get('query_type', 'A')),
                        'first_seen': int(datetime.utcnow().timestamp()),
                        'last_seen': int(datetime.utcnow().timestamp()),
                        'request_count': 1,
                        'is_active': True
                    }
                }
            else:
                self.edge_cache[edge_key]['properties']['request_count'] += 1
                self.edge_cache[edge_key]['properties']['last_seen'] = int(datetime.utcnow().timestamp())
                
        except Exception as e:
            logger.error(f"Failed to process DNS query: {e}")
        
        return vertices, []
    
    def process_tcp_connection(self, event: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """Process TCP connection event"""
        # Similar to network flow
        return self.process_network_flow(event)
    
    def process_bind_event(self, event: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """
        Process bind event - shows which pods are listening on which ports.
        Creates edges showing service endpoints.
        """
        vertices = []
        
        try:
            analysis_id = event.get('analysis_id')
            cluster_id = event.get('cluster_id', 'default')
            data = event.get('data', {})
            
            namespace = data.get('namespace') or 'unknown'
            pod_name = data.get('pod_name') or data.get('pod') or data.get('comm') or 'unknown'
            bind_addr = data.get('bind_addr') or data.get('addr') or '0.0.0.0'
            bind_port = data.get('bind_port') or data.get('port') or 0
            protocol = data.get('protocol') or 'TCP'
            
            # Source: the pod listening with analysis_id prefix
            src_vid = self._make_vid(analysis_id, cluster_id, namespace, pod_name)
            src_ip = data.get('src_ip') or data.get('pod_ip') or ''
            if src_vid not in self.vertex_cache:
                vertices.append({
                    'vid': src_vid,
                    'tag': 'Pod',
                    'labels': ['Workload', 'Service'],
                    'properties': {
                        'name': str(pod_name),
                        'namespace': str(namespace),
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(src_ip) if src_ip else '',  # Pod IP
                        'created_at': int(datetime.utcnow().timestamp()),
                        'status': 'running',
                        'is_active': True
                    }
                })
                self.vertex_cache[src_vid] = True
            
            # Create ServiceEndpoint vertex with analysis_id prefix
            endpoint_vid = self._make_vid(analysis_id, cluster_id, namespace, f"{bind_addr}:{bind_port}")
            if endpoint_vid not in self.vertex_cache:
                vertices.append({
                    'vid': endpoint_vid,
                    'tag': 'ServiceEndpoint',
                    'labels': ['ServiceEndpoint'],
                    'properties': {
                        'name': f"{bind_addr}:{bind_port}",
                        'namespace': str(namespace),
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(bind_addr) if bind_addr and bind_addr != '0.0.0.0' else '',  # Bind IP
                        'bind_addr': str(bind_addr),
                        'bind_port': int(bind_port),
                        'protocol': str(protocol),
                        'created_at': int(datetime.utcnow().timestamp()),
                        'is_active': True
                    }
                })
                self.vertex_cache[endpoint_vid] = True
            
            # Create LISTENS_ON edge
            edge_key = f"{src_vid}->LISTENS->{endpoint_vid}"
            if edge_key not in self.edge_cache:
                self.edge_cache[edge_key] = {
                    'src_vid': src_vid,
                    'dst_vid': endpoint_vid,
                    'edge_type': 'LISTENS_ON',
                    'properties': {
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'cluster_id': str(cluster_id),
                        'port': int(bind_port),
                        'protocol': str(protocol),
                        'first_seen': int(datetime.utcnow().timestamp()),
                        'last_seen': int(datetime.utcnow().timestamp()),
                        'is_active': True
                    }
                }
            else:
                self.edge_cache[edge_key]['properties']['last_seen'] = int(datetime.utcnow().timestamp())
                
        except Exception as e:
            logger.error(f"Failed to process bind event: {e}")
        
        return vertices, []
    
    def process_sni_event(self, event: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """
        Process SNI event - shows TLS connections to external services.
        Creates edges from pods to external TLS endpoints.
        """
        vertices = []
        
        try:
            analysis_id = event.get('analysis_id')
            cluster_id = event.get('cluster_id', 'default')
            data = event.get('data', {})
            
            namespace = data.get('namespace') or 'unknown'
            pod_name = data.get('pod_name') or data.get('pod') or data.get('comm') or 'unknown'
            sni_name = data.get('sni_name') or data.get('name') or data.get('server_name') or ''
            dst_ip = data.get('dst_ip') or data.get('dest_ip') or ''
            dst_port = data.get('dst_port') or data.get('dest_port') or 443
            
            if not sni_name:
                return vertices, []
            
            # Source: the pod making TLS connection with analysis_id prefix
            src_vid = self._make_vid(analysis_id, cluster_id, namespace, pod_name)
            src_ip = data.get('src_ip') or data.get('pod_ip') or ''
            if src_vid not in self.vertex_cache:
                vertices.append({
                    'vid': src_vid,
                    'tag': 'Pod',
                    'labels': ['Workload'],
                    'properties': {
                        'name': str(pod_name),
                        'namespace': str(namespace),
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(src_ip) if src_ip else '',  # Pod IP
                        'created_at': int(datetime.utcnow().timestamp()),
                        'status': 'running',
                        'is_active': True
                    }
                })
                self.vertex_cache[src_vid] = True
            
            # Destination: external TLS endpoint with analysis_id prefix
            dst_vid = self._make_vid(analysis_id, cluster_id, 'external', sni_name)
            if dst_vid not in self.vertex_cache:
                vertices.append({
                    'vid': dst_vid,
                    'tag': 'ExternalEndpoint',
                    'labels': ['ExternalEndpoint', 'TLS'],
                    'properties': {
                        'name': str(sni_name),
                        'namespace': 'external',
                        'cluster_id': str(cluster_id),
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'ip': str(dst_ip) if dst_ip else '',  # Destination IP for Public filter
                        'sni_name': str(sni_name),
                        'dst_port': int(dst_port),
                        'created_at': int(datetime.utcnow().timestamp()),
                        'is_external': True,
                        'is_active': True
                    }
                })
                self.vertex_cache[dst_vid] = True
            
            # Create TLS_CONNECTS edge
            edge_key = f"{src_vid}->TLS->{dst_vid}"
            if edge_key not in self.edge_cache:
                self.edge_cache[edge_key] = {
                    'src_vid': src_vid,
                    'dst_vid': dst_vid,
                    'edge_type': 'TLS_CONNECTS',
                    'properties': {
                        'analysis_id': str(analysis_id) if analysis_id else '',
                        'cluster_id': str(cluster_id),
                        'sni_name': str(sni_name),
                        'dst_ip': str(dst_ip),
                        'port': int(dst_port),
                        'first_seen': int(datetime.utcnow().timestamp()),
                        'last_seen': int(datetime.utcnow().timestamp()),
                        'request_count': 1,
                        'is_active': True
                    }
                }
            else:
                self.edge_cache[edge_key]['properties']['request_count'] += 1
                self.edge_cache[edge_key]['properties']['last_seen'] = int(datetime.utcnow().timestamp())
                
        except Exception as e:
            logger.error(f"Failed to process SNI event: {e}")
        
        return vertices, []
    
    def process_workload_discovery(self, workload: Dict[str, Any]) -> List[Dict]:
        """Process discovered Kubernetes workload"""
        vertices = []
        
        try:
            workload_type = workload.get('type', 'Pod')
            name = workload.get('name', '')
            namespace = workload.get('namespace', '')
            cluster_id = workload.get('cluster_id', 'default')
            analysis_id = workload.get('analysis_id', '0')
            
            # Use new VID format with analysis_id prefix for full isolation
            vid = self._make_vid(analysis_id, cluster_id, namespace, name)
            
            vertex = {
                'vid': vid,
                'tag': workload_type,
                'properties': {
                    'name': name,
                    'namespace': namespace,
                    'cluster_id': str(cluster_id),
                    'analysis_id': str(analysis_id),
                    'labels': json.dumps(workload.get('labels', {})),
                    'created_at': int(datetime.utcnow().timestamp())
                }
            }
            
            # Add type-specific properties
            if workload_type == 'Deployment':
                vertex['properties']['replicas'] = workload.get('replicas', 1)
            elif workload_type == 'Service':
                vertex['properties']['service_type'] = workload.get('service_type', 'ClusterIP')
                vertex['properties']['cluster_ip'] = workload.get('cluster_ip', '')
                vertex['properties']['ports'] = json.dumps(workload.get('ports', []))
            
            vertices.append(vertex)
            
        except Exception as e:
            logger.error(f"Failed to process workload discovery: {e}")
        
        return vertices

