"""Transform eBPF events to RabbitMQ messages

Supports all Inspektor Gadget v0.46.0+ event types:
- network_flow (trace_network, trace_tcpconnect, trace_tcpretrans)
- dns_query (trace_dns)
- tcp_connection (trace_tcp)
- process_event (trace_exec, trace_signal)
- file_event (trace_open, trace_write)
- security_event (trace_capabilities, seccomp)
- oom_event (trace_oomkill)
- bind_event (trace_bind)
- sni_event (trace_sni) - TLS/SSL SNI tracking
- mount_event (trace_mount) - Mount operations
"""

import uuid
from datetime import datetime
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class EventTransformer:
    """Transform raw eBPF events to structured messages for Inspektor Gadget v0.46.0+"""
    
    # Map gadget names to event types (v0.46.0+ compatible)
    GADGET_TO_EVENT_TYPE = {
        # Network gadgets - trace_tcp is used for network flow since trace_network doesn't exist
        "trace_network": "network_flow",  # Alias for backwards compatibility
        "trace_tcp": "network_flow",      # Primary gadget for network flow tracing
        "trace_tcpconnect": "network_flow",
        "trace_tcpretrans": "network_flow",
        "top_tcp": "network_flow",        # TCP throughput with bytes sent/received
        # DNS
        "trace_dns": "dns_query",
        # Process
        "trace_exec": "process_event",
        "trace_signal": "process_event",
        # File
        "trace_open": "file_event",
        "trace_write": "file_event",
        "trace_read": "file_event",
        "trace_close": "file_event",
        # Security
        "trace_capabilities": "security_event",
        "seccomp": "security_event",
        # OOM
        "trace_oomkill": "oom_event",
        "trace_bind": "bind_event",
        "trace_sni": "sni_event",
        "trace_mount": "mount_event",
        "trace_fsslower": "file_event",
    }
    
    @staticmethod
    def create_base_message(
        event_type: str,
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create base message structure with all common fields"""
        return {
            "message_id": str(uuid.uuid4()),
            "event_type": event_type,
            "cluster_id": cluster_id,
            "analysis_id": analysis_id,
            "analysis_name": analysis_name,
            "timestamp": datetime.utcnow().isoformat(),
            "scope": scope or {},
            "data": {}
        }
    
    # TCP states that indicate errors or abnormal termination
    TCP_ERROR_STATES = {
        'CLOSE_WAIT',      # Connection closed by remote (may indicate issue)
        'TIME_WAIT',       # Connection closed, waiting for cleanup
        'CLOSING',         # Both sides closing simultaneously
        'LAST_ACK',        # Waiting for final ACK after close
    }
    
    # TCP states that indicate connection reset or refused
    TCP_RESET_STATES = {
        'CLOSED',          # When transitioning unexpectedly
    }
    
    @staticmethod
    def _detect_network_error(raw_event: Dict[str, Any]) -> tuple:
        """
        Detect network errors from raw event data
        
        Returns:
            Tuple of (error_count, retransmit_count, error_type, connection_state)
        """
        error_count = raw_event.get("error_count", 0) or 0
        error_type = raw_event.get("error_type") or None  # May come from trace_tcpretrans normalization
        
        # Get retransmit count directly from event
        retransmit_count = raw_event.get("retransmits", 0) or raw_event.get("retransmit_count", 0) or 0
        
        # Get connection state
        connection_state = raw_event.get("state", "") or raw_event.get("new_state", "") or raw_event.get("connection_state", "")
        old_state = raw_event.get("old_state", "")
        
        # Check for RST flag (connection reset)
        if raw_event.get("rst", False) or raw_event.get("is_rst", False):
            error_count += 1
            error_type = "CONNECTION_RESET"
        
        # Check for connection refused (common error code)
        error_code = raw_event.get("error", 0) or raw_event.get("error_code", 0) or raw_event.get("errno", 0)
        if error_code:
            if error_code == 111:  # ECONNREFUSED
                error_count += 1
                error_type = "CONNECTION_REFUSED"
            elif error_code == 110:  # ETIMEDOUT
                error_count += 1
                error_type = "CONNECTION_TIMEOUT"
            elif error_code == 104:  # ECONNRESET
                error_count += 1
                error_type = "CONNECTION_RESET"
            elif error_code == 113:  # EHOSTUNREACH
                error_count += 1
                error_type = "HOST_UNREACHABLE"
            elif error_code == 101:  # ENETUNREACH
                error_count += 1
                error_type = "NETWORK_UNREACHABLE"
            elif error_code > 0:
                error_count += 1
                error_type = f"ERRNO_{error_code}"
        
        # Check for TCP state transitions that indicate errors
        # RST received: transition to CLOSED from established states
        if old_state in ('ESTABLISHED', 'SYN_SENT', 'SYN_RECV') and connection_state == 'CLOSED':
            if not error_type:  # Don't override more specific error
                error_count += 1
                error_type = "CONNECTION_RESET"
        
        # Retransmits are also counted as errors (network issues)
        if retransmit_count > 0:
            error_count += retransmit_count
            if not error_type:
                error_type = "RETRANSMIT"
        
        return error_count, retransmit_count, error_type, connection_state
    
    @staticmethod
    def transform_network_flow(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform network flow event
        
        Expected raw_event fields (from Inspektor Gadget):
        - namespace, pod, container, node
        - src_ip, src_port, dst_ip, dst_port
        - protocol, direction, bytes_sent, bytes_received
        - packets_sent, packets_received, duration_ms, latency_ms
        - retransmits, error, rst, state, old_state
        - pid, comm
        """
        message = EventTransformer.create_base_message(
            "network_flow",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        # Extract source pod info - may come from k8s context or src_* fields
        src_namespace = raw_event.get("src_namespace") or raw_event.get("namespace", "unknown")
        src_pod = raw_event.get("src_pod") or raw_event.get("pod", "unknown")
        src_container = raw_event.get("src_container") or raw_event.get("container", "unknown")
        
        # Detect network errors
        error_count, retransmit_count, error_type, connection_state = EventTransformer._detect_network_error(raw_event)
        
        message["data"] = {
            # K8s context (kept for backwards compatibility)
            "namespace": src_namespace,
            "pod_name": src_pod,
            "container_name": src_container,
            "node": raw_event.get("node", ""),
            # Source - explicitly set from k8s context
            "src_ip": raw_event.get("src_ip", ""),
            "src_port": raw_event.get("src_port", 0),
            "src_namespace": src_namespace,
            "src_pod": src_pod,
            "src_container": src_container,
            # Destination
            "dst_ip": raw_event.get("dst_ip", ""),
            "dst_port": raw_event.get("dst_port", 0),
            "dst_namespace": raw_event.get("dst_namespace", ""),
            "dst_pod": raw_event.get("dst_pod", ""),
            # Connection
            "protocol": raw_event.get("protocol", "TCP"),
            "direction": raw_event.get("direction", "outbound"),
            "connection_state": connection_state,
            # Metrics
            "bytes_sent": raw_event.get("bytes_sent", 0),
            "bytes_received": raw_event.get("bytes_received", 0),
            "packets_sent": raw_event.get("packets_sent", 0),
            "packets_received": raw_event.get("packets_received", 0),
            "duration_ms": raw_event.get("duration_ms", 0),
            "latency_ms": raw_event.get("latency_ms", 0.0),
            # Error metrics
            "error_count": error_count,
            "retransmit_count": retransmit_count,
            "error_type": error_type,
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
            # Labels
            "labels": raw_event.get("labels", {}),
        }
        
        return message
    
    @staticmethod
    def transform_dns_query(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform DNS query event
        
        Expected raw_event fields:
        - namespace, pod, container
        - query_name, query_type, query_class
        - response_code, answers, ttl
        - latency_ms, dns_server
        - pid, comm
        """
        message = EventTransformer.create_base_message(
            "dns_query",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            "src_ip": raw_event.get("src_ip", ""),
            # Query
            "query_name": raw_event.get("query_name", ""),
            "query_type": raw_event.get("query_type", "A"),
            "query_class": raw_event.get("query_class", "IN"),
            # Response
            "response_code": raw_event.get("response_code", "NOERROR"),
            "response_ips": raw_event.get("answers", []),
            "response_ttl": raw_event.get("ttl", 0),
            # Performance
            "latency_ms": raw_event.get("latency_ms", 0.0),
            # DNS Server
            "dns_server_ip": raw_event.get("dns_server", ""),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
        }
        
        return message
    
    @staticmethod
    def transform_tcp_connection(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform TCP connection event
        
        Expected raw_event fields:
        - namespace, pod, container
        - src_ip, src_port, dst_ip, dst_port
        - old_state, new_state
        - srtt_us, retransmits
        - pid, comm
        """
        message = EventTransformer.create_base_message(
            "tcp_connection",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        # Detect network errors
        error_count, retransmit_count, error_type, connection_state = EventTransformer._detect_network_error(raw_event)
        
        old_state = raw_event.get("old_state", "CLOSED")
        new_state = raw_event.get("new_state", "ESTABLISHED")
        
        # Additional error detection for TCP state transitions
        # RST detection: unexpected close from established state
        if old_state in ('ESTABLISHED', 'SYN_SENT', 'SYN_RECV') and new_state == 'CLOSED':
            if not error_type:
                error_count += 1
                error_type = "CONNECTION_RESET"
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            # Connection
            "src_ip": raw_event.get("src_ip", ""),
            "src_port": raw_event.get("src_port", 0),
            "dst_ip": raw_event.get("dst_ip", ""),
            "dst_port": raw_event.get("dst_port", 0),
            # State
            "old_state": old_state,
            "new_state": new_state,
            # Metrics
            "srtt_us": raw_event.get("srtt_us", 0),
            "rtt_ms": raw_event.get("srtt_us", 0) / 1000.0,  # Convert to ms
            "retransmits": raw_event.get("retransmits", 0),
            # Error metrics
            "error_count": error_count,
            "retransmit_count": retransmit_count,
            "error_type": error_type,
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
        }
        
        return message
    
    @staticmethod
    def transform_process_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform process event (exec, exit, signal)
        
        Expected raw_event fields:
        - namespace, pod, container, node
        - pid, ppid, uid, gid
        - comm, exe, args, cwd
        - event_type (exec/exit/signal)
        - exit_code, signal
        """
        message = EventTransformer.create_base_message(
            "process_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            "node": raw_event.get("node", ""),
            # Process identifiers
            "pid": raw_event.get("pid", 0),
            "ppid": raw_event.get("ppid", 0),
            "uid": raw_event.get("uid", 0),
            "gid": raw_event.get("gid", 0),
            # Command
            "comm": raw_event.get("comm", ""),
            "exe": raw_event.get("exe", ""),
            "args": raw_event.get("args", []),
            "cwd": raw_event.get("cwd", ""),
            # Event type
            "process_event_type": raw_event.get("event_type", "exec"),
            "exit_code": raw_event.get("exit_code", 0),
            "signal": raw_event.get("signal", 0),
            # Labels
            "labels": raw_event.get("labels", {}),
        }
        
        return message
    
    @staticmethod
    def transform_file_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform file event (open, read, write, close)
        
        Expected raw_event fields:
        - namespace, pod, container
        - path, operation, flags, mode
        - bytes, duration_us
        - error
        - pid, comm, uid, gid
        """
        message = EventTransformer.create_base_message(
            "file_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            # File operation
            "file_path": raw_event.get("path", ""),
            "operation": raw_event.get("operation", "open"),
            "file_flags": raw_event.get("flags", ""),
            "file_mode": raw_event.get("mode", 0),
            # Metrics
            "bytes": raw_event.get("bytes", 0),
            "duration_us": raw_event.get("duration_us", 0),
            # Result
            "error_code": raw_event.get("error", 0),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
            "uid": raw_event.get("uid", 0),
            "gid": raw_event.get("gid", 0),
        }
        
        return message
    
    @staticmethod
    def transform_security_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform security event (capability check, seccomp)
        
        Expected raw_event fields:
        - namespace, pod, container
        - event_type (capability/seccomp/selinux)
        - capability, syscall, verdict
        - pid, comm, uid
        """
        message = EventTransformer.create_base_message(
            "security_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            # Security event
            "security_event_type": raw_event.get("event_type", "capability"),
            "capability": raw_event.get("capability", ""),
            "syscall": raw_event.get("syscall", ""),
            "verdict": raw_event.get("verdict", "allowed"),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
            "uid": raw_event.get("uid", 0),
            "gid": raw_event.get("gid", 0),
        }
        
        return message
    
    @staticmethod
    def transform_oom_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform OOM kill event
        
        Expected raw_event fields:
        - namespace, pod, container, node
        - pid, comm
        - memory_limit, memory_usage
        - cgroup_path
        """
        message = EventTransformer.create_base_message(
            "oom_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            "node": raw_event.get("node", ""),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
            # Memory
            "memory_limit": raw_event.get("memory_limit", 0),
            "memory_usage": raw_event.get("memory_usage", 0),
            "memory_pages_total": raw_event.get("memory_pages_total", 0),
            "memory_pages_free": raw_event.get("memory_pages_free", 0),
            # Cgroup
            "cgroup_path": raw_event.get("cgroup_path", ""),
        }
        
        return message
    
    @staticmethod
    def transform_bind_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform socket bind event
        
        Expected raw_event fields:
        - namespace, pod, container, node
        - addr, port, protocol
        - interface
        - pid, comm, uid
        """
        message = EventTransformer.create_base_message(
            "bind_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            "node": raw_event.get("node", ""),
            # Bind details
            "bind_addr": raw_event.get("addr", "0.0.0.0"),
            "bind_port": raw_event.get("port", 0),
            "protocol": raw_event.get("protocol", "TCP"),
            "interface": raw_event.get("interface", ""),
            # Result
            "error_code": raw_event.get("error", 0),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
            "uid": raw_event.get("uid", 0),
        }
        
        return message
    
    @staticmethod
    def transform_sni_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform TLS/SSL SNI event
        
        Expected raw_event fields:
        - namespace, pod, container
        - name (SNI hostname)
        - src_ip, src_port, dst_ip, dst_port
        - pid, comm
        """
        message = EventTransformer.create_base_message(
            "sni_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            # SNI details
            "sni_name": raw_event.get("name", ""),
            # Connection
            "src_ip": raw_event.get("src_ip", ""),
            "src_port": raw_event.get("src_port", 0),
            "dst_ip": raw_event.get("dst_ip", ""),
            "dst_port": raw_event.get("dst_port", 0),
            # TLS info
            "tls_version": raw_event.get("tls_version", ""),
            "cipher_suite": raw_event.get("cipher_suite", ""),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
        }
        
        return message
    
    @staticmethod
    def transform_mount_event(
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Transform mount event
        
        Expected raw_event fields:
        - namespace, pod, container, node
        - operation (mount/umount)
        - source, target, fs_type
        - flags, options
        - pid, comm
        """
        message = EventTransformer.create_base_message(
            "mount_event",
            cluster_id,
            analysis_id,
            analysis_name,
            scope
        )
        
        message["data"] = {
            # K8s context
            "namespace": raw_event.get("namespace", "unknown"),
            "pod_name": raw_event.get("pod", "unknown"),
            "container_name": raw_event.get("container", ""),
            "node": raw_event.get("node", ""),
            # Mount details
            "operation": raw_event.get("operation", "mount"),
            "source": raw_event.get("source", ""),
            "target": raw_event.get("target", ""),
            "fs_type": raw_event.get("fs_type", ""),
            "flags": raw_event.get("flags", ""),
            "options": raw_event.get("options", ""),
            # Result
            "error_code": raw_event.get("error", 0),
            # Process
            "pid": raw_event.get("pid", 0),
            "comm": raw_event.get("comm", ""),
        }
        
        return message

    @classmethod
    def transform(
        cls,
        event_type: str,
        raw_event: Dict[str, Any],
        cluster_id: int,
        analysis_id: int,
        analysis_name: str,
        scope: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Universal transform method - routes to correct transformer based on event type
        
        Args:
            event_type: Gadget module name or event type
            raw_event: Raw event data from Gadget
            cluster_id: Cluster ID
            analysis_id: Analysis ID
            analysis_name: Analysis name
            scope: Collection scope
        
        Returns:
            Transformed message ready for RabbitMQ
        """
        # Map gadget name to event type if needed
        normalized_type = cls.GADGET_TO_EVENT_TYPE.get(event_type, event_type)
        
        # Route to correct transformer
        transformers = {
            "network_flow": cls.transform_network_flow,
            "dns_query": cls.transform_dns_query,
            "tcp_connection": cls.transform_tcp_connection,
            "process_event": cls.transform_process_event,
            "file_event": cls.transform_file_event,
            "security_event": cls.transform_security_event,
            "oom_event": cls.transform_oom_event,
            "bind_event": cls.transform_bind_event,
            "sni_event": cls.transform_sni_event,
            "mount_event": cls.transform_mount_event,
        }
        
        transformer = transformers.get(normalized_type)
        
        if transformer:
            return transformer(raw_event, cluster_id, analysis_id, analysis_name, scope)
        else:
            # Fallback: create generic message
            logger.warning(f"Unknown event type: {event_type}, creating generic message")
            message = cls.create_base_message(
                event_type,
                cluster_id,
                analysis_id,
                analysis_name,
                scope
            )
            message["data"] = raw_event
            return message

