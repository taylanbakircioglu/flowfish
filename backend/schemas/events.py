"""
Event Schemas - Request/Response DTOs
Sprint 5-6: Event statistics and queries

Pydantic models for event-related API endpoints.
Separates data transfer concerns from business logic.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class EventType(str, Enum):
    """
    Supported event types from eBPF gadgets
    
    IMPORTANT: These values MUST match frontend/src/store/api/eventsApi.ts EventType
    
    NOTE: tcp_lifecycle/tcp_connection removed - Inspektor Gadget trace_tcp doesn't
    produce TCP state transition events. TCP info is captured in network_flow.
    """
    NETWORK_FLOW = "network_flow"
    DNS_QUERY = "dns_query"
    PROCESS_EVENT = "process_event"      # Frontend: process_event
    FILE_EVENT = "file_event"            # Frontend: file_event
    SECURITY_EVENT = "security_event"    # Frontend: security_event
    OOM_EVENT = "oom_event"              # Frontend: oom_event
    BIND_EVENT = "bind_event"            # Frontend: bind_event
    SNI_EVENT = "sni_event"              # Frontend: sni_event
    MOUNT_EVENT = "mount_event"          # Frontend: mount_event


class ErrorCategory(str, Enum):
    """
    Network error categories for classification
    
    CRITICAL: Real errors requiring attention (connection failures, timeouts)
    WARNING: Normal TCP behavior, informational (retransmissions)
    """
    CRITICAL = "critical"
    WARNING = "warning"


# Error type to category mapping
# Critical errors indicate real problems that need attention
# Warnings are normal TCP behavior (retransmissions happen in healthy networks)
ERROR_CATEGORY_MAP: Dict[str, ErrorCategory] = {
    # Critical Errors (Red) - Real connection failures
    "CONNECTION_RESET": ErrorCategory.CRITICAL,
    "CONNECTION_REFUSED": ErrorCategory.CRITICAL,
    "CONNECTION_TIMEOUT": ErrorCategory.CRITICAL,
    "TIMEOUT": ErrorCategory.CRITICAL,
    "SOCKET_ERROR": ErrorCategory.CRITICAL,
    "HOST_UNREACHABLE": ErrorCategory.CRITICAL,
    "NETWORK_UNREACHABLE": ErrorCategory.CRITICAL,
    "PORT_UNREACHABLE": ErrorCategory.CRITICAL,
    
    # Warnings (Orange) - Normal TCP retransmissions
    # TCP retransmissions are normal network behavior, not errors
    # A small percentage (0.1-1%) is expected in healthy networks
    "RETRANSMIT": ErrorCategory.WARNING,
    "RETRANSMIT_RETRANS": ErrorCategory.WARNING,
    "RETRANSMIT_LOSS": ErrorCategory.WARNING,
    "RETRANSMIT_TIMEOUT": ErrorCategory.WARNING,
    "RETRANSMIT_RTO": ErrorCategory.WARNING,
}


def get_error_category(error_type: str) -> ErrorCategory:
    """Get the category for an error type, defaulting to WARNING for unknown types"""
    if not error_type:
        return ErrorCategory.WARNING
    
    # Check exact match
    if error_type in ERROR_CATEGORY_MAP:
        return ERROR_CATEGORY_MAP[error_type]
    
    # Check if it starts with RETRANSMIT (warning)
    if error_type.upper().startswith("RETRANSMIT"):
        return ErrorCategory.WARNING
    
    # Check for known critical patterns
    critical_patterns = ["RESET", "REFUSED", "TIMEOUT", "UNREACHABLE", "ERROR"]
    for pattern in critical_patterns:
        if pattern in error_type.upper():
            return ErrorCategory.CRITICAL
    
    # Default to warning for unknown types
    return ErrorCategory.WARNING


# =============================================================================
# Error Stats Response DTO
# =============================================================================

class ErrorStatsResponse(BaseModel):
    """
    Categorized network error statistics response
    
    Separates critical errors (real problems) from warnings (normal TCP behavior)
    to provide accurate health assessment.
    """
    # Total counts
    total_errors: int = Field(0, description="Total error count (critical + warnings)")
    total_critical: int = Field(0, description="Critical errors requiring attention")
    total_warnings: int = Field(0, description="Warnings (normal TCP behavior like retransmits)")
    
    # Breakdown by type
    critical_by_type: Dict[str, int] = Field(
        default_factory=dict, 
        description="Critical errors grouped by type"
    )
    warnings_by_type: Dict[str, int] = Field(
        default_factory=dict, 
        description="Warnings grouped by type"
    )
    
    # Metrics
    total_flows: int = Field(0, description="Total number of flows analyzed")
    error_rate_percent: float = Field(0.0, description="Overall error rate percentage")
    critical_rate_percent: float = Field(0.0, description="Critical error rate percentage")
    
    # Health assessment
    health_status: str = Field(
        "healthy", 
        description="Health status: healthy, good, warning, degraded, critical"
    )
    health_message: str = Field(
        "", 
        description="Human-readable health assessment message"
    )
    
    # Context
    cluster_id: Optional[int] = None
    analysis_id: Optional[int] = None
    namespace: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "total_errors": 1292,
                "total_critical": 45,
                "total_warnings": 1247,
                "critical_by_type": {
                    "CONNECTION_RESET": 30,
                    "TIMEOUT": 15
                },
                "warnings_by_type": {
                    "RETRANSMIT_RETRANS": 688,
                    "RETRANSMIT_LOSS": 559
                },
                "total_flows": 15420,
                "error_rate_percent": 8.38,
                "critical_rate_percent": 0.29,
                "health_status": "good",
                "health_message": "45 critical errors detected. Retransmit rate (8.1%) is within normal range.",
                "cluster_id": 1,
                "analysis_id": 3
            }
        }


# =============================================================================
# Request DTOs
# =============================================================================

class EventQueryParams(BaseModel):
    """Query parameters for event listing"""
    cluster_id: int = Field(..., description="Cluster ID", gt=0)
    analysis_id: Optional[int] = Field(None, description="Filter by analysis ID", gt=0)
    event_type: Optional[EventType] = Field(None, description="Filter by event type")
    namespace: Optional[str] = Field(None, description="Filter by namespace", max_length=253)
    pod: Optional[str] = Field(None, description="Filter by pod name", max_length=253)
    search: Optional[str] = Field(None, description="Full-text search across relevant fields", max_length=500)
    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class EventStatsParams(BaseModel):
    """Query parameters for event statistics"""
    cluster_id: int = Field(..., description="Cluster ID", gt=0)
    analysis_id: Optional[int] = Field(None, description="Filter by analysis ID", gt=0)


# =============================================================================
# Response DTOs - Nested Objects
# =============================================================================

class TimeRange(BaseModel):
    """Time range for event data"""
    start: Optional[str] = Field(None, description="Start timestamp")
    end: Optional[str] = Field(None, description="End timestamp")


class NamespaceCount(BaseModel):
    """Namespace with event count"""
    namespace: str
    count: int


class PodCount(BaseModel):
    """Pod with event count"""
    pod: str
    namespace: str
    count: int


# =============================================================================
# Response DTOs - Main Objects
# =============================================================================

class EventStats(BaseModel):
    """
    Event statistics response
    
    MUST match frontend/src/store/api/eventsApi.ts EventStats interface
    """
    cluster_id: str
    analysis_id: str = ""  # Empty string instead of null for frontend compatibility
    total_events: int = Field(0, description="Total number of events")
    event_counts: Dict[str, int] = Field(
        default_factory=dict, 
        description="Count per event type (keys match frontend EventType)"
    )
    time_range: TimeRange = Field(
        default_factory=lambda: TimeRange(),
        description="Time range of collected events"
    )
    top_namespaces: List[NamespaceCount] = Field(
        default_factory=list,
        description="Top namespaces by event count"
    )
    top_pods: List[PodCount] = Field(
        default_factory=list,
        description="Top pods by event count"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "cluster_id": "1",
                "analysis_id": "3",
                "total_events": 15420,
                "event_counts": {
                    "network_flow": 8500,
                    "dns_query": 3200,
                    "process_event": 2100,
                    "sni_event": 1620
                },
                "time_range": {
                    "start": "2025-11-27T10:00:00Z",
                    "end": "2025-11-27T16:00:00Z"
                },
                "top_namespaces": [
                    {"namespace": "flowfish", "count": 5000},
                    {"namespace": "default", "count": 2000}
                ],
                "top_pods": [
                    {"pod": "api-gateway-abc123", "namespace": "flowfish", "count": 1500}
                ]
            }
        }


class Event(BaseModel):
    """Single event record"""
    id: str = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Type of event")
    timestamp: datetime = Field(..., description="Event timestamp")
    cluster_id: int
    analysis_id: Optional[int] = None
    namespace: str = Field("", description="Kubernetes namespace")
    pod_name: str = Field("", description="Pod name")
    container: Optional[str] = Field(None, description="Container name")
    node: Optional[str] = Field(None, description="Node name")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific data")


class EventsListResponse(BaseModel):
    """Paginated events list response"""
    events: List[Event]
    total: int
    offset: int
    limit: int
    has_more: bool = False


class DnsQueryEvent(BaseModel):
    """
    DNS query event
    
    MUST match frontend/src/store/api/eventsApi.ts DnsQueryEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "dns_query"
    cluster_id: str  # Frontend expects string
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""  # Frontend expects string
    namespace: str = ""
    pod: str = ""  # Frontend uses 'pod', not 'pod_name'
    container: Optional[str] = None
    query_name: str = ""
    query_type: str = ""
    response_code: str = ""
    response_ips: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    dns_server_ip: str = ""


