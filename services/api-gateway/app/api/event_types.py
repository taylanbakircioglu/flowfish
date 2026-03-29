"""
Event Types API Endpoints
Metadata for Inspector Gadget event types
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/event-types", tags=["event-types"])


# =============================================================================
# ENUMS & MODELS
# =============================================================================

class EventCategory(str, Enum):
    NETWORK = "network"
    DNS = "dns"
    PROCESS = "process"
    FILE = "file"
    SECURITY = "security"
    RESOURCE = "resource"


class EventField(BaseModel):
    name: str
    label: str
    type: str  # string, number, float, enum, array, map
    filterable: bool = False
    aggregatable: bool = False
    enum_values: Optional[List[str]] = None


class EventTypeDefinition(BaseModel):
    id: str
    name: str
    description: str
    category: EventCategory
    gadget_name: str
    table_name: str
    default_enabled: bool
    icon: str
    color: str
    fields: List[EventField]


class EventTypeListResponse(BaseModel):
    event_types: List[EventTypeDefinition]
    total: int


# =============================================================================
# EVENT TYPE DEFINITIONS (Hardcoded metadata)
# =============================================================================

EVENT_TYPES: List[EventTypeDefinition] = [
    EventTypeDefinition(
        id="network_flow",
        name="Network Flows",
        description="TCP/UDP connection tracking with metrics",
        category=EventCategory.NETWORK,
        gadget_name="network",
        table_name="network_flows",
        default_enabled=True,
        icon="network",
        color="#1890ff",
        fields=[
            EventField(name="source_pod", label="Source Pod", type="string", filterable=True),
            EventField(name="dest_pod", label="Destination Pod", type="string", filterable=True),
            EventField(name="dest_port", label="Port", type="number", filterable=True),
            EventField(name="protocol", label="Protocol", type="enum", enum_values=["TCP", "UDP", "ICMP"]),
            EventField(name="bytes_sent", label="Bytes Sent", type="number", aggregatable=True),
            EventField(name="bytes_received", label="Bytes Received", type="number", aggregatable=True),
            EventField(name="latency_ms", label="Latency (ms)", type="float", aggregatable=True),
        ]
    ),
    EventTypeDefinition(
        id="dns_query",
        name="DNS Queries",
        description="DNS resolution tracking with latency",
        category=EventCategory.DNS,
        gadget_name="dns",
        table_name="dns_queries",
        default_enabled=True,
        icon="search",
        color="#52c41a",
        fields=[
            EventField(name="query_name", label="Domain", type="string", filterable=True),
            EventField(name="query_type", label="Query Type", type="enum", enum_values=["A", "AAAA", "CNAME", "MX"]),
            EventField(name="response_code", label="Response", type="enum", enum_values=["NOERROR", "NXDOMAIN", "SERVFAIL"]),
            EventField(name="latency_ms", label="Latency (ms)", type="float", aggregatable=True),
        ]
    ),
    EventTypeDefinition(
        id="tcp_throughput",
        name="TCP Throughput",
        description="TCP connection throughput with bytes sent/received",
        category=EventCategory.NETWORK,
        gadget_name="top_tcp",
        table_name="network_flows",
        default_enabled=True,
        icon="dashboard",
        color="#13c2c2",
        fields=[
            EventField(name="source_pod", label="Source Pod", type="string", filterable=True),
            EventField(name="dest_pod", label="Destination Pod", type="string", filterable=True),
            EventField(name="bytes_sent", label="Bytes Sent", type="number", aggregatable=True),
            EventField(name="bytes_received", label="Bytes Received", type="number", aggregatable=True),
        ]
    ),
    EventTypeDefinition(
        id="tcp_retransmit",
        name="TCP Retransmit",
        description="TCP retransmission events for network error detection",
        category=EventCategory.NETWORK,
        gadget_name="trace_tcpretrans",
        table_name="network_flows",
        default_enabled=True,
        icon="warning",
        color="#fa8c16",
        fields=[
            EventField(name="source_pod", label="Source Pod", type="string", filterable=True),
            EventField(name="dest_pod", label="Destination Pod", type="string", filterable=True),
            EventField(name="retransmit_count", label="Retransmits", type="number", aggregatable=True),
            EventField(name="error_type", label="Error Type", type="string", filterable=True),
        ]
    ),
    EventTypeDefinition(
        id="process_exec",
        name="Process Execution",
        description="Process creation and termination",
        category=EventCategory.PROCESS,
        gadget_name="exec",
        table_name="process_events",
        default_enabled=False,
        icon="code",
        color="#722ed1",
        fields=[
            EventField(name="comm", label="Command", type="string", filterable=True),
            EventField(name="exe", label="Executable", type="string", filterable=True),
            EventField(name="args", label="Arguments", type="array"),
            EventField(name="uid", label="User ID", type="number"),
            EventField(name="event_type", label="Event Type", type="enum", enum_values=["exec", "exit", "signal"]),
        ]
    ),
    EventTypeDefinition(
        id="file_operations",
        name="File Operations",
        description="File system read/write tracking",
        category=EventCategory.FILE,
        gadget_name="open",
        table_name="file_operations",
        default_enabled=False,
        icon="file",
        color="#eb2f96",
        fields=[
            EventField(name="operation", label="Operation", type="enum", enum_values=["open", "read", "write", "close", "unlink"]),
            EventField(name="file_path", label="File Path", type="string", filterable=True),
            EventField(name="bytes", label="Bytes", type="number", aggregatable=True),
            EventField(name="duration_us", label="Duration (μs)", type="number", aggregatable=True),
        ]
    ),
    EventTypeDefinition(
        id="capability_checks",
        name="Capability Checks",
        description="Linux capability permission checks",
        category=EventCategory.SECURITY,
        gadget_name="capabilities",
        table_name="capability_checks",
        default_enabled=False,
        icon="shield",
        color="#fa541c",
        fields=[
            EventField(name="capability", label="Capability", type="string", filterable=True),
            EventField(name="verdict", label="Verdict", type="enum", enum_values=["allowed", "denied"]),
            EventField(name="syscall", label="Syscall", type="string"),
        ]
    ),
    EventTypeDefinition(
        id="oom_kills",
        name="OOM Kills",
        description="Out of memory kill events",
        category=EventCategory.RESOURCE,
        gadget_name="oomkill",
        table_name="oom_kills",
        default_enabled=True,
        icon="warning",
        color="#f5222d",
        fields=[
            EventField(name="comm", label="Process", type="string"),
            EventField(name="memory_limit", label="Memory Limit (bytes)", type="number"),
            EventField(name="memory_usage", label="Memory Usage (bytes)", type="number"),
        ]
    ),
]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("", response_model=EventTypeListResponse)
async def list_event_types(
    category: Optional[EventCategory] = None,
    default_enabled_only: bool = False
):
    """
    Get all supported event types with metadata
    
    Use this endpoint to populate the event type selector in the analysis wizard.
    """
    logger.info(f"Listing event types (category={category}, default_only={default_enabled_only})")
    
    # Filter by category
    filtered_types = EVENT_TYPES
    
    if category:
        filtered_types = [et for et in filtered_types if et.category == category]
    
    if default_enabled_only:
        filtered_types = [et for et in filtered_types if et.default_enabled]
    
    return EventTypeListResponse(
        event_types=filtered_types,
        total=len(filtered_types)
    )


@router.get("/{event_type_id}", response_model=EventTypeDefinition)
async def get_event_type(event_type_id: str):
    """Get detailed information about a specific event type"""
    logger.info(f"Getting event type: {event_type_id}")
    
    event_type = next((et for et in EVENT_TYPES if et.id == event_type_id), None)
    
    if not event_type:
        raise HTTPException(
            status_code=404,
            detail=f"Event type '{event_type_id}' not found"
        )
    
    return event_type


@router.get("/categories/list")
async def list_categories():
    """Get list of all event categories"""
    return {
        "categories": [
            {"value": cat.value, "label": cat.value.title()}
            for cat in EventCategory
        ]
    }


@router.get("/gadgets/mapping")
async def get_gadget_mapping():
    """
    Get mapping between Inspector Gadget names and event types
    
    Useful for configuring Gadget trace commands.
    """
    mapping = {}
    
    for event_type in EVENT_TYPES:
        gadget_name = event_type.gadget_name
        if gadget_name not in mapping:
            mapping[gadget_name] = []
        mapping[gadget_name].append(event_type.id)
    
    return {
        "gadget_to_event_types": mapping,
        "description": "Maps Inspector Gadget names to Flowfish event types"
    }

