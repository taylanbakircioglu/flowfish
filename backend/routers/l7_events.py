"""
L7 (Beyla) event queries — proxy to timeseries-query service.
"""

import re
from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()
router = APIRouter()

# Defense-in-depth: validate trace_id format at the API boundary as well as
# in the timeseries-query layer. Prevents non-hex paths from being proxied at
# all (saves a network round trip and prevents URL-encoding edge cases).
_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{1,32}$")


def _validate_trace_id(trace_id: str) -> str:
    if not isinstance(trace_id, str) or not _TRACE_ID_RE.match(trace_id):
        raise HTTPException(status_code=400, detail=f"Invalid trace_id format: {trace_id!r}")
    return trace_id.lower()


async def _proxy_timeseries_l7_get(path: str, params: dict):
    base = settings.TIMESERIES_QUERY_URL.rstrip("/")
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            logger.warning(
                "timeseries-query L7 returned non-200",
                path=path,
                status=response.status_code,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Timeseries query returned HTTP {response.status_code}",
            )
    except httpx.ConnectError as e:
        logger.error("Cannot reach timeseries-query for L7 events", error=str(e), url=url)
        raise HTTPException(status_code=503, detail="Timeseries query service unavailable") from e
    except httpx.TimeoutException as e:
        logger.error("timeseries-query L7 timed out", error=str(e), url=url)
        raise HTTPException(status_code=504, detail="Timeseries query service timed out") from e
    except httpx.HTTPError as e:
        logger.error("timeseries-query L7 HTTP error", error=str(e), url=url)
        raise HTTPException(status_code=502, detail="Timeseries query service error") from e


