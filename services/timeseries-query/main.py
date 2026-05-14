"""
Timeseries Query Service

HTTP API for querying time-series event data.
Provides database-agnostic interface for event queries.

Endpoints:
- GET /health - Service health check
- GET /events/stats - Event statistics
- GET /events/{event_type} - Query specific event type
- GET /events - Query all events with filtering
- POST /dev-console/query - Execute custom SQL query for Dev Console
- GET /dev-console/schema - Get ClickHouse schema information

Version: 1.1.0 - Added Dev Console support
"""

import logging
import uvicorn
import re
import time
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any

from app.config import settings
from app.query_engine import TimeseriesQueryEngine

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Query engine instance
query_engine: Optional[TimeseriesQueryEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global query_engine
    
    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.port}")
    
    try:
        query_engine = TimeseriesQueryEngine()
        logger.info("✅ Query engine initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize query engine: {e}")
        raise
    
    yield
    
    # Shutdown
    if query_engine:
        query_engine.close()
    logger.info("👋 Timeseries Query Service stopped")


# Create FastAPI app
app = FastAPI(
    title="Timeseries Query Service",
    description="Query service for time-series event data",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Service health check"""
    if query_engine:
        db_health = query_engine.health_check()
        return {
            "status": "healthy" if db_health["healthy"] else "degraded",
            "service": settings.service_name,
            "database": db_health
        }
    return {"status": "unhealthy", "service": settings.service_name}


@app.get("/ready")
async def ready():
    """Readiness probe"""
    if query_engine and query_engine.health_check()["healthy"]:
        return {"ready": True}
    raise HTTPException(status_code=503, detail="Service not ready")


# ============================================================================
# Event Query Endpoints
# ============================================================================

@app.get("/events/stats")
async def get_event_stats(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter")
):
    """
    Get event statistics
    
    Returns:
    - Total event count
    - Event counts by type
    - Time range
    - Top namespaces
    - Top pods
    """
    try:
        stats = await query_engine.get_event_stats(cluster_id, analysis_id)
        return stats
    except Exception as e:
        logger.error(f"Failed to get event stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/histogram")
async def get_event_histogram(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    bucket_count: int = Query(60, ge=1, le=200, description="Number of time buckets")
):
    """
    Time-bucketed event histogram for timeline visualization.
    
    Returns aggregated event counts grouped by time bucket and event type
    using efficient server-side ClickHouse aggregation.
    """
    try:
        types_list = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        result = await query_engine.query_event_histogram(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            event_types=types_list,
            start_time=start_time,
            end_time=end_time,
            bucket_count=bucket_count
        )
        return result
    except Exception as e:
        logger.error(f"Failed to get event histogram: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events")
async def get_all_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    # `search` was previously declared on the backend gateway and forwarded
    # in `params["search"]`, but this endpoint did not accept it — FastAPI
    # silently dropped the unknown query param and the UI's "Search" box
    # therefore appeared functional but matched nothing. Accept it here so
    # the contract matches what the gateway/repository actually sends.
    search: Optional[str] = Query(None, description="Substring match across table-specific fields"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    Query all events with filtering
    
    Supports filtering by event types, namespace, and time range.
    Returns unified event format from multiple tables.
    """
    try:
        types_list = None
        if event_types:
            types_list = [t.strip() for t in event_types.split(",")]
        
        events, total = await query_engine.query_all_events(
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
        
        return {
            "events": events,
            "total": total,
            "has_more": (offset + len(events)) < total
        }
    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/network")
async def get_network_flows(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across source_ip, dest_ip, pods, namespaces"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query network flow events"""
    try:
        events, total = await query_engine.query_network_flows(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get network flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/dns")
async def get_dns_queries(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across query_name, dns_server_ip, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query DNS query events"""
    try:
        events, total = await query_engine.query_dns_queries(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"queries": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get DNS queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: /events/tcp endpoint removed - IG trace_tcp doesn't produce TCP state events
# TCP connection info is captured in network_flows via connect/accept/close events


@app.get("/events/process")
async def get_process_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across comm, exe, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query process execution events"""
    try:
        events, total = await query_engine.query_process_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get process events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/file")
async def get_file_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across file_path, comm, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query file operation events"""
    try:
        events, total = await query_engine.query_file_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get file events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/security")
async def get_security_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across capability, syscall, comm, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query security/capability events"""
    try:
        events, total = await query_engine.query_security_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get security events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/oom")
async def get_oom_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across comm, pod, namespace, node"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query OOM kill events"""
    try:
        events, total = await query_engine.query_oom_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get OOM events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/bind")
async def get_bind_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across bind_addr, comm, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query socket bind events"""
    try:
        events, total = await query_engine.query_bind_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get bind events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/sni")
async def get_sni_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across sni_name, dst_ip, pod, namespace, comm"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query TLS/SNI events"""
    try:
        events, total = await query_engine.query_sni_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get SNI events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/mount")
async def get_mount_events(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Namespace filter"),
    search: Optional[str] = Query(None, description="Search across source, target, fs_type, comm, pod, namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """Query mount events"""
    try:
        events, total = await query_engine.query_mount_events(
            cluster_id, analysis_id, namespace, start_time, end_time, limit, offset,
            search=search
        )
        return {"events": events, "total": total}
    except Exception as e:
        logger.error(f"Failed to get mount events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# L7 (Beyla) event endpoints
# ============================================================================

@app.get("/l7/events/http")
async def get_l7_http_events(
    cluster_id: Optional[str] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[str] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Match src or dst namespace"),
    method: Optional[str] = Query(None, description="HTTP method"),
    path: Optional[str] = Query(None, description="Exact http_path"),
    status_code: Optional[int] = Query(None, description="HTTP status code"),
    start_time: Optional[str] = Query(None, description="Start time (ISO)"),
    end_time: Optional[str] = Query(None, description="End time (ISO)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Query l7_http_flows with filters."""
    try:
        events, total = await query_engine.query_l7_http_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            method=method,
            path=path,
            status_code=status_code,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return {"events": events, "total": total, "has_more": (offset + len(events)) < total}
    except Exception as e:
        logger.error(f"Failed to get L7 HTTP events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/events/grpc")
async def get_l7_grpc_events(
    cluster_id: Optional[str] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[str] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Match src or dst namespace"),
    grpc_service: Optional[str] = Query(None),
    grpc_method: Optional[str] = Query(None),
    grpc_status_code: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None, description="Start time (ISO)"),
    end_time: Optional[str] = Query(None, description="End time (ISO)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Query l7_grpc_flows with filters."""
    try:
        events, total = await query_engine.query_l7_grpc_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            start_time=start_time,
            end_time=end_time,
            grpc_service=grpc_service,
            grpc_method=grpc_method,
            grpc_status_code=grpc_status_code,
            limit=limit,
            offset=offset,
        )
        return {"events": events, "total": total, "has_more": (offset + len(events)) < total}
    except Exception as e:
        logger.error(f"Failed to get L7 gRPC events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/events/dns")
async def get_l7_dns_events(
    cluster_id: Optional[str] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[str] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Match src or dst namespace"),
    query_name: Optional[str] = Query(None, description="DNS query name (exact)"),
    query_type: Optional[str] = Query(None),
    response_code: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None, description="Start time (ISO)"),
    end_time: Optional[str] = Query(None, description="End time (ISO)"),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """Query l7_dns_flows with filters."""
    try:
        events, total = await query_engine.query_l7_dns_flows(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            start_time=start_time,
            end_time=end_time,
            query_name=query_name,
            query_type=query_type,
            response_code=response_code,
            limit=limit,
            offset=offset,
        )
        return {"events": events, "total": total, "has_more": (offset + len(events)) < total}
    except Exception as e:
        logger.error(f"Failed to get L7 DNS events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/events/stats")
async def get_l7_events_stats(
    cluster_id: Optional[str] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[str] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="Match src or dst namespace"),
    start_time: Optional[str] = Query(None, description="Start time (ISO)"),
    end_time: Optional[str] = Query(None, description="End time (ISO)"),
):
    """Aggregate L7 stats across HTTP, gRPC, and DNS tables."""
    try:
        return await query_engine.query_l7_events_stats(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            start_time=start_time,
            end_time=end_time,
        )
    except Exception as e:
        logger.error(f"Failed to get L7 event stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/events/histogram")
async def get_l7_events_histogram(
    cluster_id: Optional[str] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[str] = Query(None, description="Analysis ID filter"),
    namespace: Optional[str] = Query(None, description="When set, rolls up from l7_http_flows (MV has no namespace)"),
    start_time: Optional[str] = Query(None, description="Start time (ISO)"),
    end_time: Optional[str] = Query(None, description="End time (ISO)"),
    bucket_count: int = Query(60, ge=1, le=200),
):
    """HTTP request histogram (5-min grain; uses l7_http_flows_5min_mv when namespace unset)."""
    try:
        return await query_engine.query_l7_http_histogram(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            namespace=namespace,
            start_time=start_time,
            end_time=end_time,
            bucket_count=bucket_count,
        )
    except Exception as e:
        logger.error(f"Failed to get L7 histogram: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# L7 Distributed Tracing API (Faz 3.2)
# Reads from l7_http_flows + l7_grpc_flows; DNS spans excluded.
# Errors are propagated as HTTP 500 (not silently swallowed) so the UI can
# distinguish empty traces from query failures.
# ============================================================================
@app.get("/l7/traces/{trace_id}")
async def get_l7_trace(
    trace_id: str,
    analysis_id: Optional[str] = Query(
        None,
        description=(
            "Optional analysis ID. When provided the lookup is scoped to that "
            "analysis (matched as exact OR `<analysis_id>-*` prefix for "
            "multi-cluster sub-analyses); when omitted, the trace is searched "
            "across all analyses to support deep-link URLs that only carry a "
            "trace_id."
        ),
    ),
):
    """Return all spans for a trace, ordered by timestamp ascending."""
    try:
        spans = query_engine.get_trace_spans(trace_id, analysis_id)
        # Pass already-fetched spans to avoid a second ClickHouse round-trip
        # (Bulgu 45.1). Summary is derived in-memory from the same row set.
        summary = query_engine.get_trace_summary(trace_id, analysis_id, spans=spans)
        return {"trace_id": trace_id, "spans": spans, "summary": summary}
    except ValueError as ve:
        # Invalid trace_id format
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to fetch trace {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/traces/{trace_id}/related")
async def get_l7_related_traces(
    trace_id: str,
    analysis_id: Optional[str] = Query(
        None,
        description=(
            "Optional analysis ID; when provided narrows the search to that "
            "analysis (and `<id>-*` sub-analyses)."
        ),
    ),
    rel_type: str = Query(
        "both",
        regex="^(same_edge|same_pod|both)$",
        description=(
            "Correlation type: same_edge = same (src_workload, dst_workload) "
            "pair; same_pod = same dst_pod; both = both groups."
        ),
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results per group"),
    time_window_minutes: int = Query(
        60,
        ge=5,
        le=1440,
        description="Look-back window from anchor's timestamp (5 min – 24 h)",
    ),
):
    """Find traces related to a given anchor trace.

    Returns two ranked groups (`same_edge`, `same_pod`) of recent traces
    that share the anchor's workload edge or destination pod. Used by the
    Trace Waterfall "Related Traces" tab (Phase 3C). The query unifies
    real W3C `trace_id`s and Phase 4 PID-correlated `virtual_trace_id`s
    via a coalesce, so PID-temporal virtual traces are surfaced too when
    Phase 4 is enabled and the schema is migrated. 5-tuple correlation
    (without PID) remains deferred — Phase 4 covers the most common
    "service-not-instrumented" case at the producer process granularity.
    """
    try:
        return query_engine.get_related_traces(
            trace_id=trace_id,
            analysis_id=analysis_id,
            rel_type=rel_type,
            limit=limit,
            time_window_minutes=time_window_minutes,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to fetch related traces for {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# APM RED Metrics Endpoints (Phase 2)
# ============================================================================
# Read from the AggregatingMergeTree RED MVs (clickhouse_005_add_apm_red_mvs.sql).
# All endpoints require an analysis_id (string — multi-cluster sub-IDs like
# "44-15" are valid). cluster_id is an optional narrowing filter.

@app.get("/apm/services")
async def list_apm_services(
    analysis_id: str = Query(..., description="Analysis ID (string; multi-cluster sub-IDs supported)"),
    cluster_id: Optional[str] = Query(None, description="Narrow to a single cluster"),
    namespace: Optional[str] = Query(None, description="Filter by destination namespace"),
    sort_by: str = Query("rate", regex="^(rate|errors|p50|p95|p99|avg)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    # Plan v3 Akış B m.4 — global search shared with Trace Explorer.
    # min_length=1 mirrors `/l7/traces` so empty strings are coerced to
    # null (no-op), matches FastAPI/HTTP semantics, and prevents an
    # accidental "?q=" from triggering an empty-string SQL filter.
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across destination workload/namespace.",
    ),
):
    """Workload-level RED tablosu for APM Services List page.

    Combines HTTP and gRPC RED MVs into a single per-service row with
    p50/p95/p99 percentiles (via quantileTDigestMerge), rate, and errors.
    """
    try:
        return query_engine.get_apm_services(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            namespace=namespace,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
            q=q,
        )
    except Exception as e:
        logger.error(f"Failed to list APM services: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apm/services/{workload_key:path}/operations")
async def list_apm_operations(
    workload_key: str,
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across HTTP path/method or gRPC service/method.",
    ),
):
    """Per-operation RED tablosu (HTTP method+normalized path / gRPC service+method).

    `workload_key` is `{dst_namespace}/{dst_workload}` (matches the value
    returned by `/apm/services`).
    """
    try:
        return query_engine.get_apm_operations(
            analysis_id=analysis_id,
            workload_key=workload_key,
            cluster_id=cluster_id,
            limit=limit,
            offset=offset,
            q=q,
        )
    except Exception as e:
        logger.error(f"Failed to list APM operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apm/services/{workload_key:path}/stats")
async def get_apm_service_stats(
    workload_key: str,
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
):
    """Time-series RED metrics (5-minute buckets) for one service.

    Drives the Service Detail RED chart. Combines HTTP and gRPC.
    """
    try:
        return query_engine.get_apm_service_stats(
            analysis_id=analysis_id,
            workload_key=workload_key,
            cluster_id=cluster_id,
        )
    except Exception as e:
        logger.error(f"Failed to get APM service stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Plan v3 Akış B m.2 — Trace Explorer "Operations" / "Dependencies" tabs
# need a *cross-workload* aggregate. The endpoints below mirror the
# per-workload variants but live at flat paths so FastAPI doesn't try to
# match `operations` / `dependencies` as a workload_key.

@app.get("/apm/operations")
async def list_apm_operations_global(
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across HTTP path/method, gRPC service/method, and dst workload/namespace.",
    ),
):
    """Top operations across every workload in the analysis scope —
    powers the Trace Explorer "Operations" tab.
    """
    try:
        return query_engine.get_apm_operations_global(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            q=q,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to list global APM operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apm/dependencies")
async def list_apm_dependencies_global(
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across either side of the edge (src or dst workload/namespace).",
    ),
):
    """Top service-to-service edges across the analysis scope — powers
    the Trace Explorer "Dependencies" tab.
    """
    try:
        return query_engine.get_apm_dependencies_global(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            q=q,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to list global APM dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apm/services/{workload_key:path}/dependencies")
async def get_apm_service_dependencies(
    workload_key: str,
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    direction: str = Query("both", regex="^(upstream|downstream|both)$"),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across the peer workload/namespace.",
    ),
):
    """Dependency neighbours (upstream/downstream services) for one service.

    Drives the Service Detail Dependencies tab and the Mini Service Map.
    """
    try:
        return query_engine.get_apm_service_dependencies(
            analysis_id=analysis_id,
            workload_key=workload_key,
            cluster_id=cluster_id,
            direction=direction,
            q=q,
        )
    except Exception as e:
        logger.error(f"Failed to get APM service dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/l7/traces")
async def list_l7_traces(
    analysis_id: str = Query(..., description="Analysis ID for scope filtering"),
    cluster_id: Optional[str] = Query(
        None, description="Narrow the trace list to a single cluster"
    ),
    workload: Optional[str] = Query(None, description="Filter by source or destination workload name"),
    # Phase 1A optional filters (backward-compat, all default to None / False)
    src_workload: Optional[str] = Query(None, description="Filter by source workload only"),
    dst_workload: Optional[str] = Query(None, description="Filter by destination workload only"),
    operation: Optional[str] = Query(None, description="HTTP path or gRPC method exact match"),
    min_latency_ms: Optional[float] = Query(None, ge=0, description="Minimum span latency in ms"),
    # Plan v3 Akış B m.3: trace-level upper bound on aggregated max latency.
    max_latency_ms: Optional[float] = Query(
        None, ge=0, description="Trace-level upper bound on max(latency_ms)"
    ),
    error_only: bool = Query(False, description="Only HTTP 4xx/5xx or gRPC non-zero status"),
    start_time: Optional[str] = Query(None, description="ISO-8601 lower bound on span timestamp"),
    end_time: Optional[str] = Query(None, description="ISO-8601 upper bound on span timestamp"),
    # Plan v3 Akış B m.4: free-form search across operation/workloads/trace_id.
    q: Optional[str] = Query(None, min_length=1, max_length=255, description="Free-form search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List recent traces (HTTP + gRPC) for an analysis, optionally filtered."""
    try:
        return query_engine.get_recent_traces(
            analysis_id=analysis_id,
            cluster_id=cluster_id,
            workload=workload,
            src_workload=src_workload,
            dst_workload=dst_workload,
            operation=operation,
            min_latency_ms=min_latency_ms,
            max_latency_ms=max_latency_ms,
            error_only=error_only,
            start_time=start_time,
            end_time=end_time,
            q=q,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Failed to list traces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Dev Console Endpoints - Custom SQL Query Execution
# ============================================================================

class DevConsoleQueryRequest(BaseModel):
    """Request model for Dev Console custom query"""
    query: str
    limit: int = 1000
    timeout: int = 30


class DevConsoleQueryResponse(BaseModel):
    """Response model for Dev Console query"""
    success: bool
    columns: List[str] = []
    rows: List[List] = []
    row_count: int = 0
    execution_time_ms: int = 0
    truncated: bool = False
    error: Optional[dict] = None


# ============================================================================
# Security Configuration for Dev Console
# ============================================================================
#
# Philosophy: Allow maximum read access, block only actual write operations.
# The query MUST start with a read-only command (SELECT, SHOW, etc.)
# which inherently prevents write operations at the statement level.
#
# We only need to block:
# 1. Queries that don't start with allowed read-only prefixes
# 2. Multiple statements (SQL injection)
# 3. Specific dangerous administrative commands
# ============================================================================

# Dangerous statement-level commands (must be at start of statement or after semicolon)
# These are administrative commands that could modify data or server state
DANGEROUS_STATEMENT_PATTERNS = [
    r'^\s*INSERT\b',
    r'^\s*UPDATE\b',  
    r'^\s*DELETE\b',
    r'^\s*DROP\b',
    r'^\s*TRUNCATE\b',
    r'^\s*ALTER\b',
    r'^\s*CREATE\b',
    r'^\s*GRANT\b',
    r'^\s*REVOKE\b',
    r'^\s*ATTACH\b',
    r'^\s*DETACH\b',
    r'^\s*OPTIMIZE\b',
    r'^\s*RENAME\b',
    r'^\s*EXCHANGE\b',
    r'^\s*SYSTEM\b',
    r'^\s*KILL\s+QUERY\b',
    r'^\s*KILL\s+MUTATION\b',
]


def validate_read_only_query(query: str) -> tuple:
    """
    Validate that query is read-only statement.
    
    Security model:
    - Query must START with a read-only command (SELECT, SHOW, etc.)
    - This inherently blocks write operations at statement level
    - Multiple statements are blocked to prevent injection
    - No keyword scanning within query body (avoids false positives)
    
    Returns:
        tuple: (is_valid, error_message)
    """
    import re
    
    # Remove comments FIRST before any validation
    # Remove single-line comments (-- ...)
    cleaned_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    # Remove multi-line comments (/* ... */)
    cleaned_query = re.sub(r'/\*.*?\*/', '', cleaned_query, flags=re.DOTALL)
    
    query_stripped = cleaned_query.strip()
    query_upper = query_stripped.upper()
    
    # Empty query check
    if not query_stripped:
        return False, "Empty query"
    
    # Allowed read-only command prefixes
    ALLOWED_PREFIXES = (
        'SELECT',      # Data queries
        'WITH',        # CTEs (Common Table Expressions) - always followed by SELECT
        'SHOW',        # SHOW TABLES, SHOW DATABASES, SHOW CREATE TABLE, etc.
        'DESCRIBE',    # Table structure
        'DESC',        # Shorthand for DESCRIBE
        'EXPLAIN',     # Query execution plan
        'EXISTS',      # EXISTS check (read-only)
    )
    
    # Main security check: query must start with allowed read-only prefix
    if not query_upper.startswith(ALLOWED_PREFIXES):
        return False, "Only read-only queries allowed (SELECT, WITH, SHOW, DESCRIBE, EXPLAIN)"
    
    # Check for multiple statements (SQL injection protection)
    # Split by semicolon and check each part
    statements = [s.strip() for s in cleaned_query.split(';') if s.strip()]
    
    if len(statements) > 1:
        # Multiple statements - check if any is dangerous
        for stmt in statements[1:]:  # Skip first (already validated)
            stmt_upper = stmt.upper()
            for pattern in DANGEROUS_STATEMENT_PATTERNS:
                if re.match(pattern, stmt_upper, re.IGNORECASE):
                    return False, "Multiple statements with write operations not allowed"
        # Even if all seem safe, block multiple statements for security
        return False, "Multiple statements not allowed"
    
    return True, ""


@app.post("/dev-console/query", response_model=DevConsoleQueryResponse)
async def execute_dev_console_query(request: DevConsoleQueryRequest):
    """
    Execute a custom SQL query for Dev Console
    
    Security features:
    - Read-only queries only (SELECT statements)
    - Automatic LIMIT enforcement
    - Query timeout
    - Result size limits
    
    This endpoint is for developer debugging and exploration.
    """
    import time
    import re
    from datetime import datetime
    
    start_time = time.time()
    
    try:
        # Security: Validate query is read-only
        is_valid, error_msg = validate_read_only_query(request.query)
        if not is_valid:
            return DevConsoleQueryResponse(
                success=False,
                error={"code": "SECURITY_ERROR", "message": error_msg}
            )
        
        # Ensure LIMIT is present
        query = request.query.strip().rstrip(';')
        query_upper = query.upper()
        if 'LIMIT' not in query_upper:
            query = f"{query} LIMIT {request.limit}"
        
        # Execute query via query engine
        result = query_engine.client.execute(query, with_column_types=True)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        if not result:
            return DevConsoleQueryResponse(
                success=True,
                columns=[],
                rows=[],
                row_count=0,
                execution_time_ms=execution_time_ms,
                truncated=False
            )
        
        rows_data, columns_info = result
        column_names = [col[0] for col in columns_info]
        
        # Convert rows to serializable format
        processed_rows = []
        for row in rows_data:
            processed_row = []
            for val in row:
                if isinstance(val, datetime):
                    processed_row.append(val.isoformat())
                elif isinstance(val, bytes):
                    processed_row.append(val.hex()[:1000])  # Truncate binary
                elif val is None:
                    processed_row.append(None)
                else:
                    # Truncate large strings
                    str_val = str(val)
                    if len(str_val) > 10000:
                        str_val = str_val[:10000] + "... [truncated]"
                    processed_row.append(val if not isinstance(val, str) or len(str(val)) <= 10000 else str_val)
            processed_rows.append(processed_row)
        
        # Check if truncated due to limit
        truncated = len(processed_rows) >= request.limit
        
        return DevConsoleQueryResponse(
            success=True,
            columns=column_names,
            rows=processed_rows,
            row_count=len(processed_rows),
            execution_time_ms=execution_time_ms,
            truncated=truncated
        )
        
    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        
        # Sanitize error message
        if 'password' in error_msg.lower() or 'secret' in error_msg.lower():
            error_msg = "Database error. Please contact administrator."
        
        logger.error(f"Dev Console query failed: {error_msg}")
        
        return DevConsoleQueryResponse(
            success=False,
            execution_time_ms=execution_time_ms,
            error={"code": "QUERY_ERROR", "message": error_msg[:500]}
        )


@app.get("/dev-console/schema")
async def get_clickhouse_schema():
    """
    Get ClickHouse schema information for Dev Console
    
    Returns list of tables with their columns and types.
    """
    try:
        # Get tables in flowfish database
        tables_query = """
        SELECT name, engine
        FROM system.tables
        WHERE database = 'flowfish'
        ORDER BY name
        """
        tables_result = query_engine.client.execute(tables_query)
        
        schema = {"database": "clickhouse", "tables": []}
        
        for table_row in tables_result:
            table_name = table_row[0]
            
            # Get columns for this table
            columns_query = f"""
            SELECT name, type, comment
            FROM system.columns
            WHERE database = 'flowfish' AND table = '{table_name}'
            ORDER BY position
            """
            columns_result = query_engine.client.execute(columns_query)
            
            columns = []
            for col in columns_result:
                columns.append({
                    "name": col[0],
                    "type": col[1],
                    "description": col[2] if col[2] else None
                })
            
            schema["tables"].append({
                "name": table_name,
                "columns": columns
            })
        
        return schema
        
    except Exception as e:
        logger.error(f"Failed to get schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Admin Endpoints
# ============================================================================

@app.delete("/admin/analysis/{analysis_id}")
async def delete_analysis_data(
    analysis_id: int,
    wait_for_completion: bool = Query(True, description="Wait for mutations to complete"),
    timeout_seconds: int = Query(60, ge=5, le=300, description="Max wait time in seconds")
):
    """
    Delete all event data for an analysis
    
    This is an admin operation that removes all ClickHouse data for a specific analysis.
    Use with caution - this operation cannot be undone.
    
    Returns:
    - tables: Count of deleted records per table
    - total_deleted: Total records deleted
    - completed: Whether all mutations completed
    - duration_ms: Operation duration
    """
    try:
        result = await query_engine.delete_analysis_data(
            analysis_id=analysis_id,
            wait_for_completion=wait_for_completion,
            timeout_seconds=timeout_seconds
        )
        return result
    except Exception as e:
        logger.error(f"Failed to delete analysis data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower()
    )

