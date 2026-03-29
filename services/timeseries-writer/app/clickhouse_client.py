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
    
    def close(self):
        """Close connection"""
        if self.client:
            self.client.disconnect()
            logger.info("Time-series database connection closed")

