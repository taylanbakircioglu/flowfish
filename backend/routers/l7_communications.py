"""
L7 (Beyla) communications and dependency graph — proxy to graph-query service.
"""

from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()
router = APIRouter()


async def _proxy_graph_l7_get(path: str, params: dict):
    base = settings.GRAPH_QUERY_URL.rstrip("/")
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                ct = response.headers.get("content-type", "")
                if "application/json" in ct:
                    return response.json()
                return response.text
            logger.warning(
                "graph-query L7 returned non-200",
                path=path,
                status=response.status_code,
                body=response.text[:500],
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Graph query returned HTTP {response.status_code}",
            )
    except httpx.ConnectError as e:
        logger.error("Cannot reach graph-query for L7", error=str(e), url=url)
        raise HTTPException(status_code=503, detail="Graph query service unavailable") from e
    except httpx.TimeoutException as e:
        logger.error("graph-query L7 timed out", error=str(e), url=url)
        raise HTTPException(status_code=504, detail="Graph query service timed out") from e
    except httpx.HTTPError as e:
        logger.error("graph-query L7 HTTP error", error=str(e), url=url)
        raise HTTPException(status_code=502, detail="Graph query service error") from e


@router.get("/communications")
async def get_l7_communications(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=10000),
    current_user: dict = Depends(get_current_user),
):
    params = {"analysis_id": analysis_id, "limit": limit}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if namespace is not None:
        params["namespace"] = namespace
    if protocol is not None:
        params["protocol"] = protocol
    return await _proxy_graph_l7_get("/l7/communications", params)


@router.get("/dependencies/graph")
async def get_l7_dependency_graph(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    protocols: Optional[str] = Query(None, description="Comma-separated protocol list (e.g. http,grpc)"),
    namespaces: Optional[str] = Query(None, description="Comma-separated namespace list"),
    include_metadata: bool = Query(True, description="Include labels/annotations/owner_kind on nodes"),
    current_user: dict = Depends(get_current_user),
):
    params = {"analysis_id": analysis_id, "include_metadata": str(include_metadata).lower()}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if namespace is not None:
        params["namespace"] = namespace
    if protocols is not None:
        params["protocols"] = protocols
    elif protocol is not None:
        params["protocol"] = protocol
    if namespaces is not None:
        params["namespaces"] = namespaces
    return await _proxy_graph_l7_get("/l7/dependencies/graph", params)


@router.get("/communications/stats")
async def get_l7_communication_stats(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    params = {"analysis_id": analysis_id}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    return await _proxy_graph_l7_get("/l7/communications/stats", params)


@router.get("/communications/error-stats")
async def get_l7_error_stats(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    params = {"analysis_id": analysis_id}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if namespace is not None:
        params["namespace"] = namespace
    return await _proxy_graph_l7_get("/l7/communications/error-stats", params)


@router.get("/dependencies/summary")
async def get_l7_dependency_summary(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None, description="Filter to namespace"),
    include_metadata: bool = Query(True, description="Include labels/annotations/owner_kind"),
    annotation_key: Optional[str] = Query(None, description="Filter workloads by annotation key (supports fnmatch globs)"),
    annotation_value: Optional[str] = Query(None, description="Filter workloads by annotation value (supports fnmatch globs)"),
    label_key: Optional[str] = Query(None, description="Filter workloads by label key (supports fnmatch globs)"),
    label_value: Optional[str] = Query(None, description="Filter workloads by label value (supports fnmatch globs)"),
    owner_name: Optional[str] = Query(None, description="Workload owner name (aliased to workload_name for L7 parity)"),
    pod_name: Optional[str] = Query(None, description="Case-insensitive substring match against workload name"),
    workload_name: Optional[str] = Query(None, description="Case-insensitive substring match against workload name"),
    filter_noise_annotations: bool = Query(False, description="Strip Kubernetes infrastructure annotations from response"),
    current_user: dict = Depends(get_current_user),
):
    params: dict = {"analysis_id": analysis_id, "include_metadata": str(include_metadata).lower()}
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if namespace is not None:
        params["namespace"] = namespace
    if annotation_key is not None:
        params["annotation_key"] = annotation_key
    if annotation_value is not None:
        params["annotation_value"] = annotation_value
    if label_key is not None:
        params["label_key"] = label_key
    if label_value is not None:
        params["label_value"] = label_value
    # owner_name is the L4 nomenclature ("Pod owner controller name"). For L7
    # the equivalent identity is the L7Workload.name, so the backend aliases
    # the field. Explicit workload_name wins when both are provided.
    if workload_name is not None:
        params["workload_name"] = workload_name
    elif owner_name is not None:
        params["workload_name"] = owner_name
    if pod_name is not None:
        params["pod_name"] = pod_name
    if filter_noise_annotations:
        params["filter_noise_annotations"] = "true"
    return await _proxy_graph_l7_get("/l7/dependencies/summary", params)


@router.get("/dependencies/tree-summary")
async def get_l7_dependency_tree_summary(
    analysis_id: str = Query(..., description="Analysis ID"),
    cluster_id: Optional[str] = Query(None),
    workload_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=3),
    label_key: Optional[str] = Query(None, description="Filter by label key"),
    label_value: Optional[str] = Query(None, description="Filter by label value"),
    annotation_key: Optional[str] = Query(None, description="Filter by annotation key"),
    annotation_value: Optional[str] = Query(None, description="Filter by annotation value"),
    include_metadata: bool = Query(True, description="Include labels/annotations/owner_kind"),
    workload_name_exact: bool = Query(
        True,
        description="Exact name match (default True for backward compat); set False for case-insensitive substring",
    ),
    current_user: dict = Depends(get_current_user),
):
    params: dict = {
        "analysis_id": analysis_id,
        "depth": depth,
        "include_metadata": str(include_metadata).lower(),
        "workload_name_exact": str(workload_name_exact).lower(),
    }
    if cluster_id is not None:
        params["cluster_id"] = cluster_id
    if workload_name is not None:
        params["workload_name"] = workload_name
    if namespace is not None:
        params["namespace"] = namespace
    if label_key is not None:
        params["label_key"] = label_key
    if label_value is not None:
        params["label_value"] = label_value
    if annotation_key is not None:
        params["annotation_key"] = annotation_key
    if annotation_value is not None:
        params["annotation_value"] = annotation_value
    return await _proxy_graph_l7_get("/l7/dependencies/tree-summary", params)
