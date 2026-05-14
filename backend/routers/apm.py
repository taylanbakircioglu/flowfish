"""
APM (Application Performance Monitoring) endpoints — Phase 2.

Proxy layer for the timeseries-query service's APM RED metrics endpoints,
backed by AggregatingMergeTree materialized views with quantileTDigest
state (see schemas/migrations/clickhouse_005_add_apm_red_mvs.sql).

All endpoints share the same scoping rules: `analysis_id` is required
(string — multi-cluster sub-analysis IDs like '44-15' are valid),
`cluster_id` is an optional narrowing filter. Authentication uses the
project-wide `utils.jwt_utils.get_current_user` dependency, matching
every other router.
"""

from typing import Optional
from urllib.parse import quote

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()
router = APIRouter()


async def _proxy_apm_get(path: str, params: dict):
    """Proxy a GET request to the timeseries-query APM endpoint.

    Mirrors the structure of `l7_events._proxy_timeseries_l7_get` so the
    error semantics (503 / 504 / 502) are consistent across L7 and APM
    surfaces.
    """
    base = settings.TIMESERIES_QUERY_URL.rstrip("/")
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            logger.warning(
                "timeseries-query APM returned non-200",
                path=path,
                status=response.status_code,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Timeseries query returned HTTP {response.status_code}",
            )
    except httpx.ConnectError as e:
        logger.error("Cannot reach timeseries-query for APM", error=str(e), url=url)
        raise HTTPException(status_code=503, detail="Timeseries query service unavailable") from e
    except httpx.TimeoutException as e:
        logger.error("timeseries-query APM timed out", error=str(e), url=url)
        raise HTTPException(status_code=504, detail="Timeseries query service timed out") from e
    except httpx.HTTPError as e:
        logger.error("timeseries-query APM HTTP error", error=str(e), url=url)
        raise HTTPException(status_code=502, detail="Timeseries query service error") from e


def _encode_workload_key(workload_key: str) -> str:
    """URL-encode a workload key (`namespace/workload`) for use as a path
    segment. Without this the embedded slash would change the route shape.
    """
    return quote(workload_key, safe="")


@router.get("/services")
async def list_apm_services(
    analysis_id: str = Query(
        ...,
        description="Analysis ID (string; multi-cluster sub-IDs like '44-15' are supported)",
    ),
    cluster_id: Optional[str] = Query(None, description="Narrow to a single cluster"),
    namespace: Optional[str] = Query(None, description="Filter by destination namespace"),
    sort_by: str = Query(
        "rate",
        regex="^(rate|errors|p50|p95|p99)$",
        description="Sort column for the table",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    # Plan v3 Akış B m.4 — global search shared with Trace Explorer.
    # min_length=1/max_length=255 mirrors `/l7/traces` so an empty
    # `?q=` is rejected before it hits the SQL builder, and the upper
    # bound prevents a runaway query from turning into a DoS vector.
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across destination workload/namespace.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Workload-level RED tablosu for the APM Services List page.

    Combines HTTP and gRPC RED MVs (HTTP-only or gRPC-only services
    naturally collapse to one protocol). Returns
    `{services: [...], total, limit, offset, sort_by}`. Each service has
    `workload_key`, `request_count`, `error_count`, `error_rate` and
    `latency_p50_ms / p95_ms / p99_ms`.
    """
    params: dict = {
        "analysis_id": analysis_id,
        "sort_by": sort_by,
        "limit": limit,
        "offset": offset,
    }
    if cluster_id:
        params["cluster_id"] = cluster_id
    if namespace:
        params["namespace"] = namespace
    if q:
        params["q"] = q
    return await _proxy_apm_get("/apm/services", params)


@router.get("/services/{workload_key:path}/operations")
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
    current_user: dict = Depends(get_current_user),
):
    """Per-operation RED tablosu (HTTP method+path / gRPC service+method).

    `workload_key` is `{namespace}/{workload}` (the value returned in
    `/apm/services` responses); the embedded slash is URL-encoded when
    proxied to timeseries-query so the path-param routing matches.
    """
    params: dict = {"analysis_id": analysis_id, "limit": limit, "offset": offset}
    if cluster_id:
        params["cluster_id"] = cluster_id
    if q:
        params["q"] = q
    encoded = _encode_workload_key(workload_key)
    return await _proxy_apm_get(f"/apm/services/{encoded}/operations", params)


@router.get("/services/{workload_key:path}/stats")
async def get_apm_service_stats(
    workload_key: str,
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Time-series RED metrics (5-minute buckets) for one service —
    drives the Service Detail RED chart.
    """
    params: dict = {"analysis_id": analysis_id}
    if cluster_id:
        params["cluster_id"] = cluster_id
    encoded = _encode_workload_key(workload_key)
    return await _proxy_apm_get(f"/apm/services/{encoded}/stats", params)


# Plan v3 Akış B m.2 — Trace Explorer "Operations" / "Dependencies"
# tabs. Cross-workload aggregates that share scoping rules with the
# per-workload variants but don't take a `workload_key` path segment.
# Implemented as separate routes (rather than `workload_key="*"` magic
# value) so OpenAPI clients see distinct shapes and the operator never
# accidentally types a workload literally named `*`.

@router.get("/operations")
async def list_apm_operations_global(
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across HTTP/gRPC operation columns and dst workload/namespace.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Top operations across every workload in the analysis scope —
    drives the Trace Explorer "Operations" tab.
    """
    params: dict = {"analysis_id": analysis_id, "limit": limit}
    if cluster_id:
        params["cluster_id"] = cluster_id
    if q:
        params["q"] = q
    return await _proxy_apm_get("/apm/operations", params)


@router.get("/dependencies")
async def list_apm_dependencies_global(
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across either side of the edge.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Top service-to-service edges across the analysis scope — drives
    the Trace Explorer "Dependencies" tab.
    """
    params: dict = {"analysis_id": analysis_id, "limit": limit}
    if cluster_id:
        params["cluster_id"] = cluster_id
    if q:
        params["q"] = q
    return await _proxy_apm_get("/apm/dependencies", params)


@router.get("/services/{workload_key:path}/dependencies")
async def get_apm_service_dependencies(
    workload_key: str,
    analysis_id: str = Query(...),
    cluster_id: Optional[str] = Query(None),
    direction: str = Query(
        "both",
        regex="^(upstream|downstream|both)$",
        description="Which neighbours to return",
    ),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=255,
        description="Free-form search across the peer workload/namespace.",
    ),
    current_user: dict = Depends(get_current_user),
):
    """Dependency neighbours (upstream/downstream) for one service —
    drives the Service Detail Dependencies tab and the Mini Service Map.
    """
    params: dict = {"analysis_id": analysis_id, "direction": direction}
    if cluster_id:
        params["cluster_id"] = cluster_id
    if q:
        params["q"] = q
    encoded = _encode_workload_key(workload_key)
    return await _proxy_apm_get(f"/apm/services/{encoded}/dependencies", params)
