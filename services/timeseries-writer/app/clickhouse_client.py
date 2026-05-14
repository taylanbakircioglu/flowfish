"""ClickHouse Client for bulk writes

Supports all Inspector Gadget event types:
- network_flows
- dns_queries
- process_events
- file_operations
- capability_checks (security events)
- oom_kills
- bind_events
- sni_events
- mount_events

NOTE: tcp_lifecycle is deprecated - Inspektor Gadget trace_tcp doesn't produce
TCP state transition events. TCP connection info is captured in network_flows.
"""

import logging
import json
import re
from typing import List, Dict, Any, Union
from datetime import datetime, timezone
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickHouseError
from app.config import settings
from app import virtual_trace_correlator

logger = logging.getLogger(__name__)


def sanitize_labels(labels: Any) -> Dict[str, str]:
    """
    Sanitize labels for ClickHouse Map(String, String) columns.
    
    Ensures all keys and values are strings.
    Handles:
    - Dict with nested values (flatten to string)
    - String labels (parse comma-separated format)
    - None (return empty dict)
    """
    if labels is None:
        return {}
    
    if isinstance(labels, str):
        # Parse comma-separated format: "key1=val1,key2=val2"
        if not labels:
            return {}
        result = {}
        for item in labels.split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                result[k.strip()] = v.strip()
        return result
    
    if isinstance(labels, dict):
        # Convert all values to strings
        result = {}
        for k, v in labels.items():
            if isinstance(v, dict):
                # Nested dict - convert to JSON string
                result[str(k)] = json.dumps(v, default=str)
            elif isinstance(v, (list, tuple)):
                result[str(k)] = json.dumps(v, default=str)
            elif v is None:
                result[str(k)] = ""
            else:
                result[str(k)] = str(v)
        return result
    
    return {}


def sanitize_string_array(arr: Any) -> List[str]:
    """
    Sanitize array for ClickHouse Array(String) columns.
    
    Ensures all items are strings.
    """
    if arr is None:
        return []
    
    if isinstance(arr, str):
        # Single string - return as list
        return [arr] if arr else []
    
    if isinstance(arr, (list, tuple)):
        result = []
        for item in arr:
            if item is None:
                continue
            if isinstance(item, (dict, list, tuple)):
                result.append(json.dumps(item, default=str))
            else:
                result.append(str(item))
        return result
    
    return [str(arr)]


def safe_string(value: Any, default: str = "") -> str:
    """
    Safely convert any value to string for ClickHouse String columns.
    
    Handles:
    - None → default value
    - str → as is
    - int/float → str()
    - dict → extract known fields (addr, ip, name) or JSON dump
    - list → JSON dump
    """
    if value is None:
        return default
    
    if isinstance(value, str):
        return value
    
    if isinstance(value, (int, float, bool)):
        return str(value)
    
    if isinstance(value, dict):
        # Try to extract meaningful value from nested dict
        # Inspektor Gadget often wraps values in dicts with 'addr', 'ip', 'name' keys
        for key in ['addr', 'ip', 'name', 'pod', 'namespace', 'container', 'node', 'value']:
            if key in value:
                extracted = value[key]
                if isinstance(extracted, str):
                    return extracted
                elif isinstance(extracted, (int, float)):
                    return str(extracted)
        
        # If no known key, check if it's a k8s nested structure
        if 'k8s' in value:
            k8s = value['k8s']
            if isinstance(k8s, dict):
                # Try pod/namespace from k8s
                for key in ['podName', 'pod', 'namespace', 'containerName']:
                    if key in k8s and isinstance(k8s[key], str):
                        return k8s[key]
        
        # Fallback: dump as JSON
        return json.dumps(value, default=str)
    
    if isinstance(value, (list, tuple)):
        # For list/tuple, convert to JSON
        return json.dumps(value, default=str)
    
    # Fallback for any other type
    return str(value)


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert any value to int for ClickHouse Int columns."""
    if value is None:
        return default
    
    if isinstance(value, int):
        return value
    
    if isinstance(value, float):
        return int(value)
    
    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    if isinstance(value, dict):
        # Try to extract from nested dict
        for key in ['port', 'value', 'pid', 'uid', 'gid']:
            if key in value:
                return safe_int(value[key], default)
    
    return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert any value to float for ClickHouse Float columns."""
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    return default


def parse_latency_ns(value: Any) -> int:
    """
    Parse latency_ns value which can be:
    - int: 123456 (nanoseconds)
    - str: "123456ns", "0ns", "123456" (with or without 'ns' suffix)
    - float: 123456.0
    
    Returns nanoseconds as integer.
    """
    if value is None:
        return 0
    
    if isinstance(value, int):
        return value
    
    if isinstance(value, float):
        return int(value)
    
    if isinstance(value, str):
        # Remove 'ns' suffix if present
        cleaned = value.strip().rstrip('ns').strip()
        if not cleaned:
            return 0
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return 0
    
    return 0


def parse_l7_timestamp(ts: Any) -> datetime:
    """Parse L7 event timestamp (ISO string, datetime, or Unix ms int from ingestion)."""
    if ts is None:
        logger.warning("L7 timestamp is None, using current time")
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, (int, float)):
        t = float(ts)
        if t > 1e15:
            t = t / 1e6
        elif t > 1e12:
            t = t / 1000.0
        return datetime.fromtimestamp(t, tz=timezone.utc)
    if isinstance(ts, str):
        return parse_timestamp(ts)
    logger.warning("L7 timestamp has unexpected type %s, using current time", type(ts).__name__)
    return datetime.now(timezone.utc)


