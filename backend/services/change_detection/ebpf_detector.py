"""
eBPF Event Detector Module - Service-Level Change Detection

Detects behavioral changes by analyzing eBPF events stored in ClickHouse.
Uses ServicePortRegistry to filter ephemeral ports and track service-level connections.

Architecture:
- Uses ChangeDetectionRepository for all database queries (no direct DB access)
- Uses ServicePortRegistry to identify valid service ports
- Aggregates connections at service level (not raw TCP flows)
- Repository provides data abstraction
- Detector focuses on business logic (comparison, anomaly detection)

Detects:
- CONNECTION_ADDED: New service connection appeared (not in baseline)
- CONNECTION_REMOVED: Service connection disappeared (was in baseline)
- PORT_CHANGED: Same source/dest service but different port
- TRAFFIC_ANOMALY: Unusual traffic volume or latency
- DNS_ANOMALY: New domains, NXDOMAIN errors
- PROCESS_ANOMALY: New/suspicious process executions
- ERROR_ANOMALY: Connection errors, retransmits

Port Filtering:
- Uses ServicePortRegistry to get known service ports from K8s
- Filters out ephemeral ports (32768-65535) automatically
- Falls back to heuristics for external connections
"""

from typing import List, Dict, Any, Optional, Set, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import structlog

from .base_detector import BaseDetector, Change, ChangeSource, RiskLevel
from .strategies import (
    DetectionStrategy,
    ConnectionKey,
    ConnectionDiff,
    ServiceConnectionKey,
    ServiceConnectionDiff,
    get_strategy
)

if TYPE_CHECKING:
    from .service_port_registry import ServicePortRegistry

logger = structlog.get_logger(__name__)


# Ephemeral port range - ports in this range are NEVER service ports
EPHEMERAL_PORT_START = 32768


@dataclass(frozen=True)
class ConnectionWithDirection:
    """
    Connection with direction awareness (hashable for set operations).
    
    LEGACY: Used for raw TCP flow tracking.
    For service-level tracking, use ServiceConnectionKey instead.
    """
    source_pod: str
    source_namespace: str
    dest_pod: str
    dest_namespace: str
    dest_port: int
    protocol: str
    direction: str
    
    def __hash__(self):
        return hash((
            self.source_pod, self.dest_pod, self.dest_port, 
            self.protocol, self.direction
        ))