class DnsQueriesResponse(BaseModel):
    """DNS queries list response"""
    queries: List[DnsQueryEvent]
    total: int


class SniEvent(BaseModel):
    """
    TLS/SNI event
    
    MUST match frontend/src/store/api/eventsApi.ts SniEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "sni_event"
    cluster_id: str  # Frontend expects string
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""  # Frontend expects string
    namespace: str = ""
    pod: str = ""  # Frontend uses 'pod', not 'pod_name'
    container: Optional[str] = None
    server_name: str = ""  # TLS SNI hostname
    src_ip: Optional[str] = None  # Source IP (from ClickHouse)
    src_port: Optional[int] = None  # Source port
    dest_ip: str = ""  # Destination IP
    dest_port: int = 0  # Destination port
    tls_version: str = ""
    cipher_suite: str = ""
    pid: Optional[int] = None  # Process ID
    comm: Optional[str] = None  # Command name


class SniEventsResponse(BaseModel):
    """SNI events list response"""
    events: List[SniEvent]
    total: int


# =============================================================================
# Process Event Schemas
# =============================================================================

class ProcessEvent(BaseModel):
    """
    Process execution event
    
    MUST match frontend/src/store/api/eventsApi.ts ProcessEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "process_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    pid: int = 0
    ppid: int = 0
    comm: str = ""
    exe: str = ""
    args: List[str] = Field(default_factory=list)
    event_subtype: str = "exec"  # exec, exit, signal
    exit_code: Optional[int] = None
    signal: Optional[int] = None
    uid: int = 0
    gid: int = 0


