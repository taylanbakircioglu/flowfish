"""
Event Types router - Inspector Gadget event types metadata
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict
import structlog

logger = structlog.get_logger()

router = APIRouter()

# Event type metadata - matches Inspector Gadget v0.46.0+ gadgets
# IMPORTANT: These IDs must match frontend EventType definitions
EVENT_TYPES = [
    {
        "id": "network_flow",
        "name": "Network Flow",
        "display_name": "Network Flow",
        "description": "Captures network traffic between pods, including connection details, protocols, and data volumes",
        "category": "network",
        "gadget_name": "trace_network",
        "gadget_command": "kubectl-gadget trace network",
        "performance_impact": "medium",
        "data_volume": "high",
        "recommended_duration": "5-30 minutes",
        "use_cases": [
            "Service communication mapping",
            "Network traffic analysis",
            "Bandwidth monitoring",
            "Dependency discovery"
        ],
        "collected_metrics": [
            "source_ip", "dest_ip", "source_port", "dest_port",
            "protocol", "bytes_sent", "bytes_received", "connection_duration"
        ],
        "status": "available"
    },
    {
        "id": "dns_query",
        "name": "DNS Query",
        "display_name": "DNS Query",
        "description": "Monitors DNS queries and responses to understand service discovery and external dependencies",
        "category": "network",
        "gadget_name": "trace_dns",
        "gadget_command": "kubectl-gadget trace dns",
        "performance_impact": "low",
        "data_volume": "medium",
        "recommended_duration": "10-60 minutes",
        "use_cases": [
            "External service discovery",
            "DNS resolution tracking",
            "Service mesh analysis",
            "Troubleshooting connectivity"
        ],
        "collected_metrics": [
            "query_name", "query_type", "response_code",
            "resolved_ips", "latency", "nameserver"
        ],
        "status": "available"
    },
    # NOTE: tcp_lifecycle removed - Inspektor Gadget trace_tcp doesn't produce
    # TCP state transition events (oldstate/newstate). TCP connection info is
    # captured in network_flows via connect/accept/close events instead.
    {
        "id": "tcp_throughput",
        "name": "TCP Throughput",
        "display_name": "TCP Throughput",
        "description": "Measures TCP connection throughput with bytes sent/received per connection. Required for 'Data Transferred' metrics.",
        "category": "network",
        "gadget_name": "top_tcp",
        "gadget_command": "kubectl-gadget run top_tcp:latest",
        "performance_impact": "low",
        "data_volume": "medium",
        "recommended_duration": "5-60 minutes",
        "use_cases": [
            "Bandwidth monitoring",
            "Data transfer analysis",
            "Traffic volume tracking",
            "Network capacity planning"
        ],
        "collected_metrics": [
            "source_ip", "dest_ip", "source_port", "dest_port",
            "bytes_sent", "bytes_received", "protocol"
        ],
        "status": "available"
    },
    {
        "id": "tcp_retransmit",
        "name": "TCP Retransmit",
        "display_name": "TCP Retransmit/Errors",
        "description": "Captures TCP retransmission events indicating network errors, packet loss, or congestion. Required for 'Network Errors' metrics.",
        "category": "network",
        "gadget_name": "trace_tcpretrans",
        "gadget_command": "kubectl-gadget trace tcpretrans",
        "performance_impact": "low",
        "data_volume": "low",
        "recommended_duration": "15-120 minutes",
        "use_cases": [
            "Network error detection",
            "Packet loss monitoring",
            "Connection quality analysis",
            "Troubleshooting network issues"
        ],
        "collected_metrics": [
            "source_ip", "dest_ip", "source_port", "dest_port",
            "state", "retransmit_count", "error_type"
        ],
        "status": "available"
    },
    {
        "id": "process_exec",
        "name": "Process Execution",
        "display_name": "Process Execution",
        "description": "Captures process execution events within containers",
        "category": "process",
        "gadget_name": "trace_exec",
        "gadget_command": "kubectl-gadget trace exec",
        "performance_impact": "low",
        "data_volume": "medium",
        "recommended_duration": "15-60 minutes",
        "use_cases": [
            "Security monitoring",
            "Container activity tracking",
            "Command execution audit",
            "Anomaly detection"
        ],
        "collected_metrics": [
            "process_name", "command_line", "pid", "parent_pid",
            "user", "exit_code", "execution_time"
        ],
        "status": "available"
    },
    {
        "id": "file_operations",
        "name": "File Operations",
        "display_name": "File Operations",
        "description": "Monitors file system operations (open, read, write, delete)",
        "category": "filesystem",
        "gadget_name": "trace_open",
        "gadget_command": "kubectl-gadget trace open",
        "performance_impact": "medium",
        "data_volume": "high",
        "recommended_duration": "5-15 minutes",
        "use_cases": [
            "Configuration file monitoring",
            "Data access patterns",
            "Security audit",
            "I/O performance analysis"
        ],
        "collected_metrics": [
            "file_path", "operation_type", "flags", "mode",
            "process_name", "pid", "return_value"
        ],
        "status": "available"
    },
    {
        "id": "capability_checks",
        "name": "Capability Checks",
        "display_name": "Capability Checks",
        "description": "Tracks Linux capability checks for privilege escalation detection",
        "category": "security",
        "gadget_name": "trace_capabilities",
        "gadget_command": "kubectl-gadget trace capabilities",
        "performance_impact": "low",
        "data_volume": "low",
        "recommended_duration": "30-120 minutes",
        "use_cases": [
            "Security compliance",
            "Privilege escalation detection",
            "Container security audit",
            "Least privilege verification"
        ],
        "collected_metrics": [
            "capability_name", "syscall", "process_name",
            "pid", "uid", "audit_result"
        ],
        "status": "available"
    },
    {
        "id": "oom_kills",
        "name": "OOM Kills",
        "display_name": "OOM Kills",
        "description": "Captures Out-of-Memory kill events for resource management analysis",
        "category": "resource",
        "gadget_name": "trace_oomkill",
        "gadget_command": "kubectl-gadget trace oomkill",
        "performance_impact": "low",
        "data_volume": "low",
        "recommended_duration": "Always-on recommended",
        "use_cases": [
            "Resource limit tuning",
            "Memory leak detection",
            "Capacity planning",
            "Stability monitoring"
        ],
        "collected_metrics": [
            "killed_process", "killed_pid", "triggered_by_pid",
            "pages_used", "memory_limit"
        ],
        "status": "available"
    },
    {
        "id": "bind_events",
        "name": "Socket Bind",
        "display_name": "Socket Bind Events",
        "description": "Tracks socket bind events to discover listening ports and services",
        "category": "network",
        "gadget_name": "trace_bind",
        "gadget_command": "kubectl-gadget trace bind",
        "performance_impact": "low",
        "data_volume": "low",
        "recommended_duration": "15-60 minutes",
        "use_cases": [
            "Service port discovery",
            "Detect unauthorized listeners",
            "Network policy validation",
            "Service inventory"
        ],
        "collected_metrics": [
            "bind_address", "bind_port", "protocol",
            "process_name", "pid", "interface"
        ],
        "status": "available"
    },
    {
        "id": "sni_events",
        "name": "TLS/SNI",
        "display_name": "TLS/SNI Events",
        "description": "Captures TLS Server Name Indication for encrypted traffic analysis",
        "category": "network",
        "gadget_name": "trace_sni",
        "gadget_command": "kubectl-gadget trace sni",
        "performance_impact": "low",
        "data_volume": "medium",
        "recommended_duration": "10-60 minutes",
        "use_cases": [
            "HTTPS connection tracking",
            "External API dependencies",
            "Certificate validation",
            "Encrypted traffic visibility"
        ],
        "collected_metrics": [
            "server_name", "destination_ip", "destination_port",
            "tls_version", "cipher_suite"
        ],
        "status": "available"
    },
    {
        "id": "mount_events",
        "name": "Mount Events",
        "display_name": "Filesystem Mounts",
        "description": "Tracks filesystem mount and unmount operations",
        "category": "filesystem",
        "gadget_name": "trace_mount",
        "gadget_command": "kubectl-gadget trace mount",
        "performance_impact": "low",
        "data_volume": "low",
        "recommended_duration": "30-120 minutes",
        "use_cases": [
            "Volume mount tracking",
            "Security audit",
            "Container escape detection",
            "Storage monitoring"
        ],
        "collected_metrics": [
            "source", "target", "fs_type",
            "mount_options", "operation"
        ],
        "status": "available"
    }
]


@router.get("/event-types")
async def get_event_types():
    """Get all available event types"""
    try:
        logger.info("Retrieved event types", count=len(EVENT_TYPES))
        # Return array directly (frontend expects EventType[])
        return EVENT_TYPES
    except Exception as e:
        logger.error("Get event types failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve event types: {str(e)}"
        )


@router.get("/event-types/{event_type_id}")
async def get_event_type(event_type_id: str):
    """Get specific event type by ID"""
    try:
        event_type = next((et for et in EVENT_TYPES if et["id"] == event_type_id), None)
        
        if not event_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event type '{event_type_id}' not found"
            )
        
        return event_type
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get event type failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve event type: {str(e)}"
        )


@router.get("/event-types/categories/list")
async def get_event_type_categories():
    """Get all event type categories"""
    try:
        # Group event types by category
        categories_map = {}
        for et in EVENT_TYPES:
            cat = et["category"]
            if cat not in categories_map:
                categories_map[cat] = {
                    "category": cat,
                    "display_name": cat.replace("_", " ").title(),
                    "event_types": []
                }
            categories_map[cat]["event_types"].append(et["id"])
        
        # Return array directly (frontend expects EventTypeCategory[])
        return list(categories_map.values())
        
    except Exception as e:
        logger.error("Get categories failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve categories: {str(e)}"
        )


@router.get("/event-types/gadgets/mapping")
async def get_gadget_mapping():
    """Get mapping of event types to Inspector Gadget names"""
    try:
        mapping = {et["id"]: et["gadget_name"] for et in EVENT_TYPES}
        
        return {
            "mapping": mapping,
            "count": len(mapping)
        }
        
    except Exception as e:
        logger.error("Get gadget mapping failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve gadget mapping: {str(e)}"
        )