class eBPFDetector(BaseDetector):
    """
    Service-level eBPF event-based change detector.
    
    Key improvements over raw TCP flow tracking:
    - Uses ServicePortRegistry to identify valid service ports
    - Aggregates connections at workload level (not pod level)
    - Filters out ephemeral port noise
    - Tracks service-to-service relationships
    
    Analyzes data from ClickHouse through ChangeDetectionRepository:
    - network_flows: Connection and traffic anomalies
    - dns_queries: DNS anomalies
    - process_events: Process anomalies
    
    Changes detected are trustworthy and immediately valid.
    """
    
    # Thresholds for anomaly detection
    TRAFFIC_SPIKE_MULTIPLIER = 3.0  # 3x baseline = anomaly
    LATENCY_SPIKE_MULTIPLIER = 2.5  # 2.5x baseline = anomaly
    MIN_BASELINE_SAMPLES = 5  # Minimum samples for baseline
    
    # Suspicious commands to flag
    SUSPICIOUS_COMMANDS = {
        'nc', 'ncat', 'netcat',  # Network utilities
        'curl', 'wget',  # Data exfiltration potential
        'nmap', 'masscan',  # Network scanning
        'python', 'perl', 'ruby',  # Scripting (unusual in containers)
        'bash', 'sh', 'ash',  # Shell access
        'ssh', 'sshd',  # Remote access
        'base64', 'xxd',  # Encoding tools
        'chmod', 'chown',  # Permission changes
    }
    
    def __init__(self):
        super().__init__()
        self.source = ChangeSource.EBPF_EVENTS
        self._repository = None
        self._service_registry: Optional['ServicePortRegistry'] = None
    
    @property
    def repository(self):
        """Lazy-load repository through factory function"""
        if self._repository is None:
            from repositories.change_detection_repository import get_change_detection_repository
            self._repository = get_change_detection_repository()
        return self._repository
    
    @property
    def service_registry(self) -> Optional['ServicePortRegistry']:
        """Get the service port registry"""
        return self._service_registry
    
    def set_service_registry(self, registry: 'ServicePortRegistry') -> None:
        """
        Set the ServicePortRegistry for intelligent port filtering.
        
        When set, the detector will:
        1. Use known service ports from the registry
        2. Aggregate connections at workload level
        3. Filter out ephemeral port noise
        
        Args:
            registry: ServicePortRegistry instance with loaded service data
        """
        self._service_registry = registry
        logger.debug("ServicePortRegistry set for eBPF detector")
    
    async def detect(
        self,
        cluster_id: int,
        analysis_id: str,
        strategy: str = 'baseline',
        run_id: Optional[int] = None,
        run_number: Optional[int] = None,
        enabled_types: Optional[List[str]] = None,
        analysis_start: Optional[datetime] = None,
        namespace_scope: Optional[List[str]] = None,
        **kwargs
    ) -> List[Change]:
        """
        Detect behavioral changes from eBPF events.
        
        Uses ServicePortRegistry (if set) for intelligent port filtering:
        - Only tracks connections to known service ports
        - Aggregates connections at workload level
        - Filters out ephemeral port noise
        
        Args:
            cluster_id: The cluster to analyze
            analysis_id: The analysis ID for filtering events
            strategy: Detection strategy (baseline, rolling_window, run_comparison)
            run_id: Optional run ID for run-based tracking
            run_number: Optional run number
            enabled_types: List of enabled change types
            analysis_start: When the analysis started (for baseline calculation)
            namespace_scope: Optional list of namespaces to limit detection to
            
        Returns:
            List of detected Change objects
        """
        changes: List[Change] = []
        enabled = enabled_types or ['all']
        
        # Store namespace scope for use in detection methods
        self._current_namespace_scope = namespace_scope
        
        try:
            # Get detection strategy
            detection_strategy = get_strategy(strategy)
            
            # Default analysis start to 1 hour ago if not provided
            if analysis_start is None:
                analysis_start = datetime.now(timezone.utc) - timedelta(hours=1)
            # Ensure analysis_start is timezone-aware
            elif analysis_start.tzinfo is None:
                analysis_start = analysis_start.replace(tzinfo=timezone.utc)
            
            # Get time windows from strategy
            (baseline_start, baseline_end), (current_start, current_end) = \
                detection_strategy.get_time_windows(analysis_start)
            
            # Get known service ports from registry (if available)
            service_ports = None
            if self._service_registry:
                service_ports = self._service_registry.get_all_service_ports(namespace_scope)
                logger.debug(
                    "Using ServicePortRegistry for port filtering",
                    port_count=len(service_ports),
                    sample_ports=list(service_ports)[:10]
                )
            
            # ==========================================
            # 1. CONNECTION CHANGES (service-level)
            # ==========================================
            if 'all' in enabled or 'connection_added' in enabled or 'connection_removed' in enabled:
                conn_changes = await self._detect_connection_changes(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    enabled_types=enabled,
                    namespace_scope=namespace_scope,
                    service_ports=service_ports
                )
                changes.extend(conn_changes)
            
            # ==========================================
            # 2. PORT CHANGES (service ports only)
            # ==========================================
            if 'all' in enabled or 'port_changed' in enabled:
                port_changes = await self._detect_port_changes(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    namespace_scope=namespace_scope,
                    service_ports=service_ports
                )
                changes.extend(port_changes)
            
            # ==========================================
            # 3. TRAFFIC ANOMALIES (volume, latency)
            # ==========================================
            if 'all' in enabled or 'traffic_anomaly' in enabled:
                traffic_changes = await self._detect_traffic_anomalies(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    namespace_scope=namespace_scope
                )
                changes.extend(traffic_changes)
            
            # ==========================================
            # 4. DNS ANOMALIES
            # ==========================================
            if 'all' in enabled or 'dns_anomaly' in enabled:
                dns_changes = await self._detect_dns_anomalies(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    namespace_scope=namespace_scope
                )
                changes.extend(dns_changes)
            
            # ==========================================
            # 5. PROCESS ANOMALIES
            # ==========================================
            if 'all' in enabled or 'process_anomaly' in enabled:
                process_changes = await self._detect_process_anomalies(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    namespace_scope=namespace_scope
                )
                changes.extend(process_changes)
            
            # ==========================================
            # 6. ERROR ANOMALIES
            # ==========================================
            if 'all' in enabled or 'error_anomaly' in enabled:
                error_changes = await self._detect_error_anomalies(
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    baseline_window=(baseline_start, baseline_end),
                    current_window=(current_start, current_end),
                    run_id=run_id,
                    run_number=run_number,
                    namespace_scope=namespace_scope
                )
                changes.extend(error_changes)
            
            logger.info(
                "eBPF detection completed",
                analysis_id=analysis_id,
                strategy=strategy,
                total_changes=len(changes),
                connection_added=len([c for c in changes if c.change_type == 'connection_added']),
                connection_removed=len([c for c in changes if c.change_type == 'connection_removed']),
                traffic_anomaly=len([c for c in changes if c.change_type == 'traffic_anomaly']),
                dns_anomaly=len([c for c in changes if c.change_type == 'dns_anomaly']),
                process_anomaly=len([c for c in changes if c.change_type == 'process_anomaly']),
                error_anomaly=len([c for c in changes if c.change_type == 'error_anomaly'])
            )
            
        except Exception as e:
            logger.error("eBPF detection failed", analysis_id=analysis_id, error=str(e))
        
        return changes
    
    # ==========================================
    # CONNECTION DETECTION (Service-Level)
    # ==========================================
    
    async def _detect_connection_changes(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        enabled_types: List[str],
        namespace_scope: Optional[List[str]] = None,
        service_ports: Optional[Set[int]] = None
    ) -> List[Change]:
        """
        Detect connection additions and removals at service level.
        
        Uses ServicePortRegistry (via service_ports) for intelligent filtering:
        - Only tracks connections to known service ports
        - Aggregates connections at workload level (not pod level)
        - Filters out ephemeral port noise
        
        Args:
            service_ports: Set of known service ports from ServicePortRegistry.
                          If provided, only connections to these ports are tracked.
        """
        changes: List[Change] = []
        
        try:
            # Query through repository with service port filtering
            baseline_records = await self.repository.get_connections(
                analysis_id, baseline_window[0], baseline_window[1], 
                namespace_scope, service_ports
            )
            current_records = await self.repository.get_connections(
                analysis_id, current_window[0], current_window[1], 
                namespace_scope, service_ports
            )
            
            # Aggregate to service level if registry is available
            if self._service_registry:
                baseline_set = self._aggregate_to_service_connections(baseline_records)
                current_set = self._aggregate_to_service_connections(current_records)
            else:
                # Fallback: use raw connections with port filtering
                baseline_set = {
                    ConnectionWithDirection(
                        r.source_pod, r.source_namespace, r.dest_pod, 
                        r.dest_namespace, r.dest_port, r.protocol, r.direction
                    )
                    for r in baseline_records
                    if self._is_service_port(r.dest_port)
                }
                current_set = {
                    ConnectionWithDirection(
                        r.source_pod, r.source_namespace, r.dest_pod, 
                        r.dest_namespace, r.dest_port, r.protocol, r.direction
                    )
                    for r in current_records
                    if self._is_service_port(r.dest_port)
                }
            
            added = current_set - baseline_set
            removed = baseline_set - current_set
            
            logger.debug(
                "Connection comparison (service-level)",
                baseline_count=len(baseline_set),
                current_count=len(current_set),
                added=len(added),
                removed=len(removed),
                using_registry=self._service_registry is not None
            )
            
            # Create changes for added connections
            if 'all' in enabled_types or 'connection_added' in enabled_types:
                for conn in added:
                    change = self._create_connection_change(
                        conn, cluster_id, analysis_id, run_id, run_number, 
                        is_new=True
                    )
                    changes.append(change)
            
            # Create changes for removed connections
            if 'all' in enabled_types or 'connection_removed' in enabled_types:
                for conn in removed:
                    change = self._create_connection_change(
                        conn, cluster_id, analysis_id, run_id, run_number, 
                        is_new=False
                    )
                    changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect connection changes", error=str(e))
        
        return changes
    
    def _aggregate_to_service_connections(
        self, 
        records: List[Any]
    ) -> Set[ServiceConnectionKey]:
        """
        Aggregate raw connection records to service-level connections.
        
        This:
        - Resolves pod names to workload names (deployment/statefulset)
        - Resolves IPs to service names
        - Filters out ephemeral ports
        - Deduplicates connections from different pods of same workload
        """
        connections = set()
        
        for r in records:
            # Skip ephemeral ports
            if r.dest_port >= EPHEMERAL_PORT_START:
                continue
            
            # Resolve source workload
            if self._service_registry:
                source_workload = self._service_registry.resolve_to_workload(
                    r.source_namespace, r.source_pod
                )
            else:
                source_workload = self._extract_workload_name(r.source_pod)
            
            # Resolve destination
            dest_service = r.dest_pod
            dest_namespace = r.dest_namespace or r.source_namespace
            
            if self._service_registry:
                # Try to resolve IP to service
                if self._is_ip_address(r.dest_pod):
                    resolved = self._service_registry.resolve_ip_to_service(r.dest_pod)
                    if resolved:
                        parts = resolved.split("/", 1)
                        dest_namespace = parts[0]
                        dest_service = parts[1] if len(parts) > 1 else parts[0]
                    else:
                        # External IP - keep as-is
                        dest_namespace = "external"
                else:
                    # Pod name - resolve to workload
                    dest_service = self._service_registry.resolve_to_workload(
                        dest_namespace, r.dest_pod
                    )
            else:
                # Fallback: extract workload name from pod name
                if not self._is_ip_address(r.dest_pod):
                    dest_service = self._extract_workload_name(r.dest_pod)
            
            connections.add(ServiceConnectionKey(
                source_workload=source_workload,
                source_namespace=r.source_namespace,
                dest_service=dest_service,
                dest_namespace=dest_namespace,
                dest_port=r.dest_port,
                protocol=r.protocol or "TCP"
            ))
        
        return connections
    
    def _create_connection_change(
        self,
        conn: Any,  # ConnectionWithDirection or ServiceConnectionKey
        cluster_id: int,
        analysis_id: str,
        run_id: Optional[int],
        run_number: Optional[int],
        is_new: bool
    ) -> Change:
        """Create a Change object for a connection add/remove."""
        
        # Handle both ConnectionWithDirection and ServiceConnectionKey
        if isinstance(conn, ServiceConnectionKey):
            target = f"{conn.source_workload} → {conn.dest_service}:{conn.dest_port}"
            namespace = conn.source_namespace
            dest_port = conn.dest_port
            protocol = conn.protocol
            direction = "outbound"  # Service connections are typically outbound
            
            state = {
                "source_workload": conn.source_workload,
                "source_namespace": conn.source_namespace,
                "dest_service": conn.dest_service,
                "dest_namespace": conn.dest_namespace,
                "dest_port": conn.dest_port,
                "protocol": conn.protocol
            }
        else:
            # ConnectionWithDirection (legacy)
            target = f"{conn.source_pod} → {conn.dest_pod}:{conn.dest_port}"
            namespace = conn.source_namespace or self._extract_namespace(conn.source_pod)
            dest_port = conn.dest_port
            protocol = conn.protocol
            direction = conn.direction
            
            state = {
                "source_pod": conn.source_pod,
                "source_namespace": conn.source_namespace,
                "dest_pod": conn.dest_pod,
                "dest_namespace": conn.dest_namespace,
                "dest_port": conn.dest_port,
                "protocol": conn.protocol,
                "direction": conn.direction
            }
        
        # Assess risk
        risk_level = self._assess_connection_risk_by_port(dest_port, direction, is_new)
        
        # Format details
        action = "New service" if is_new else "Lost service"
        details = f"{action} connection to port {dest_port} ({protocol})"
        
        return Change(
            change_type='connection_added' if is_new else 'connection_removed',
            target=target,
            namespace=namespace,
            details=details,
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            run_id=run_id,
            run_number=run_number,
            source=ChangeSource.EBPF_EVENTS.value,
            before_state={} if is_new else state,
            after_state=state if is_new else {},
            entity_type="connection",
            risk_level=risk_level,
            metadata={
                "connection_type": "new" if is_new else "lost",
                "direction": direction,
                "protocol": protocol,
                "service_level": isinstance(conn, ServiceConnectionKey)
            }
        )
    
    def _assess_connection_risk_by_port(
        self, 
        port: int, 
        direction: str, 
        is_new: bool
    ) -> str:
        """Assess risk level based on port and connection characteristics"""
        if direction == 'inbound':
            return RiskLevel.HIGH.value
        
        if port in [22, 23, 3389, 5900]:  # SSH, Telnet, RDP, VNC
            return RiskLevel.CRITICAL.value
        
        if port < 1024:
            return RiskLevel.HIGH.value if is_new else RiskLevel.MEDIUM.value
        
        if not is_new:
            return RiskLevel.HIGH.value
        
        return RiskLevel.MEDIUM.value
    
    def _assess_connection_risk(self, conn: ConnectionWithDirection, is_new: bool) -> str:
        """LEGACY: Assess risk level based on connection characteristics"""
        return self._assess_connection_risk_by_port(conn.dest_port, conn.direction, is_new)
    
    def _format_connection_details(self, conn: ConnectionWithDirection, is_new: bool) -> str:
        """LEGACY: Format detailed connection description"""
        action = "New" if is_new else "Lost"
        direction_label = {
            'inbound': '← (inbound)',
            'outbound': '→ (outbound)',
            'internal': '↔ (internal)'
        }.get(conn.direction, '')
        
        return f"{action} {conn.protocol} connection {direction_label} to port {conn.dest_port}"
    
    # ==========================================
    # PORT CHANGE DETECTION (Service Ports Only)
    # ==========================================
    
    def _is_service_port(self, port: int) -> bool:
        """
        Check if port is a service port (not ephemeral).
        
        Port Classification (GLOBAL - not product-specific):
        1. port >= 32768 (Linux ephemeral range) → NEVER a service port
        2. ServicePortRegistry has the port → Definitely a service port
        3. port < 32768 → Likely a service port (general rule)
        
        This logic is GENERAL and works for ANY product/service:
        - No hardcoded product-specific port lists
        - Uses dynamic K8s Service definitions when available
        - Falls back to OS-level ephemeral port range detection
        """
        # Ephemeral ports (32768-65535 on Linux) are NEVER service ports
        # This is the ONLY hardcoded rule and it's based on OS defaults
        if port >= EPHEMERAL_PORT_START:
            return False
        
        # If we have ServicePortRegistry, prefer its knowledge
        # This includes ALL ports defined in K8s Services (any product)
        if self._service_registry:
            known_ports = self._service_registry.get_all_service_ports()
            if port in known_ports:
                return True
        
        # Fallback: ports below ephemeral range are likely service ports
        # This is a GENERAL rule - no product-specific assumptions
        return True
    
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
        if ":" in value and not "/" in value:
            return True
        
        return False
    
    def _extract_workload_name(self, pod_name: str) -> str:
        """
        Extract workload name from pod name.
        
        Examples:
        - backend-7b56fbb98c-26wjd -> backend
        - redis-0 -> redis
        - centos-6448f7b947-jlc88 -> centos
        """
        import re
        
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
    
    async def _detect_port_changes(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None,
        service_ports: Optional[Set[int]] = None
    ) -> List[Change]:
        """
        Detect port changes for existing service connections.
        
        Only tracks changes to service ports:
        - Uses ServicePortRegistry if available
        - Falls back to ephemeral port filtering
        - Aggregates at workload level if registry available
        """
        changes: List[Change] = []
        
        try:
            baseline_records = await self.repository.get_connections(
                analysis_id, baseline_window[0], baseline_window[1], 
                namespace_scope, service_ports
            )
            current_records = await self.repository.get_connections(
                analysis_id, current_window[0], current_window[1], 
                namespace_scope, service_ports
            )
            
            # Index by source-dest workload pair (aggregated level)
            baseline_by_pair: Dict[tuple, Set[int]] = {}
            for r in baseline_records:
                if not self._is_service_port(r.dest_port):
                    continue
                
                # Use workload names instead of pod names
                if self._service_registry:
                    src = self._service_registry.resolve_to_workload(r.source_namespace, r.source_pod)
                    dst = self._service_registry.resolve_to_workload(r.dest_namespace or r.source_namespace, r.dest_pod)
                else:
                    src = self._extract_workload_name(r.source_pod)
                    dst = self._extract_workload_name(r.dest_pod) if not self._is_ip_address(r.dest_pod) else r.dest_pod
                
                key = (src, dst, r.source_namespace)
                if key not in baseline_by_pair:
                    baseline_by_pair[key] = set()
                baseline_by_pair[key].add(r.dest_port)
            
            current_by_pair: Dict[tuple, Set[int]] = {}
            for r in current_records:
                if not self._is_service_port(r.dest_port):
                    continue
                
                if self._service_registry:
                    src = self._service_registry.resolve_to_workload(r.source_namespace, r.source_pod)
                    dst = self._service_registry.resolve_to_workload(r.dest_namespace or r.source_namespace, r.dest_pod)
                else:
                    src = self._extract_workload_name(r.source_pod)
                    dst = self._extract_workload_name(r.dest_pod) if not self._is_ip_address(r.dest_pod) else r.dest_pod
                
                key = (src, dst, r.source_namespace)
                if key not in current_by_pair:
                    current_by_pair[key] = set()
                current_by_pair[key].add(r.dest_port)
            
            # Find port changes (only for service ports)
            for key, current_ports in current_by_pair.items():
                if key in baseline_by_pair:
                    baseline_ports = baseline_by_pair[key]
                    new_ports = current_ports - baseline_ports
                    removed_ports = baseline_ports - current_ports
                    
                    # Only report if there are actual service port changes
                    if new_ports or removed_ports:
                        src_workload, dst_workload, namespace = key
                        
                        # Assess risk based on port types
                        risk = RiskLevel.MEDIUM.value
                        high_risk_ports = {22, 23, 3389, 5900}
                        if any(p in high_risk_ports for p in new_ports):
                            risk = RiskLevel.HIGH.value
                        
                        change = Change(
                            change_type='port_changed',
                            target=f"{src_workload} → {dst_workload}",
                            namespace=namespace,
                            details=self._format_port_change(baseline_ports, current_ports),
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.EBPF_EVENTS.value,
                            before_state={"ports": sorted(baseline_ports)},
                            after_state={"ports": sorted(current_ports)},
                            entity_type="connection",
                            risk_level=risk,
                            metadata={
                                "new_ports": sorted(new_ports),
                                "removed_ports": sorted(removed_ports),
                                "service_level": self._service_registry is not None
                            }
                        )
                        changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect port changes", error=str(e))
        
        return changes
    
    # ==========================================
    # TRAFFIC ANOMALY DETECTION
    # ==========================================
    
    async def _detect_traffic_anomalies(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None
    ) -> List[Change]:
        """Detect traffic volume and latency anomalies."""
        changes: List[Change] = []
        
        try:
            baseline_stats = await self.repository.get_traffic_stats(
                analysis_id, baseline_window[0], baseline_window[1], namespace_scope
            )
            current_stats = await self.repository.get_traffic_stats(
                analysis_id, current_window[0], current_window[1], namespace_scope
            )
            
            for key, current in current_stats.items():
                if key in baseline_stats:
                    baseline = baseline_stats[key]
                    
                    # Volume spike
                    if baseline.total_bytes > 0:
                        volume_ratio = current.total_bytes / baseline.total_bytes
                        if volume_ratio >= self.TRAFFIC_SPIKE_MULTIPLIER:
                            change = Change(
                                change_type='traffic_anomaly',
                                target=f"{current.source_pod} → {current.dest_pod}",
                                namespace=self._extract_namespace(current.source_pod),
                                details=f"Traffic volume spike: {volume_ratio:.1f}x baseline ({self._format_bytes(baseline.total_bytes)} → {self._format_bytes(current.total_bytes)})",
                                cluster_id=cluster_id,
                                analysis_id=analysis_id,
                                run_id=run_id,
                                run_number=run_number,
                                source=ChangeSource.EBPF_EVENTS.value,
                                before_state={"bytes": baseline.total_bytes, "packets": baseline.total_packets},
                                after_state={"bytes": current.total_bytes, "packets": current.total_packets},
                                entity_type="traffic",
                                risk_level=RiskLevel.HIGH.value if volume_ratio > 5 else RiskLevel.MEDIUM.value,
                                metadata={"anomaly_type": "volume_spike", "ratio": volume_ratio}
                            )
                            changes.append(change)
                    
                    # Latency spike
                    if baseline.avg_latency_ms > 0:
                        latency_ratio = current.avg_latency_ms / baseline.avg_latency_ms
                        if latency_ratio >= self.LATENCY_SPIKE_MULTIPLIER:
                            change = Change(
                                change_type='traffic_anomaly',
                                target=f"{current.source_pod} → {current.dest_pod}",
                                namespace=self._extract_namespace(current.source_pod),
                                details=f"Latency spike: {latency_ratio:.1f}x baseline ({baseline.avg_latency_ms:.1f}ms → {current.avg_latency_ms:.1f}ms)",
                                cluster_id=cluster_id,
                                analysis_id=analysis_id,
                                run_id=run_id,
                                run_number=run_number,
                                source=ChangeSource.EBPF_EVENTS.value,
                                before_state={"avg_latency_ms": baseline.avg_latency_ms, "max_latency_ms": baseline.max_latency_ms},
                                after_state={"avg_latency_ms": current.avg_latency_ms, "max_latency_ms": current.max_latency_ms},
                                entity_type="traffic",
                                risk_level=RiskLevel.HIGH.value if latency_ratio > 5 else RiskLevel.MEDIUM.value,
                                metadata={"anomaly_type": "latency_spike", "ratio": latency_ratio}
                            )
                            changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect traffic anomalies", error=str(e))
        
        return changes
    
    # ==========================================
    # DNS ANOMALY DETECTION
    # ==========================================
    
    async def _detect_dns_anomalies(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None
    ) -> List[Change]:
        """Detect DNS anomalies: new domains, NXDOMAIN errors."""
        changes: List[Change] = []
        
        try:
            baseline_dns = await self.repository.get_dns_queries(
                analysis_id, baseline_window[0], baseline_window[1], namespace_scope
            )
            current_dns = await self.repository.get_dns_queries(
                analysis_id, current_window[0], current_window[1], namespace_scope
            )
            
            # Find new domains
            baseline_domains = {(d.source_pod, d.query_name) for d in baseline_dns}
            current_domains = {(d.source_pod, d.query_name) for d in current_dns}
            new_domain_keys = current_domains - baseline_domains
            
            for source_pod, query_name in new_domain_keys:
                dns_obj = next((d for d in current_dns if d.source_pod == source_pod and d.query_name == query_name), None)
                if not dns_obj:
                    continue
                
                risk = RiskLevel.MEDIUM.value
                if dns_obj.response_code == 'NXDOMAIN':
                    risk = RiskLevel.HIGH.value
                
                change = Change(
                    change_type='dns_anomaly',
                    target=f"{source_pod} → {query_name}",
                    namespace=dns_obj.source_namespace or self._extract_namespace(source_pod),
                    details=f"New DNS query: {query_name} ({dns_obj.query_type}) - Response: {dns_obj.response_code}",
                    cluster_id=cluster_id,
                    analysis_id=analysis_id,
                    run_id=run_id,
                    run_number=run_number,
                    source=ChangeSource.EBPF_EVENTS.value,
                    before_state={},
                    after_state={"query_name": query_name, "query_type": dns_obj.query_type, "response_code": dns_obj.response_code},
                    entity_type="dns",
                    risk_level=risk,
                    metadata={"anomaly_type": "new_domain", "response_code": dns_obj.response_code}
                )
                changes.append(change)
            
            # NXDOMAIN spike
            baseline_nxdomain = len([d for d in baseline_dns if d.response_code == 'NXDOMAIN'])
            current_nxdomain = len([d for d in current_dns if d.response_code == 'NXDOMAIN'])
            
            if current_nxdomain > baseline_nxdomain + 10:
                change = Change(
                    change_type='dns_anomaly',
                    target="DNS NXDOMAIN Spike",
                    namespace="cluster-wide",
                    details=f"NXDOMAIN spike detected: {baseline_nxdomain} → {current_nxdomain} (possible DGA or DNS tunneling)",
                    cluster_id=cluster_id,
                    analysis_id=analysis_id,
                    run_id=run_id,
                    run_number=run_number,
                    source=ChangeSource.EBPF_EVENTS.value,
                    before_state={"nxdomain_count": baseline_nxdomain},
                    after_state={"nxdomain_count": current_nxdomain},
                    entity_type="dns",
                    risk_level=RiskLevel.CRITICAL.value,
                    metadata={"anomaly_type": "nxdomain_spike", "increase": current_nxdomain - baseline_nxdomain}
                )
                changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect DNS anomalies", error=str(e))
        
        return changes
    
    # ==========================================
    # PROCESS ANOMALY DETECTION
    # ==========================================
    
    async def _detect_process_anomalies(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None
    ) -> List[Change]:
        """Detect process anomalies: new processes, suspicious commands."""
        changes: List[Change] = []
        
        try:
            baseline_procs = await self.repository.get_process_executions(
                analysis_id, baseline_window[0], baseline_window[1], namespace_scope
            )
            current_procs = await self.repository.get_process_executions(
                analysis_id, current_window[0], current_window[1], namespace_scope
            )
            
            baseline_keys = {(p.pod, p.container, p.comm) for p in baseline_procs}
            current_keys = {(p.pod, p.container, p.comm) for p in current_procs}
            new_proc_keys = current_keys - baseline_keys
            
            for pod, container, comm in new_proc_keys:
                proc = next((p for p in current_procs if p.pod == pod and p.container == container and p.comm == comm), None)
                if not proc:
                    continue
                
                risk = RiskLevel.LOW.value
                anomaly_reason = "new_process"
                
                if comm in self.SUSPICIOUS_COMMANDS:
                    risk = RiskLevel.HIGH.value
                    anomaly_reason = "suspicious_command"
                elif proc.is_root:
                    risk = RiskLevel.MEDIUM.value
                    anomaly_reason = "root_process"
                
                # Build details message - show path only if available
                details_parts = [f"New process: {comm}"]
                if proc.exe:
                    details_parts.append(f"(path: {proc.exe})")
                if proc.is_root:
                    details_parts.append("[ROOT]")
                details_msg = " ".join(details_parts)
                
                change = Change(
                    change_type='process_anomaly',
                    target=f"{pod}/{container}: {comm}",
                    namespace=proc.namespace,
                    details=details_msg,
                    cluster_id=cluster_id,
                    analysis_id=analysis_id,
                    run_id=run_id,
                    run_number=run_number,
                    source=ChangeSource.EBPF_EVENTS.value,
                    before_state={},
                    after_state={
                        "command": comm, 
                        "executable": proc.exe if proc.exe else None, 
                        "uid": proc.uid, 
                        "is_root": proc.is_root
                    },
                    entity_type="process",
                    risk_level=risk,
                    metadata={"anomaly_type": anomaly_reason, "is_suspicious": comm in self.SUSPICIOUS_COMMANDS}
                )
                changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect process anomalies", error=str(e))
        
        return changes
    
    # ==========================================
    # ERROR ANOMALY DETECTION
    # ==========================================
    
    async def _detect_error_anomalies(
        self,
        analysis_id: str,
        cluster_id: int,
        baseline_window: tuple,
        current_window: tuple,
        run_id: Optional[int],
        run_number: Optional[int],
        namespace_scope: Optional[List[str]] = None
    ) -> List[Change]:
        """Detect connection error anomalies."""
        changes: List[Change] = []
        
        try:
            baseline_errors = await self.repository.get_error_stats(
                analysis_id, baseline_window[0], baseline_window[1], namespace_scope
            )
            current_errors = await self.repository.get_error_stats(
                analysis_id, current_window[0], current_window[1], namespace_scope
            )
            
            for key, current in current_errors.items():
                baseline = baseline_errors.get(key)
                source_pod, dest_pod, error_type = key
                
                # New error type
                if baseline is None or baseline.error_count == 0:
                    if current.error_count > 0:
                        change = Change(
                            change_type='error_anomaly',
                            target=f"{source_pod} → {dest_pod}",
                            namespace=self._extract_namespace(source_pod),
                            details=f"New connection errors: {error_type} (count: {current.error_count})",
                            cluster_id=cluster_id,
                            analysis_id=analysis_id,
                            run_id=run_id,
                            run_number=run_number,
                            source=ChangeSource.EBPF_EVENTS.value,
                            before_state={"error_count": 0},
                            after_state={"error_count": current.error_count, "error_type": error_type},
                            entity_type="error",
                            risk_level=RiskLevel.HIGH.value,
                            metadata={"anomaly_type": "new_errors", "error_type": error_type}
                        )
                        changes.append(change)
                
                # Error spike
                elif baseline.error_count > 0 and current.error_count > baseline.error_count * 2:
                    change = Change(
                        change_type='error_anomaly',
                        target=f"{source_pod} → {dest_pod}",
                        namespace=self._extract_namespace(source_pod),
                        details=f"Error spike: {error_type} ({baseline.error_count} → {current.error_count})",
                        cluster_id=cluster_id,
                        analysis_id=analysis_id,
                        run_id=run_id,
                        run_number=run_number,
                        source=ChangeSource.EBPF_EVENTS.value,
                        before_state={"error_count": baseline.error_count},
                        after_state={"error_count": current.error_count},
                        entity_type="error",
                        risk_level=RiskLevel.MEDIUM.value,
                        metadata={
                            "anomaly_type": "error_spike",
                            "error_type": error_type,
                            "increase_ratio": current.error_count / baseline.error_count
                        }
                    )
                    changes.append(change)
            
        except Exception as e:
            logger.error("Failed to detect error anomalies", error=str(e))
        
        return changes
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    def _extract_namespace(self, pod_name: str) -> str:
        """Extract namespace from pod name if formatted as namespace/pod"""
        if '/' in pod_name:
            return pod_name.split('/')[0]
        return 'default'
    
    def _format_port_change(self, old_ports: Set[int], new_ports: Set[int]) -> str:
        """Format port change description"""
        added = new_ports - old_ports
        removed = old_ports - new_ports
        
        parts = []
        if added:
            parts.append(f"Added ports: {sorted(added)}")
        if removed:
            parts.append(f"Removed ports: {sorted(removed)}")
        
        return "; ".join(parts) if parts else "Port configuration changed"
    
    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes in human readable form"""
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.1f} GB"