class ProcessEventsResponse(BaseModel):
    """Process events list response"""
    events: List[ProcessEvent]
    total: int


# =============================================================================
# File Event Schemas
# =============================================================================

class FileEvent(BaseModel):
    """
    File operation event
    
    MUST match frontend/src/store/api/eventsApi.ts FileEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "file_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    operation: str = ""  # open, read, write, close, unlink, rename
    file_path: str = ""
    file_flags: str = ""
    file_mode: int = 0
    bytes: int = 0
    duration_us: int = 0
    error_code: int = 0
    pid: int = 0
    comm: str = ""
    uid: int = 0
    gid: int = 0


class FileEventsResponse(BaseModel):
    """File events list response"""
    events: List[FileEvent]
    total: int


# =============================================================================
# Security Event Schemas
# =============================================================================

class SecurityEvent(BaseModel):
    """
    Security/capability check event
    
    MUST match frontend/src/store/api/eventsApi.ts SecurityEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "security_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    security_type: str = "capability"  # capability, seccomp, selinux
    capability: Optional[str] = None
    syscall: Optional[str] = None
    verdict: str = "allowed"  # allowed, denied
    pid: int = 0
    comm: str = ""
    uid: int = 0
    gid: int = 0


class SecurityEventsResponse(BaseModel):
    """Security events list response"""
    events: List[SecurityEvent]
    total: int