@router.get("/http")
async def get_l7_http_events(
    cluster_id: Optional[str] = Query(None),
    analysis_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    http_path: Optional[str] = Query(None, alias="path"),
    status_code: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    params = {"limit": limit, "offset": offset}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    if namespace is not None:
        params["namespace"] = namespace
    if method is not None:
        params["method"] = method
    if http_path is not None:
        params["path"] = http_path
    if status_code is not None:
        params["status_code"] = status_code
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return await _proxy_timeseries_l7_get("/l7/events/http", params)


@router.get("/grpc")
async def get_l7_grpc_events(
    cluster_id: Optional[str] = Query(None),
    analysis_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    grpc_service: Optional[str] = Query(None),
    grpc_method: Optional[str] = Query(None),
    grpc_status_code: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    params = {"limit": limit, "offset": offset}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    if namespace is not None:
        params["namespace"] = namespace
    if grpc_service is not None:
        params["grpc_service"] = grpc_service
    if grpc_method is not None:
        params["grpc_method"] = grpc_method
    if grpc_status_code is not None:
        params["grpc_status_code"] = grpc_status_code
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return await _proxy_timeseries_l7_get("/l7/events/grpc", params)


@router.get("/dns")
async def get_l7_dns_events(
    cluster_id: Optional[str] = Query(None),
    analysis_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    query_name: Optional[str] = Query(None),
    query_type: Optional[str] = Query(None),
    response_code: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    params = {"limit": limit, "offset": offset}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    if namespace is not None:
        params["namespace"] = namespace
    if query_name is not None:
        params["query_name"] = query_name
    if query_type is not None:
        params["query_type"] = query_type
    if response_code is not None:
        params["response_code"] = response_code
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return await _proxy_timeseries_l7_get("/l7/events/dns", params)


@router.get("/stats")
async def get_l7_event_stats(
    cluster_id: Optional[str] = Query(None),
    analysis_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    params = {}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    if namespace is not None:
        params["namespace"] = namespace
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return await _proxy_timeseries_l7_get("/l7/events/stats", params)


@router.get("/histogram")
async def get_l7_http_histogram(
    cluster_id: Optional[str] = Query(None),
    analysis_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    bucket_count: int = Query(60, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    params = {"bucket_count": bucket_count}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    if namespace is not None:
        params["namespace"] = namespace
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return await _proxy_timeseries_l7_get("/l7/events/histogram", params)


# ============================================================================
# L7 Distributed Tracing API (Faz 3.3)
# Proxies to timeseries-query /l7/traces endpoints. Validates trace_id format
# defensively at the gateway before forwarding.
# ============================================================================
@router.get("/traces/{trace_id}")
async def get_l7_trace(
    trace_id: str,
    analysis_id: Optional[str] = Query(
        None,
        description=(
            "Optional analysis ID. When provided, the lookup is scoped to that "
            "analysis (and its multi-cluster sub-analyses via the `<aid>-*` "
            "prefix). When omitted, the trace is searched cluster-wide — used "
            "by the Trace Explorer deep-link `/trace-explorer?trace_id=...` "
            "where the operator only has the trace_id."
        ),
    ),
    current_user: dict = Depends(get_current_user),
):
    """Return all spans (HTTP + gRPC) for a single trace, ordered by timestamp.

    Pass `analysis_id` to restrict the lookup; omit it to support deep-link
    URLs that only carry a trace_id.
    """
    validated = _validate_trace_id(trace_id)
    params: dict = {}
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    return await _proxy_timeseries_l7_get(f"/l7/traces/{validated}", params)


@router.get("/traces/{trace_id}/related")
async def get_l7_related_traces(
    trace_id: str,
    analysis_id: Optional[str] = Query(
        None,
        description=(
            "Optional analysis ID; narrows the related search to the same "
            "analysis (and `<aid>-*` sub-analyses)."
        ),
    ),
    rel_type: str = Query(
        "both",
        regex="^(same_edge|same_pod|both)$",
        description=(
            "Correlation type: same_edge = same (src_workload, dst_workload) "
            "pair; same_pod = same dst_pod; both = both groups (default)."
        ),
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results per group"),
    time_window_minutes: int = Query(
        60,
        ge=5,
        le=1440,
        description="Look-back window from anchor's timestamp (5 min – 24 h)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Find traces related to a given anchor trace (Phase 3B).

    Drives the Trace Waterfall "Related Traces" tab. Returns two ranked
    groups (same_edge, same_pod) of recent traces sharing the anchor's
    edge or destination pod. 5-tuple correlation is deferred to Phase 4
    (PID-based virtual_trace_id).
    """
    validated = _validate_trace_id(trace_id)
    params: dict = {
        "rel_type": rel_type,
        "limit": limit,
        "time_window_minutes": time_window_minutes,
    }
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
    return await _proxy_timeseries_l7_get(f"/l7/traces/{validated}/related", params)


@router.get("/traces")
async def list_l7_traces(
    analysis_id: str = Query(..., description="Analysis ID for scope filtering"),
    # Multi-cluster narrowing. Other L7 endpoints (/http /grpc /dns /stats
    # /histogram) all expose `cluster_id`; the trace list was the lone
    # outlier and a multi-cluster analysis would always show traces from
    # both clusters mixed together with no way to filter. The DB writes
    # `analysis_id` as the bare numeric id (not `<aid>-<cluster>`), so
    # `analysis_id=<aid>-<cid>` returns zero rows — `cluster_id` is the
    # right knob to narrow the view.
    cluster_id: Optional[str] = Query(
        None, description="Narrow the trace list to a single cluster"
    ),
    workload: Optional[str] = Query(None, description="Filter by source or destination workload"),
    # Phase 1A — optional filters (default None / False keep legacy behaviour)
    src_workload: Optional[str] = Query(None, description="Filter by source workload only"),
    dst_workload: Optional[str] = Query(None, description="Filter by destination workload only"),
    operation: Optional[str] = Query(None, description="HTTP path or gRPC method exact match"),
    min_latency_ms: Optional[float] = Query(None, ge=0, description="Min span latency (ms)"),
    # Plan v3 Akış B m.3 (B1.2 fix): trace-level upper bound, used by the
    # latency histogram bucket click. The filter applies to the aggregated
    # max(latency_ms) per trace, applied via a HAVING clause downstream.
    max_latency_ms: Optional[float] = Query(
        None, ge=0, description="Trace-level max(latency_ms) upper bound (ms)"
    ),
    error_only: bool = Query(False, description="Only error spans (HTTP 4xx/5xx, gRPC != 0)"),
    start_time: Optional[str] = Query(None, description="ISO-8601 lower bound"),
    end_time: Optional[str] = Query(None, description="ISO-8601 upper bound"),
    # Plan v3 Akış B m.4 (B1.3 fix): free-form search across operation,
    # workloads, namespace, trace_id. `min_length=1` rejects empty strings
    # (RTK Query `cleanParams` already drops them but defense-in-depth);
    # `max_length` keeps malicious inputs short.
    q: Optional[str] = Query(None, min_length=1, max_length=255, description="Free-form search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """List recent traces for an analysis, optionally filtered.

    All filter parameters are optional and additive. Calling with only
    `analysis_id` reproduces the legacy behaviour exactly.
    """
    params: dict = {"analysis_id": analysis_id, "limit": limit, "offset": offset}
    if cluster_id:
        params["cluster_id"] = cluster_id
    if workload:
        params["workload"] = workload
    if src_workload:
        params["src_workload"] = src_workload
    if dst_workload:
        params["dst_workload"] = dst_workload
    if operation:
        params["operation"] = operation
    if min_latency_ms is not None:
        params["min_latency_ms"] = min_latency_ms
    if max_latency_ms is not None:
        params["max_latency_ms"] = max_latency_ms
    if error_only:
        params["error_only"] = "true"
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    if q:
        params["q"] = q
    return await _proxy_timeseries_l7_get("/l7/traces", params)