def _l7_flat_endpoint(data: Dict[str, Any], side: str) -> Dict[str, Any]:
    """Resolve src/dst fields from flat keys or nested {src|dst} dict (L7 ingestion format).

    Empty namespace/workload are normalised to 'unknown' so ClickHouse stays
    consistent with the graph-writer's Neo4j node IDs.
    """
    nested = data.get(side)
    if isinstance(nested, dict):
        wl = (
            nested.get("workload_name")
            or nested.get("pod_name")
            or nested.get("name")
            or nested.get("ip")
            or "unknown"
        )
        return {
            "namespace": nested.get("namespace") or "unknown",
            "workload": wl,
            "pod": nested.get("pod_name") or nested.get("name") or "",
            "ip": nested.get("ip", ""),
            "port": nested.get("port"),
            "service_name": nested.get("name") or "",
        }
    prefix = "src_" if side == "src" else "dst_"
    return {
        "namespace": data.get(f"{prefix}namespace") or "unknown",
        "workload": data.get(f"{prefix}workload") or data.get(f"{prefix}workload_name") or "unknown",
        "pod": data.get(f"{prefix}pod", ""),
        "ip": data.get(f"{prefix}ip", ""),
        "port": data.get(f"{prefix}port"),
        "service_name": data.get("dst_service", "") if side == "dst" else "",
    }


def _l7_labels_json(val: Any) -> str:
    if val is None:
        return "{}"
    if isinstance(val, str):
        return val if val.strip() else "{}"
    if isinstance(val, dict):
        return json.dumps(val, default=str)
    return json.dumps(sanitize_labels(val), default=str)


# Synthetic namespaces produced upstream when a Beyla endpoint cannot be
# resolved to a real Kubernetes object. Spans whose source or destination
# falls into one of these buckets carry no distributed-observability value
# and pollute aggregate Service Map metrics (e.g. Flowfish's own gadget
# gRPC streams produce per-connection durations measured in minutes).
# The flowfish-l7-collector already drops these at ingestion; this set is
# the second layer of defense so a stale collector or operator-applied
# Beyla configuration cannot leak self-monitoring traffic into ClickHouse.
_L7_NOISE_NAMESPACES: frozenset = frozenset({"loopback"})


def _l7_endpoint_namespace(data: Dict[str, Any], side: str) -> str:
    """Extract namespace from either the flat or nested endpoint format.

    Order: flat top-level (`src_namespace` / `dst_namespace`) → nested
    (`src.namespace` / `dst.namespace`). Returns empty string for any
    shape we don't recognize so a malformed upstream message cannot
    crash the writer batch path.
    """
    flat = data.get(f"{side}_namespace")
    if isinstance(flat, str) and flat:
        return flat
    nested = data.get(side)
    if isinstance(nested, dict):
        ns = nested.get("namespace")
        if isinstance(ns, str):
            return ns
    return ""


def _is_l7_self_monitoring(msg: Any) -> bool:
    """Return True when an L7 message represents pod-internal localhost traffic.

    Inspects both the flat src_namespace/dst_namespace fields used by the
    intermediate Flowfish event format and the nested data.src/data.dst
    endpoint dicts produced by the collector. Tolerates malformed messages
    (non-dict msg or non-dict data) by returning False so the caller will
    pass the row through to the regular insertion path, where ClickHouse's
    schema validation catches genuinely broken events.
    """
    if not isinstance(msg, dict):
        return False
    data = msg.get("data")
    if not isinstance(data, dict):
        return False
    src_ns = _l7_endpoint_namespace(data, "src")
    dst_ns = _l7_endpoint_namespace(data, "dst")
    return src_ns.lower() in _L7_NOISE_NAMESPACES or dst_ns.lower() in _L7_NOISE_NAMESPACES


def _filter_l7_noise(batch: List[Dict[str, Any]], protocol: str) -> List[Dict[str, Any]]:
    """Drop self-monitoring localhost spans before insertion. Logs at debug
    level when at least one event was filtered so operators can correlate
    suppressed counts with Service Map cleanliness."""
    if not batch:
        return batch
    kept = [m for m in batch if not _is_l7_self_monitoring(m)]
    dropped = len(batch) - len(kept)
    if dropped:
        logger.debug(
            "Filtered %d localhost-only %s span(s) (Flowfish self-monitoring noise)",
            dropped,
            protocol,
        )
    return kept


def parse_timestamp(ts: Union[str, datetime, None]) -> datetime:
    """
    Parse timestamp from various formats to datetime object.
    
    Handles:
    - ISO format with nanoseconds: "2025-11-27T07:51:43.029321509Z"
    - ISO format with microseconds: "2025-11-27T07:51:43.029321Z"
    - ISO format without fraction: "2025-11-27T07:51:43Z"
    - datetime objects
    - None (returns current UTC time)
    """
    if ts is None:
        return datetime.now(timezone.utc)
    
    if isinstance(ts, datetime):
        return ts
    
    if not isinstance(ts, str):
        return datetime.now(timezone.utc)
    
    try:
        # Remove 'Z' suffix and handle timezone
        ts_clean = ts.replace('Z', '+00:00')
        
        # Handle nanoseconds by truncating to microseconds (6 digits)
        # Match pattern like .029321509 and truncate to .029321
        ns_pattern = r'\.(\d{7,9})([+-])'
        match = re.search(ns_pattern, ts_clean)
        if match:
            fraction = match.group(1)[:6]  # Keep only first 6 digits
            ts_clean = re.sub(ns_pattern, f'.{fraction}\\2', ts_clean)
        
        # Try parsing with fromisoformat
        return datetime.fromisoformat(ts_clean)
        
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{ts}': {e}, using current time")
        return datetime.now(timezone.utc)