# =============================================================================
# OOM Event Schemas
# =============================================================================

class OomEvent(BaseModel):
    """
    OOM kill event
    
    MUST match frontend/src/store/api/eventsApi.ts OomEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "oom_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    node: Optional[str] = None
    pid: int = 0
    comm: str = ""
    memory_limit: int = 0
    memory_usage: int = 0
    memory_pages_total: int = 0
    memory_pages_free: int = 0
    cgroup_path: str = ""


class OomEventsResponse(BaseModel):
    """OOM events list response"""
    events: List[OomEvent]
    total: int


# =============================================================================
# Bind Event Schemas
# =============================================================================

class BindEvent(BaseModel):
    """
    Socket bind event
    
    MUST match frontend/src/store/api/eventsApi.ts BindEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "bind_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    node: Optional[str] = None
    bind_addr: str = ""
    bind_port: int = 0
    protocol: str = "TCP"
    interface: str = ""
    error_code: int = 0
    pid: int = 0
    comm: str = ""
    uid: int = 0


class BindEventsResponse(BaseModel):
    """Bind events list response"""
    events: List[BindEvent]
    total: int


# =============================================================================
# Mount Event Schemas
# =============================================================================

class MountEvent(BaseModel):
    """
    Filesystem mount event
    
    MUST match frontend/src/store/api/eventsApi.ts MountEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "mount_event"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    node: Optional[str] = None
    operation: str = "mount"  # mount, umount
    source: str = ""
    target: str = ""
    fs_type: str = ""
    flags: str = ""
    options: str = ""
    error_code: int = 0
    pid: int = 0
    comm: str = ""


class MountEventsResponse(BaseModel):
    """Mount events list response"""
    events: List[MountEvent]
    total: int


# =============================================================================
# Network Flow Event Schemas
# =============================================================================

class NetworkFlowEvent(BaseModel):
    """
    Network flow event
    
    MUST match frontend/src/store/api/eventsApi.ts NetworkFlowEvent interface
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "network_flow"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    source_ip: str = ""
    source_port: int = 0
    dest_ip: str = ""
    dest_port: int = 0
    protocol: str = "TCP"
    direction: str = "outbound"
    bytes_sent: int = 0
    bytes_received: int = 0
    latency_ms: float = 0.0
    connection_state: str = ""
    # Error fields - from ClickHouse network_flows table
    error_count: int = 0
    retransmit_count: int = 0
    error_type: Optional[str] = None


class NetworkFlowsResponse(BaseModel):
    """Network flows list response"""
    events: List[NetworkFlowEvent]
    total: int


# =============================================================================
# TCP Connection Event Schemas (DEPRECATED)
# NOTE: Inspektor Gadget trace_tcp doesn't produce TCP state transition events
# (oldstate/newstate). TCP connection info is captured in NetworkFlowEvent.
# These schemas are kept for backward compatibility but are not actively used.
# =============================================================================

class TcpConnectionEvent(BaseModel):
    """
    TCP lifecycle event (DEPRECATED - not produced by Inspektor Gadget)
    TCP connection events are now part of NetworkFlowEvent
    """
    timestamp: datetime
    event_id: str = ""
    event_type: str = "tcp_connection"
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    source_ip: str = ""
    source_port: int = 0
    dest_ip: str = ""
    dest_port: int = 0
    old_state: str = ""
    new_state: str = ""
    pid: int = 0
    comm: str = ""


class TcpConnectionsResponse(BaseModel):
    """TCP connections list response (DEPRECATED)"""
    events: List[TcpConnectionEvent]
    total: int


# =============================================================================
# Generic Events Response (for unified endpoint)
# =============================================================================

class GenericEvent(BaseModel):
    """Generic event for unified events endpoint"""
    timestamp: datetime
    event_id: str = ""
    event_type: str
    cluster_id: str
    cluster_name: Optional[str] = None  # Cluster display name for multi-cluster visibility
    analysis_id: str = ""
    namespace: str = ""
    pod: str = ""
    container: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    details: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class GenericEventsResponse(BaseModel):
    """Generic events list response"""
    events: List[GenericEvent]
    total: int
    has_more: bool = False

