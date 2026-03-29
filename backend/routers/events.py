"""
Events Router - API Controller Layer
Sprint 5-6: Event statistics and queries

This is a thin controller layer that handles:
- HTTP request/response
- Input validation (via Pydantic schemas)
- Dependency injection
- Error handling with appropriate HTTP status codes

Business logic is delegated to EventService.
Data access is delegated to EventRepository via Service.

Follows Clean Architecture / Layered Architecture principles.

**Multi-Cluster Support (Sprint 7):**
- cluster_ids parameter for filtering events from multiple clusters
- Automatic cluster_ids resolution from analysis_id
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional, List
import structlog
import json

from utils.jwt_utils import get_current_user
from schemas.events import (
    EventStats,
    DnsQueriesResponse,
    SniEventsResponse,
    ProcessEventsResponse,
    FileEventsResponse,
    SecurityEventsResponse,
    OomEventsResponse,
    BindEventsResponse,
    MountEventsResponse,
    NetworkFlowsResponse,
    TcpConnectionsResponse,
    GenericEventsResponse,
)
from services.event_service import EventService, get_event_service
from database.postgresql import database

logger = structlog.get_logger(__name__)
router = APIRouter()


# =============================================================================
# Multi-Cluster Helper
# =============================================================================

async def resolve_cluster_ids(
    cluster_id: Optional[int] = None,
    cluster_ids: Optional[str] = None,
    analysis_id: Optional[int] = None
) -> List[int]:
    """
    Resolve cluster IDs from various sources.
    
    Priority:
    1. cluster_ids parameter (comma-separated)
    2. cluster_id parameter (single)
    3. analysis_id -> lookup cluster_ids from analysis
    
    Returns list of cluster IDs to query.
    """
    # Parse cluster_ids if provided
    if cluster_ids:
        try:
            return [int(cid.strip()) for cid in cluster_ids.split(",") if cid.strip()]
        except ValueError:
            pass
    
    # Single cluster_id
    if cluster_id:
        return [cluster_id]
    
    # Resolve from analysis
    if analysis_id:
        query = "SELECT cluster_id, cluster_ids, is_multi_cluster FROM analyses WHERE id = :id"
        result = await database.fetch_one(query, {"id": analysis_id})
        if result:
            if result["is_multi_cluster"] and result["cluster_ids"]:
                ids = result["cluster_ids"]
                if isinstance(ids, str):
                    ids = json.loads(ids)
                return ids
            return [result["cluster_id"]]
    
    return []


# =============================================================================
# Dependency Injection
# =============================================================================

def get_service() -> EventService:
    """
    Dependency provider for EventService
    
    Allows easy mocking in tests by overriding this dependency.
    """
    return get_event_service()


# =============================================================================
# API Endpoints
# =============================================================================

@router.get(
    "/stats",
    response_model=EventStats,
    summary="Get Event Statistics",
    description="""
    Get comprehensive event statistics for a cluster or specific analysis.
    
    **Multi-Cluster Support:**
    - Use cluster_ids (comma-separated) to get stats from multiple clusters
    - Or provide analysis_id to auto-resolve cluster_ids from multi-cluster analysis
    
    Returns:
    - Total event count
    - Event counts grouped by type (network_flow, dns_query, etc.)
    - Time range of collected events
    - Top namespaces by event count
    - Top pods by event count
    
    **Sprint 5-6 Feature, Multi-Cluster (Sprint 7)**
    """,
    responses={
        200: {"description": "Event statistics retrieved successfully"},
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"}
    }
)
async def get_event_stats(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    cluster_ids: Optional[str] = Query(None, description="Comma-separated cluster IDs for multi-cluster"),
    analysis_id: Optional[int] = Query(None, description="Filter by specific analysis", gt=0),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> EventStats:
    """
    Get event statistics endpoint
    
    Path: GET /api/v1/events/stats
    Query Params:
        - cluster_id (required): Primary cluster to get stats for
        - cluster_ids (optional): Comma-separated IDs for multi-cluster queries
        - analysis_id (optional): Filter by analysis (auto-resolves cluster_ids)
    """
    try:
        # Resolve cluster IDs for multi-cluster support
        resolved_ids = await resolve_cluster_ids(cluster_id, cluster_ids, analysis_id)
        primary_cluster = resolved_ids[0] if resolved_ids else cluster_id
        
        # For now, use primary cluster for stats (can be enhanced for aggregation)
        stats = await service.get_event_stats(
            cluster_id=primary_cluster,
            analysis_id=analysis_id
        )
        return stats
        
    except Exception as e:
        logger.error(
            "Failed to get event stats",
            error=str(e),
            cluster_id=cluster_id,
            cluster_ids=cluster_ids,
            analysis_id=analysis_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve event statistics: {str(e)}"
        )


@router.get(
    "/dns",
    response_model=DnsQueriesResponse,
    summary="Get DNS Query Events",
    description="""
    Get DNS query events from eBPF trace_dns gadget.
    
    Returns DNS lookups made by pods including:
    - Query name (domain)
    - Query type (A, AAAA, CNAME, etc.)
    - Response code
    - Resolved IP addresses
    - Latency
    
    **Search:** Full-text search across query_name, dns_server_ip, pod, namespace
    
    **Sprint 5-6 Feature**
    """
)
async def get_dns_queries(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> DnsQueriesResponse:
    """
    Get DNS queries endpoint
    
    Path: GET /api/v1/events/dns
    """
    try:
        response = await service.get_dns_queries(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        return response
        
    except Exception as e:
        logger.error(
            "Failed to get DNS queries",
            error=str(e),
            cluster_id=cluster_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve DNS queries: {str(e)}"
        )


@router.get(
    "/sni",
    response_model=SniEventsResponse,
    summary="Get TLS/SNI Events",
    description="""
    Get TLS Server Name Indication (SNI) events from eBPF trace_sni gadget.
    
    Returns HTTPS/TLS connections showing:
    - Server name (from TLS handshake)
    - Destination IP and port
    - TLS version
    
    Useful for tracking encrypted external connections.
    
    **Search:** Full-text search across server_name, dest_ip, pod, namespace, comm
    
    **Sprint 5-6 Feature**
    """
)
async def get_sni_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> SniEventsResponse:
    """
    Get SNI events endpoint
    
    Path: GET /api/v1/events/sni
    """
    try:
        response = await service.get_sni_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
        return response
        
    except Exception as e:
        logger.error(
            "Failed to get SNI events",
            error=str(e),
            cluster_id=cluster_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve SNI events: {str(e)}"
        )


@router.get(
    "/process",
    response_model=ProcessEventsResponse,
    summary="Get Process Events",
    description="Get process execution events (exec, exit, signal) from eBPF trace_exec gadget. Search across comm, exe, pod, namespace."
)
async def get_process_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> ProcessEventsResponse:
    """Get process events endpoint"""
    try:
        return await service.get_process_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get process events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve process events: {str(e)}"
        )


@router.get(
    "/file",
    response_model=FileEventsResponse,
    summary="Get File Events",
    description="Get file operation events (open, read, write, close) from eBPF trace_open gadget. Search across file_path, comm, pod, namespace."
)
async def get_file_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> FileEventsResponse:
    """Get file events endpoint"""
    try:
        return await service.get_file_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get file events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve file events: {str(e)}"
        )


@router.get(
    "/security",
    response_model=SecurityEventsResponse,
    summary="Get Security Events",
    description="Get security/capability check events from eBPF trace_capabilities gadget. Search across capability, syscall, comm, pod, namespace."
)
async def get_security_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> SecurityEventsResponse:
    """Get security events endpoint"""
    try:
        return await service.get_security_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get security events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve security events: {str(e)}"
        )


@router.get(
    "/oom",
    response_model=OomEventsResponse,
    summary="Get OOM Events",
    description="Get Out-of-Memory kill events from eBPF trace_oomkill gadget. Search across comm, pod, namespace, node."
)
async def get_oom_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> OomEventsResponse:
    """Get OOM events endpoint"""
    try:
        return await service.get_oom_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get OOM events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve OOM events: {str(e)}"
        )


@router.get(
    "/bind",
    response_model=BindEventsResponse,
    summary="Get Bind Events",
    description="Get socket bind events (listening ports) from eBPF trace_bind gadget. Search across bind_addr, bind_port, comm, interface, pod, namespace."
)
async def get_bind_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> BindEventsResponse:
    """Get bind events endpoint"""
    try:
        return await service.get_bind_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get bind events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve bind events: {str(e)}"
        )


@router.get(
    "/mount",
    response_model=MountEventsResponse,
    summary="Get Mount Events",
    description="Get filesystem mount events from eBPF trace_mount gadget. Search across source, target, fs_type, comm, pod, namespace."
)
async def get_mount_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> MountEventsResponse:
    """Get mount events endpoint"""
    try:
        return await service.get_mount_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get mount events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve mount events: {str(e)}"
        )


@router.get(
    "/network",
    response_model=NetworkFlowsResponse,
    summary="Get Network Flows",
    description="Get network flow events from eBPF trace_network gadget. Search across source_ip, dest_ip, source_pod, dest_pod, source_namespace, dest_namespace."
)
async def get_network_flows(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> NetworkFlowsResponse:
    """Get network flow events endpoint"""
    try:
        return await service.get_network_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get network flows", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve network flows: {str(e)}"
        )


@router.get(
    "/tcp",
    response_model=TcpConnectionsResponse,
    summary="Get TCP Connections",
    description="Get TCP connection lifecycle events from eBPF trace_tcp gadget. Search across source_ip, dest_ip, source_pod, dest_pod."
)
async def get_tcp_connections(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> TcpConnectionsResponse:
    """Get TCP connection events endpoint"""
    try:
        return await service.get_tcp_connections(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get TCP connections", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve TCP connections: {str(e)}"
        )


@router.get(
    "",
    response_model=GenericEventsResponse,
    summary="Get All Events",
    description="Get all events with filtering by type, time range, and more. Search is applied to relevant fields for each event type."
)
async def get_all_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster via analysis_id)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis", gt=0),
    namespace: Optional[str] = Query(None, description="Filter by namespace", max_length=253),
    search: Optional[str] = Query(None, description="Full-text search across relevant fields", max_length=500),
    event_types: Optional[str] = Query(None, description="Comma-separated event types to include"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: dict = Depends(get_current_user),
    service: EventService = Depends(get_service)
) -> GenericEventsResponse:
    """Get all events with filtering"""
    try:
        # Parse event_types if provided
        types_list: Optional[List[str]] = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        return await service.get_all_events(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            search=search,
            event_types=types_list,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error("Failed to get events", error=str(e), cluster_id=cluster_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve events: {str(e)}"
        )