class ClickHouseWriter:
    """ClickHouse bulk writer for all event types"""
    
    def __init__(self):
        self.client = None
        # Per-table flag for graceful trace column fallback.
        # Each L7 table tracks independently whether trace columns are migrated.
        # When INSERT fails with "Unknown column" the corresponding flag flips
        # to False and subsequent INSERTs use legacy column lists for that table.
        # Flags reset on process restart (re-discovers schema state).
        self._trace_cols = {"http": True, "grpc": True, "dns": True}
        # Phase 4 — separate flag for the PID columns (pid, ppid, container_id,
        # virtual_trace_id). These rolled out via clickhouse_007_add_l7_pid.sql
        # and may be missing on clusters that haven't yet applied the
        # migration. DNS is intentionally left out of this map: PID
        # correlation is HTTP/gRPC only. Mirrors `_trace_cols` semantics:
        # initially True, flips to False on schema mismatch.
        self._pid_cols = {"http": True, "grpc": True}
        self._connect()
    
    def _connect(self):
        """Connect to ClickHouse"""
        try:
            self.client = Client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                user=settings.clickhouse_user,
                password=settings.clickhouse_password,
                database=settings.clickhouse_database,
                send_receive_timeout=60,
            )
            
            # Test connection
            self.client.execute('SELECT 1')
            logger.info(f"✅ Connected to ClickHouse at {settings.clickhouse_host}:{settings.clickhouse_port}")
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to connect to ClickHouse: {e}")
            raise
    
    def write_network_flows(self, messages: List[Dict[str, Any]]) -> int:
        """
        Bulk insert network flows
        
        Args:
            messages: List of network flow messages
            
        Returns:
            Number of rows inserted
        """
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: namespace/pod/container and src_namespace/src_pod/src_container
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('src_namespace') or data.get('namespace', '')),
                safe_string(data.get('src_pod') or data.get('pod') or data.get('pod_name', '')),
                safe_string(data.get('src_container') or data.get('container') or data.get('container_name', '')),
                safe_string(data.get('src_node') or data.get('node', '')),
                safe_string(data.get('src_ip', '')),
                safe_int(data.get('src_port', 0)),
                safe_string(data.get('dst_namespace', '')),
                safe_string(data.get('dst_pod', '')),
                safe_string(data.get('dst_container', '')),
                safe_string(data.get('dst_ip', '')),
                safe_int(data.get('dst_port', 0)),
                safe_string(data.get('dst_hostname', '')),
                safe_string(data.get('protocol', 'TCP')),
                safe_string(data.get('direction', 'outbound')),
                safe_string(data.get('type') or data.get('event_subtype', '')),  # connection_state from event type
                safe_int(data.get('bytes_sent', 0)),
                safe_int(data.get('bytes_received', 0)),
                safe_int(data.get('packets_sent', 0)),
                safe_int(data.get('packets_received', 0)),
                safe_int(data.get('duration_ms', 0)),
                safe_float(data.get('latency_ms') or (parse_latency_ns(data.get('latency_ns')) / 1000000)),
                safe_int(data.get('error_count') or data.get('error') or data.get('error_code', 0)),
                safe_int(data.get('retransmit_count') or data.get('retransmits', 0)),
                safe_string(data.get('error_type', '')),  # Error type: CONNECTION_RESET, RETRANSMIT, etc.
                sanitize_labels(data.get('labels', {})),  # source_labels
                sanitize_labels(data.get('dst_labels', {})),  # dest_labels
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO network_flows (
                timestamp, cluster_id, analysis_id, cluster_name,
                source_namespace, source_pod, source_container, source_node,
                source_ip, source_port,
                dest_namespace, dest_pod, dest_container,
                dest_ip, dest_port, dest_hostname,
                protocol, direction, connection_state,
                bytes_sent, bytes_received,
                packets_sent, packets_received,
                duration_ms, latency_ms,
                error_count, retransmit_count, error_type,
                source_labels, dest_labels,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} network_flows")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert network_flows: {e}")
            raise
    
    def write_dns_queries(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert DNS queries"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: name (query_name), qtype (query_type), rcode (response_code), answers (response_ips)
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('src_namespace') or data.get('namespace', '')),
                safe_string(data.get('src_pod') or data.get('pod') or data.get('pod_name', '')),
                safe_string(data.get('src_container') or data.get('container') or data.get('container_name', '')),
                safe_string(data.get('src_ip', '')),
                safe_string(data.get('name') or data.get('query_name', '')),
                safe_string(data.get('qtype') or data.get('query_type', 'A')),
                safe_string(data.get('query_class', 'IN')),
                safe_string(data.get('rcode') or data.get('response_code', '')),
                sanitize_string_array(data.get('addresses') or data.get('answers') or data.get('response_ips', [])),
                [],  # response_cnames
                safe_int(data.get('response_ttl', 0)),
                safe_float(data.get('latency_ms') or (parse_latency_ns(data.get('latency_ns')) / 1000000)),
                safe_string(data.get('dst_ip') or data.get('dns_server_ip', '')),
                safe_int(data.get('dst_port') or data.get('dns_server_port', 53)),
                sanitize_labels(data.get('labels', {})),
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO dns_queries (
                timestamp, cluster_id, analysis_id, cluster_name,
                source_namespace, source_pod, source_container, source_ip,
                query_name, query_type, query_class,
                response_code, response_ips, response_cnames, response_ttl,
                latency_ms,
                dns_server_ip, dns_server_port,
                labels, event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} dns_queries")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert dns_queries: {e}")
            raise
    
    def write_tcp_connections(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert TCP lifecycle events (DEPRECATED)
        
        NOTE: This method is deprecated. Inspektor Gadget trace_tcp doesn't produce
        TCP state transition events (oldstate/newstate). TCP connection info is
        captured in network_flows via connect/accept/close events.
        
        This method is kept for backward compatibility but will receive no data.
        """
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('src_ip', '')),
                safe_int(data.get('src_port', 0)),
                safe_string(data.get('dst_ip', '')),
                safe_int(data.get('dst_port', 0)),
                safe_string(data.get('old_state', 'CLOSED')),
                safe_string(data.get('new_state', 'ESTABLISHED')),
                safe_string(data.get('src_namespace') or data.get('namespace', '')),
                safe_string(data.get('src_pod') or data.get('pod_name', '')),
                safe_string(data.get('src_container') or data.get('container_name', '')),
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO tcp_lifecycle (
                timestamp, cluster_id, analysis_id, cluster_name,
                source_ip, source_port, dest_ip, dest_port,
                old_state, new_state,
                source_namespace, source_pod, source_container,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} tcp_lifecycle")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert tcp_lifecycle: {e}")
            raise
    
    def write_process_events(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert process events (exec, exit, signal)"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, exepath
            # Support both IG format and legacy pod_name/container_name format
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('node') or data.get('src_node', '')),
                safe_int(data.get('pid', 0)),
                safe_int(data.get('ppid', 0)),
                safe_int(data.get('uid', 0)),
                safe_int(data.get('gid', 0)),
                safe_string(data.get('comm', '')),
                safe_string(data.get('exepath') or data.get('exe', '')),
                sanitize_string_array(data.get('args', [])),
                safe_string(data.get('cwd', '')),
                safe_string(data.get('type') or data.get('process_event_type', 'exec')),
                safe_int(data.get('exit_code', 0)),
                safe_int(data.get('signal', 0)),
                sanitize_labels(data.get('labels', {})),
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO process_events (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container, node,
                pid, ppid, uid, gid,
                comm, exe, args, cwd,
                event_type, exit_code, signal,
                labels, event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} process_events")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert process_events: {e}")
            raise
    
    def write_file_events(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert file operation events"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container (not pod_name, container_name)
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('operation') or data.get('type', 'open')),
                safe_string(data.get('file_path') or data.get('path') or data.get('filename', '')),
                safe_string(data.get('file_flags') or data.get('flags', '')),
                safe_int(data.get('file_mode') or data.get('mode', 0)),
                safe_int(data.get('pid', 0)),
                safe_string(data.get('comm', '')),
                safe_int(data.get('uid', 0)),
                safe_int(data.get('gid', 0)),
                safe_int(data.get('bytes', 0)),
                safe_int(data.get('duration_us') or (parse_latency_ns(data.get('latency_ns')) // 1000)),
                safe_int(data.get('error_code') or data.get('error', 0)),
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO file_operations (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container,
                operation, file_path, file_flags, file_mode,
                pid, comm, uid, gid,
                bytes, duration_us, error_code,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} file_operations")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert file_operations: {e}")
            raise
    
    def write_security_events(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert security events (capability checks)"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, cap (not pod_name, container_name, capability)
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('cap') or data.get('capability', '')),
                safe_string(data.get('syscall', '')),
                safe_int(data.get('pid', 0)),
                safe_string(data.get('comm', '')),
                safe_int(data.get('uid', 0)),
                safe_int(data.get('gid', 0)),
                # Inspector Gadget sends verdict as integer: 0=allowed, 1=denied
                # Convert to string for ClickHouse schema compatibility
                'denied' if data.get('verdict') == 1 or data.get('verdict') == '1' or data.get('capable') == False else 'allowed',
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO capability_checks (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container,
                capability, syscall,
                pid, comm, uid, gid,
                verdict,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} capability_checks")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert capability_checks: {e}")
            raise
    
    def write_oom_events(self, messages: List[Dict[str, Any]]) -> int:
        """Bulk insert OOM kill events"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, fpid/kpid, fcomm/kcomm
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('node') or data.get('src_node', '')),
                safe_int(data.get('fpid') or data.get('pid', 0)),
                safe_string(data.get('fcomm') or data.get('comm', '')),
                safe_int(data.get('memory_limit') or data.get('fpages', 0)),
                safe_int(data.get('memory_usage', 0)),
                safe_int(data.get('memory_pages_total') or data.get('tpages', 0)),
                safe_int(data.get('memory_pages_free', 0)),
                safe_string(data.get('cgroup_path') or data.get('cgroup', '')),
                json.dumps(data, default=str),  # event_data_json
            ))
        
        try:
            query = '''
            INSERT INTO oom_kills (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container, node,
                pid, comm,
                memory_limit, memory_usage,
                memory_pages_total, memory_pages_free,
                cgroup_path,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} oom_kills")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert oom_kills: {e}")
            raise
    
    def write_bind_events(self, messages: List[Dict[str, Any]]) -> int:
        """Write socket bind events to ClickHouse"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, addr, port
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('node') or data.get('src_node', '')),
                safe_string(data.get('addr') or data.get('bind_addr') or data.get('dst_ip', '')),
                safe_int(data.get('port') or data.get('bind_port') or data.get('dst_port', 0)),
                safe_string(data.get('protocol', 'TCP')),
                safe_string(data.get('interface') or data.get('if', '')),
                safe_int(data.get('error_code', 0)),
                safe_int(data.get('pid', 0)),
                safe_string(data.get('comm', '')),
                safe_int(data.get('uid', 0)),
                json.dumps(data, default=str),
            ))
        
        try:
            query = '''
            INSERT INTO bind_events (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container, node,
                bind_addr, bind_port, protocol, interface,
                error_code, pid, comm, uid,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} bind_events")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert bind_events: {e}")
            raise
    
    def write_sni_events(self, messages: List[Dict[str, Any]]) -> int:
        """Write TLS/SSL SNI events to ClickHouse"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, name (SNI name)
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('name') or data.get('sni_name', '')),
                safe_string(data.get('src_ip', '')),
                safe_int(data.get('src_port', 0)),
                safe_string(data.get('dst_ip', '')),
                safe_int(data.get('dst_port', 0)),
                safe_string(data.get('tls_version') or data.get('version', '')),
                safe_string(data.get('cipher_suite', '')),
                safe_int(data.get('pid', 0)),
                safe_string(data.get('comm', '')),
                json.dumps(data, default=str),
            ))
        
        try:
            query = '''
            INSERT INTO sni_events (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container,
                sni_name, src_ip, src_port, dst_ip, dst_port,
                tls_version, cipher_suite,
                pid, comm,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} sni_events")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert sni_events: {e}")
            raise
    
    def write_mount_events(self, messages: List[Dict[str, Any]]) -> int:
        """Write mount events to ClickHouse"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            # Inspector Gadget uses: pod, container, src/dest
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(msg.get('analysis_name', '')),
                safe_string(data.get('namespace') or data.get('src_namespace', '')),
                safe_string(data.get('pod') or data.get('pod_name') or data.get('src_pod', '')),
                safe_string(data.get('container') or data.get('container_name') or data.get('src_container', '')),
                safe_string(data.get('node') or data.get('src_node', '')),
                safe_string(data.get('call') or data.get('operation', 'mount')),
                safe_string(data.get('src') or data.get('source', '')),
                safe_string(data.get('dest') or data.get('target', '')),
                safe_string(data.get('fs') or data.get('fs_type', '')),
                safe_string(data.get('flags') or data.get('data', '')),
                safe_string(data.get('options', '')),
                safe_int(data.get('error') or data.get('error_code', 0)),
                safe_int(data.get('pid', 0)),
                safe_string(data.get('comm', '')),
                json.dumps(data, default=str),
            ))
        
        try:
            query = '''
            INSERT INTO mount_events (
                timestamp, cluster_id, analysis_id, cluster_name,
                namespace, pod, container, node,
                operation, source, target, fs_type, flags, options,
                error_code, pid, comm,
                event_data_json
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} mount_events")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert mount_events: {e}")
            raise
    
    def write_workload_metadata(self, messages: List[Dict[str, Any]]) -> int:
        """Write workload/pod metadata to ClickHouse for IP -> Pod lookups"""
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            labels = data.get('labels', {})
            if not isinstance(labels, dict):
                labels = {}
            
            rows.append((
                parse_timestamp(msg.get('timestamp')),
                safe_string(msg.get('cluster_id', '')),
                safe_string(msg.get('cluster_name', '')),
                safe_string(msg.get('analysis_id', '')),
                safe_string(data.get('namespace', '')),
                safe_string(data.get('workload_name', '')),
                safe_string(data.get('workload_type', 'Pod')),
                safe_string(data.get('pod_name', '')),
                safe_string(data.get('pod_uid', '')),
                safe_string(data.get('container_name', '')),
                safe_string(data.get('container_id', '')),
                safe_string(data.get('node_name', '')),
                safe_string(data.get('pod_ip', '')),
                {safe_string(k): safe_string(v) for k, v in labels.items()},  # labels Map
                {},  # annotations Map (empty for now)
                safe_string(data.get('owner_kind', '')),
                safe_string(data.get('owner_name', '')),
                parse_timestamp(msg.get('timestamp')),  # first_seen
                parse_timestamp(msg.get('timestamp')),  # last_seen
                1,  # event_count
            ))
        
        try:
            query = '''
            INSERT INTO workload_metadata (
                timestamp, cluster_id, cluster_name, analysis_id,
                namespace, workload_name, workload_type,
                pod_name, pod_uid, container_name, container_id,
                node_name, pod_ip,
                labels, annotations,
                owner_kind, owner_name,
                first_seen, last_seen, event_count
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} workload_metadata records")
            
            # Phase 8: Sync to PostgreSQL if enabled (for change detection)
            try:
                from app.postgres_sync import sync_workloads_to_postgresql
                synced = sync_workloads_to_postgresql(messages)
                if synced > 0:
                    logger.debug(f"Synced {synced} workloads to PostgreSQL")
            except Exception as sync_error:
                # Don't fail ClickHouse write if PostgreSQL sync fails
                logger.warning(f"PostgreSQL sync failed (ClickHouse write OK): {sync_error}")
            
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert workload_metadata: {e}")
            raise
    
    def write_change_events(self, messages: List[Dict[str, Any]]) -> int:
        """
        Write change events to ClickHouse for Change Detection feature.
        
        Uses ReplacingMergeTree with event_id UUID for idempotency.
        NO TTL - data retained until analysis is deleted.
        
        Args:
            messages: List of change event messages from Change Detection Worker
            
        Returns:
            Number of rows inserted
        """
        if not messages:
            return 0
        
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            
            # Build row tuple matching ClickHouse schema
            rows.append((
                # Timestamps
                parse_timestamp(msg.get('timestamp')),
                parse_timestamp(msg.get('detected_at') or msg.get('timestamp')),
                
                # Identifiers
                safe_string(msg.get('event_id', '')),  # UUID as string
                safe_int(msg.get('cluster_id', 0)),
                safe_string(msg.get('cluster_name', '')),
                safe_string(msg.get('analysis_id', '')),
                
                # Run information
                safe_int(msg.get('run_id', 0)),
                safe_int(msg.get('run_number', 1)),
                
                # Change details
                safe_string(data.get('change_type') or msg.get('change_type', '')),
                safe_string(data.get('risk_level') or msg.get('risk_level', 'medium')),
                
                # Target info
                safe_string(data.get('target_name') or data.get('target', '')),
                safe_string(data.get('target_namespace') or data.get('namespace', '')),
                safe_string(data.get('target_type', 'workload')),
                safe_int(data.get('entity_id', 0)),
                safe_int(data.get('namespace_id')) if data.get('namespace_id') else None,
                
                # State (JSON)
                json.dumps(data.get('before_state', {}), default=str),
                json.dumps(data.get('after_state', {}), default=str),
                
                # Impact
                safe_int(data.get('affected_services', 0)),
                safe_int(data.get('blast_radius', 0)),
                
                # Audit
                safe_string(data.get('changed_by', 'auto-discovery')),
                safe_string(data.get('details', '')),
                json.dumps(data.get('metadata', {}), default=str),
            ))
        
        try:
            query = '''
            INSERT INTO change_events (
                timestamp, detected_at,
                event_id, cluster_id, cluster_name, analysis_id,
                run_id, run_number,
                change_type, risk_level,
                target_name, target_namespace, target_type, entity_id, namespace_id,
                before_state, after_state,
                affected_services, blast_radius,
                changed_by, details, metadata
            ) VALUES
            '''
            
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} change_events")
            return len(rows)
            
        except ClickHouseError as e:
            logger.error(f"❌ Failed to insert change_events: {e}")
            raise
    
    # ------------------------------------------------------------------
    # L7 INSERT helpers: legacy and with-trace row builders.
    # Trace columns are positional; tuples must match the column lists in the
    # corresponding INSERT statements exactly. Order: legacy columns first,
    # then trace columns (trace_id, span_id, parent_span_id, span_name,
    # span_kind), then event_data_json (always last).
    # ------------------------------------------------------------------
    def _build_http_row_legacy(self, msg: Dict[str, Any]) -> tuple:
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        s = _l7_flat_endpoint(data, "src")
        d = _l7_flat_endpoint(data, "dst")
        req_headers = data.get("request_headers")
        if req_headers is None and isinstance(data.get("request"), dict):
            req_headers = (data.get("request") or {}).get("headers")
        return (
            parse_l7_timestamp(msg.get("timestamp")),
            safe_string(msg.get("cluster_id", "")),
            safe_string(msg.get("cluster_name", "")),
            safe_string(msg.get("analysis_id", "")),
            safe_string(s["namespace"]),
            safe_string(s["workload"]),
            safe_string(s["pod"]),
            safe_string(s["ip"]),
            safe_int(s["port"], 0),
            safe_string(d["namespace"]),
            safe_string(d["workload"]),
            safe_string(d["pod"]),
            safe_string(d["ip"]),
            safe_int(d["port"], 0),
            safe_string(data.get("dst_service") or d["service_name"] or ""),
            safe_string(data.get("http_method") or data.get("method", "")),
            safe_string(data.get("http_path") or data.get("path", "")),
            safe_string(data.get("http_host") or data.get("host", "")),
            safe_int(
                data.get("http_status_code")
                if data.get("http_status_code") is not None
                else data.get("response_status"),
                0,
            ),
            safe_string(data.get("http_version", "")),
            safe_string(data.get("content_type", "")),
            safe_int(data.get("request_size", 0)),
            safe_int(data.get("response_size", 0)),
            safe_float(data.get("latency_ms") or data.get("duration_ms"), 0.0),
            _l7_labels_json(data.get("src_labels")),
            _l7_labels_json(data.get("dst_labels")),
            _l7_labels_json(req_headers),
            json.dumps(data, default=str),
        )
    
    def _build_http_row_with_trace(self, msg: Dict[str, Any]) -> tuple:
        legacy = self._build_http_row_legacy(msg)
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        # Insert trace columns before the trailing event_data_json (last element)
        trace_cols = (
            safe_string(data.get("trace_id", "")),
            safe_string(data.get("span_id", "")),
            safe_string(data.get("parent_span_id", "")),
            safe_string(data.get("span_name", "")),
            safe_int(data.get("span_kind", 0), 0),
        )
        return legacy[:-1] + trace_cols + (legacy[-1],)
    
    _INSERT_HTTP_LEGACY = """
    INSERT INTO l7_http_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        http_method, http_path, http_host, http_status_code, http_version, content_type,
        request_size, response_size, latency_ms,
        src_labels, dst_labels, request_headers,
        event_data_json
    ) VALUES
    """
    
    _INSERT_HTTP_WITH_TRACE = """
    INSERT INTO l7_http_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        http_method, http_path, http_host, http_status_code, http_version, content_type,
        request_size, response_size, latency_ms,
        src_labels, dst_labels, request_headers,
        trace_id, span_id, parent_span_id, span_name, span_kind,
        event_data_json
    ) VALUES
    """

    # Phase 4 — full INSERT including PID-temporal correlation columns.
    # Column order: legacy + trace + pid columns + event_data_json (always last).
    _INSERT_HTTP_WITH_PID = """
    INSERT INTO l7_http_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        http_method, http_path, http_host, http_status_code, http_version, content_type,
        request_size, response_size, latency_ms,
        src_labels, dst_labels, request_headers,
        trace_id, span_id, parent_span_id, span_name, span_kind,
        pid, ppid, container_id, virtual_trace_id,
        event_data_json
    ) VALUES
    """

    def _build_http_row_with_pid(self, msg: Dict[str, Any]) -> tuple:
        """Build the full row tuple including trace + PID columns.

        Reads the same `data.{trace_id, span_id, ...}` plus the new
        `data.{pid, ppid, container_id, virtual_trace_id}` fields. The
        virtual_trace_id is populated by `virtual_trace_correlator.correlate()`
        before this builder runs; events without one default to ''.
        """
        with_trace = self._build_http_row_with_trace(msg)
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        pid_cols = (
            safe_int(data.get("pid", 0), 0),
            safe_int(data.get("ppid", 0), 0),
            safe_string(data.get("container_id", "")),
            safe_string(data.get("virtual_trace_id", "")),
        )
        return with_trace[:-1] + pid_cols + (with_trace[-1],)

    def insert_l7_http_flow(self, batch: List[Dict[str, Any]]) -> int:
        """Bulk insert L7 HTTP flows into l7_http_flows.
        
        When trace columns are migrated and l7_tracing_enabled is true, includes
        trace_id/span_id/parent_span_id/span_name/span_kind. Falls back gracefully
        to legacy column list when ClickHouse reports unknown columns (handles
        deploy-order races where writer is upgraded before migration runs).

        Phase 4: when l7_pid_correlation_enabled is true AND trace columns are
        migrated, also includes pid/ppid/container_id/virtual_trace_id and
        runs the PID-temporal correlator over the batch first. Two-step
        fallback chain: PID variant → trace variant → legacy variant.
        """
        if not batch:
            return 0
        batch = _filter_l7_noise(batch, "HTTP")
        if not batch:
            return 0
        use_trace = settings.l7_tracing_enabled and self._trace_cols.get("http", True)
        use_pid = (
            use_trace
            and settings.l7_pid_correlation_enabled
            and self._pid_cols.get("http", True)
        )
        if use_pid:
            virtual_trace_correlator.correlate(
                batch,
                window_ms=settings.l7_pid_correlation_window_ms,
            )
        if use_pid:
            rows = [self._build_http_row_with_pid(m) for m in batch]
            query = self._INSERT_HTTP_WITH_PID
        elif use_trace:
            rows = [self._build_http_row_with_trace(m) for m in batch]
            query = self._INSERT_HTTP_WITH_TRACE
        else:
            rows = [self._build_http_row_legacy(m) for m in batch]
            query = self._INSERT_HTTP_LEGACY
        try:
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} l7_http_flows")
            return len(rows)
        except ClickHouseError as e:
            err_str = str(e)
            schema_miss = (
                "Unknown column" in err_str
                or "doesn't have column" in err_str
                or "No such column" in err_str
            )
            if use_pid and schema_miss:
                # PID columns not yet migrated — disable PID variant for HTTP
                # table and retry with the trace variant.
                logger.warning(
                    f"l7_http_flows pid columns missing; falling back to trace INSERT: {e}"
                )
                self._pid_cols["http"] = False
                rows_trace = [self._build_http_row_with_trace(m) for m in batch]
                try:
                    self.client.execute(self._INSERT_HTTP_WITH_TRACE, rows_trace)
                    return len(rows_trace)
                except ClickHouseError as e2:
                    err_str2 = str(e2)
                    if "Unknown column" in err_str2 or "doesn't have column" in err_str2 or "No such column" in err_str2:
                        logger.warning(
                            f"l7_http_flows trace columns also missing; falling back to legacy INSERT: {e2}"
                        )
                        self._trace_cols["http"] = False
                        rows_legacy = [self._build_http_row_legacy(m) for m in batch]
                        self.client.execute(self._INSERT_HTTP_LEGACY, rows_legacy)
                        return len(rows_legacy)
                    raise
            if use_trace and schema_miss:
                # Trace columns not yet migrated — disable for HTTP table and retry legacy
                logger.warning(
                    f"l7_http_flows trace columns missing; falling back to legacy INSERT: {e}"
                )
                self._trace_cols["http"] = False
                rows_legacy = [self._build_http_row_legacy(m) for m in batch]
                self.client.execute(self._INSERT_HTTP_LEGACY, rows_legacy)
                return len(rows_legacy)
            logger.error(f"❌ Failed to insert l7_http_flows: {e}")
            raise
    
    def _build_grpc_row_legacy(self, msg: Dict[str, Any]) -> tuple:
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        s = _l7_flat_endpoint(data, "src")
        d = _l7_flat_endpoint(data, "dst")
        status_msg = data.get("grpc_status_message")
        if status_msg is None and isinstance(data.get("response"), dict):
            status_msg = (data.get("response") or {}).get("statusText") or (
                data.get("response") or {}
            ).get("message")
        return (
            parse_l7_timestamp(msg.get("timestamp")),
            safe_string(msg.get("cluster_id", "")),
            safe_string(msg.get("cluster_name", "")),
            safe_string(msg.get("analysis_id", "")),
            safe_string(s["namespace"]),
            safe_string(s["workload"]),
            safe_string(s["pod"]),
            safe_string(s["ip"]),
            safe_int(s["port"], 0),
            safe_string(d["namespace"]),
            safe_string(d["workload"]),
            safe_string(d["pod"]),
            safe_string(d["ip"]),
            safe_int(d["port"], 0),
            safe_string(data.get("dst_service") or d["service_name"] or ""),
            safe_string(data.get("grpc_service", "")),
            safe_string(data.get("grpc_method", "")),
            safe_int(
                data.get("grpc_status_code")
                if data.get("grpc_status_code") is not None
                else data.get("response_status"),
                0,
            ),
            safe_string(status_msg or ""),
            safe_int(data.get("request_size", 0)),
            safe_int(data.get("response_size", 0)),
            safe_float(data.get("latency_ms") or data.get("duration_ms"), 0.0),
            _l7_labels_json(data.get("src_labels")),
            _l7_labels_json(data.get("dst_labels")),
            json.dumps(data, default=str),
        )
    
    def _build_grpc_row_with_trace(self, msg: Dict[str, Any]) -> tuple:
        legacy = self._build_grpc_row_legacy(msg)
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        trace_cols = (
            safe_string(data.get("trace_id", "")),
            safe_string(data.get("span_id", "")),
            safe_string(data.get("parent_span_id", "")),
            safe_string(data.get("span_name", "")),
            safe_int(data.get("span_kind", 0), 0),
        )
        return legacy[:-1] + trace_cols + (legacy[-1],)
    
    _INSERT_GRPC_LEGACY = """
    INSERT INTO l7_grpc_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        grpc_service, grpc_method, grpc_status_code, grpc_status_message,
        request_size, response_size, latency_ms,
        src_labels, dst_labels,
        event_data_json
    ) VALUES
    """
    
    _INSERT_GRPC_WITH_TRACE = """
    INSERT INTO l7_grpc_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        grpc_service, grpc_method, grpc_status_code, grpc_status_message,
        request_size, response_size, latency_ms,
        src_labels, dst_labels,
        trace_id, span_id, parent_span_id, span_name, span_kind,
        event_data_json
    ) VALUES
    """

    # Phase 4 — full INSERT including PID-temporal correlation columns.
    _INSERT_GRPC_WITH_PID = """
    INSERT INTO l7_grpc_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port, dst_service,
        grpc_service, grpc_method, grpc_status_code, grpc_status_message,
        request_size, response_size, latency_ms,
        src_labels, dst_labels,
        trace_id, span_id, parent_span_id, span_name, span_kind,
        pid, ppid, container_id, virtual_trace_id,
        event_data_json
    ) VALUES
    """

    def _build_grpc_row_with_pid(self, msg: Dict[str, Any]) -> tuple:
        """Build the full gRPC row tuple including trace + PID columns."""
        with_trace = self._build_grpc_row_with_trace(msg)
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        pid_cols = (
            safe_int(data.get("pid", 0), 0),
            safe_int(data.get("ppid", 0), 0),
            safe_string(data.get("container_id", "")),
            safe_string(data.get("virtual_trace_id", "")),
        )
        return with_trace[:-1] + pid_cols + (with_trace[-1],)

    def insert_l7_grpc_flow(self, batch: List[Dict[str, Any]]) -> int:
        """Bulk insert L7 gRPC flows into l7_grpc_flows (with trace + PID column fallback)."""
        if not batch:
            return 0
        batch = _filter_l7_noise(batch, "gRPC")
        if not batch:
            return 0
        use_trace = settings.l7_tracing_enabled and self._trace_cols.get("grpc", True)
        use_pid = (
            use_trace
            and settings.l7_pid_correlation_enabled
            and self._pid_cols.get("grpc", True)
        )
        if use_pid:
            virtual_trace_correlator.correlate(
                batch,
                window_ms=settings.l7_pid_correlation_window_ms,
            )
        if use_pid:
            rows = [self._build_grpc_row_with_pid(m) for m in batch]
            query = self._INSERT_GRPC_WITH_PID
        elif use_trace:
            rows = [self._build_grpc_row_with_trace(m) for m in batch]
            query = self._INSERT_GRPC_WITH_TRACE
        else:
            rows = [self._build_grpc_row_legacy(m) for m in batch]
            query = self._INSERT_GRPC_LEGACY
        try:
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} l7_grpc_flows")
            return len(rows)
        except ClickHouseError as e:
            err_str = str(e)
            schema_miss = (
                "Unknown column" in err_str
                or "doesn't have column" in err_str
                or "No such column" in err_str
            )
            if use_pid and schema_miss:
                logger.warning(
                    f"l7_grpc_flows pid columns missing; falling back to trace INSERT: {e}"
                )
                self._pid_cols["grpc"] = False
                rows_trace = [self._build_grpc_row_with_trace(m) for m in batch]
                try:
                    self.client.execute(self._INSERT_GRPC_WITH_TRACE, rows_trace)
                    return len(rows_trace)
                except ClickHouseError as e2:
                    err_str2 = str(e2)
                    if "Unknown column" in err_str2 or "doesn't have column" in err_str2 or "No such column" in err_str2:
                        logger.warning(
                            f"l7_grpc_flows trace columns also missing; falling back to legacy INSERT: {e2}"
                        )
                        self._trace_cols["grpc"] = False
                        rows_legacy = [self._build_grpc_row_legacy(m) for m in batch]
                        self.client.execute(self._INSERT_GRPC_LEGACY, rows_legacy)
                        return len(rows_legacy)
                    raise
            if use_trace and schema_miss:
                logger.warning(
                    f"l7_grpc_flows trace columns missing; falling back to legacy INSERT: {e}"
                )
                self._trace_cols["grpc"] = False
                rows_legacy = [self._build_grpc_row_legacy(m) for m in batch]
                self.client.execute(self._INSERT_GRPC_LEGACY, rows_legacy)
                return len(rows_legacy)
            logger.error(f"❌ Failed to insert l7_grpc_flows: {e}")
            raise
    
    def _build_dns_row_legacy(self, msg: Dict[str, Any]) -> tuple:
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        s = _l7_flat_endpoint(data, "src")
        d = _l7_flat_endpoint(data, "dst")
        resp_ips = data.get("response_ips") or data.get("answers") or []
        if isinstance(resp_ips, str):
            try:
                resp_ips = json.loads(resp_ips)
            except (json.JSONDecodeError, TypeError):
                resp_ips = [resp_ips] if resp_ips else []
        if isinstance(resp_ips, list):
            resp_ips_str = json.dumps([str(x) for x in resp_ips], default=str)
        else:
            resp_ips_str = "[]"
        return (
            parse_l7_timestamp(msg.get("timestamp")),
            safe_string(msg.get("cluster_id", "")),
            safe_string(msg.get("cluster_name", "")),
            safe_string(msg.get("analysis_id", "")),
            safe_string(s["namespace"]),
            safe_string(s["workload"]),
            safe_string(s["pod"]),
            safe_string(s["ip"]),
            safe_int(s["port"], 0),
            safe_string(d["namespace"]),
            safe_string(d["workload"]),
            safe_string(d["pod"]),
            safe_string(d["ip"]),
            safe_int(d["port"], 0),
            safe_string(data.get("query_name", "")),
            safe_string(data.get("query_type", "")),
            safe_int(data.get("response_code"), 0),
            resp_ips_str,
            safe_float(data.get("latency_ms") or data.get("duration_ms"), 0.0),
            _l7_labels_json(data.get("src_labels")),
            _l7_labels_json(data.get("dst_labels")),
            json.dumps(data, default=str),
        )
    
    def _build_dns_row_with_trace(self, msg: Dict[str, Any]) -> tuple:
        legacy = self._build_dns_row_legacy(msg)
        data = msg.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        trace_cols = (
            safe_string(data.get("trace_id", "")),
            safe_string(data.get("span_id", "")),
            safe_string(data.get("parent_span_id", "")),
            safe_string(data.get("span_name", "")),
            safe_int(data.get("span_kind", 0), 0),
        )
        return legacy[:-1] + trace_cols + (legacy[-1],)
    
    _INSERT_DNS_LEGACY = """
    INSERT INTO l7_dns_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
        query_name, query_type, response_code, response_ips,
        latency_ms,
        src_labels, dst_labels,
        event_data_json
    ) VALUES
    """
    
    _INSERT_DNS_WITH_TRACE = """
    INSERT INTO l7_dns_flows (
        timestamp, cluster_id, cluster_name, analysis_id,
        src_namespace, src_workload, src_pod, src_ip, src_port,
        dst_namespace, dst_workload, dst_pod, dst_ip, dst_port,
        query_name, query_type, response_code, response_ips,
        latency_ms,
        src_labels, dst_labels,
        trace_id, span_id, parent_span_id, span_name, span_kind,
        event_data_json
    ) VALUES
    """
    
    def insert_l7_dns_flow(self, batch: List[Dict[str, Any]]) -> int:
        """Bulk insert L7 DNS flows into l7_dns_flows (with trace column fallback)."""
        if not batch:
            return 0
        batch = _filter_l7_noise(batch, "DNS")
        if not batch:
            return 0
        use_trace = settings.l7_tracing_enabled and self._trace_cols.get("dns", True)
        rows = [
            (self._build_dns_row_with_trace(m) if use_trace else self._build_dns_row_legacy(m))
            for m in batch
        ]
        try:
            query = self._INSERT_DNS_WITH_TRACE if use_trace else self._INSERT_DNS_LEGACY
            self.client.execute(query, rows)
            logger.info(f"✅ Inserted {len(rows)} l7_dns_flows")
            return len(rows)
        except ClickHouseError as e:
            err_str = str(e)
            if use_trace and ("Unknown column" in err_str or "doesn't have column" in err_str or "No such column" in err_str):
                logger.warning(
                    f"l7_dns_flows trace columns missing; falling back to legacy INSERT: {e}"
                )
                self._trace_cols["dns"] = False
                rows_legacy = [self._build_dns_row_legacy(m) for m in batch]
                self.client.execute(self._INSERT_DNS_LEGACY, rows_legacy)
                return len(rows_legacy)
            logger.error(f"❌ Failed to insert l7_dns_flows: {e}")
            raise
    
    def close(self):
        """Close connection"""
        if self.client:
            self.client.disconnect()
            logger.info("Time-series database connection closed")

