"""
Communications Router - Proxies to graph-query service
"""

import logging
import httpx
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Communications"])


async def proxy_to_graph_query(path: str, params: dict = None, json_body: dict = None) -> dict:
    """
    Proxy request to graph-query service (GET or POST)
    """
    url = f"{settings.graph_query_url}{path}"
    
    if params:
        params = {k: v for k, v in params.items() if v is not None}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if json_body is not None:
                response = await client.post(url, json=json_body)
            else:
                response = await client.get(url, params=params)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/plain" in content_type:
                return {"content": response.text, "format": "text"}
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Graph query error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError as e:
        logger.error(f"Graph query connection error: {e}")
        raise HTTPException(status_code=503, detail="Graph query service unavailable")


@router.get("/communications")
async def get_communications(
    cluster_id: int = Query(..., description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    protocol: Optional[str] = Query(None, description="Filter by protocol"),
    limit: int = Query(100, description="Limit results")
):
    """
    Get communications list
    """
    params = {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id,
        "namespace": namespace,
        "protocol": protocol,
        "limit": limit
    }
    return await proxy_to_graph_query("/communications", params)


@router.get("/communications/graph")
async def get_dependency_graph(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    depth: int = Query(2, description="Traversal depth")
):
    """
    Get dependency graph for visualization
    
    Returns nodes and edges for the Live Map.
    For multi-cluster analyses, only analysis_id is required.
    For single-cluster, cluster_id can be provided for additional filtering.
    """
    params = {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id,
        "namespace": namespace,
        "depth": depth
    }
    return await proxy_to_graph_query("/dependencies/graph", params)


@router.get("/communications/cross-namespace")
async def get_cross_namespace_communications(
    cluster_id: int = Query(..., description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    limit: int = Query(50, description="Limit results")
):
    """
    Get cross-namespace communications (potential security risk)
    """
    params = {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id,
        "limit": limit
    }
    return await proxy_to_graph_query("/communications/cross-namespace", params)


@router.get("/communications/high-risk")
async def get_high_risk_communications(
    cluster_id: int = Query(..., description="Cluster ID"),
    risk_threshold: float = Query(0.5, description="Risk threshold"),
    limit: int = Query(50, description="Limit results")
):
    """
    Get high-risk communications
    """
    params = {
        "cluster_id": cluster_id,
        "risk_threshold": risk_threshold,
        "limit": limit
    }
    return await proxy_to_graph_query("/communications/high-risk", params)


@router.get("/communications/external")
async def get_external_communications(
    cluster_id: int = Query(..., description="Cluster ID"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID"),
    limit: int = Query(50, description="Limit results")
):
    """
    Get external communications (to endpoints outside the cluster)
    """
    params = {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id,
        "limit": limit
    }
    return await proxy_to_graph_query("/communications/external", params)


@router.get("/communications/stats")
async def get_communication_stats(
    cluster_id: Optional[int] = Query(None, description="Cluster ID (optional for multi-cluster)"),
    analysis_id: Optional[int] = Query(None, description="Filter by analysis ID")
):
    """
    Get communication statistics.
    For multi-cluster analyses, only analysis_id is required.
    """
    params = {
        "cluster_id": cluster_id,
        "analysis_id": analysis_id
    }
    return await proxy_to_graph_query("/communications/stats", params)


@router.get("/communications/dependencies/stream")
async def find_pod_dependencies(
    analysis_id: Optional[int] = Query(None),
    cluster_id: Optional[int] = Query(None),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    label_key: Optional[str] = Query(None),
    label_value: Optional[str] = Query(None),
    annotation_key: Optional[str] = Query(None),
    annotation_value: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=5),
    format: Optional[str] = Query("json"),
):
    """Proxy: find pod dependencies (upstream/downstream/callers)"""
    params = {
        "analysis_id": analysis_id, "cluster_id": cluster_id,
        "pod_name": pod_name, "namespace": namespace,
        "owner_name": owner_name, "label_key": label_key,
        "label_value": label_value, "annotation_key": annotation_key,
        "annotation_value": annotation_value, "ip": ip,
        "depth": depth, "format": format,
    }
    return await proxy_to_graph_query("/dependencies/stream", params)


@router.post("/communications/dependencies/batch")
async def batch_find_dependencies(request: dict):
    """Proxy: batch find dependencies for multiple services"""
    return await proxy_to_graph_query("/dependencies/batch", json_body=request)


@router.get("/communications/dependencies/diff")
async def diff_dependencies(
    analysis_id_before: str = Query(...),
    analysis_id_after: str = Query(...),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    cluster_id: Optional[int] = Query(None),
):
    """Proxy: diff dependencies between two analysis runs"""
    params = {
        "analysis_id_before": analysis_id_before,
        "analysis_id_after": analysis_id_after,
        "pod_name": pod_name, "namespace": namespace,
        "owner_name": owner_name, "cluster_id": cluster_id,
    }
    return await proxy_to_graph_query("/dependencies/diff", params)

@router.get("/communications/dependencies/summary")
async def get_dependency_summary(
    analysis_ids: List[int] = Query(...),
    cluster_id: Optional[int] = Query(None),
    pod_name: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    label_key: Optional[str] = Query(None),
    label_value: Optional[str] = Query(None),
    annotation_key: Optional[str] = Query(None),
    annotation_value: Optional[str] = Query(None),
    ip: Optional[str] = Query(None),
    depth: int = Query(1, ge=1, le=5),
):
    """Proxy: AI-agent-friendly dependency summary grouped by category"""
    params = {
        "analysis_ids": [str(a) for a in analysis_ids],
        "cluster_id": cluster_id, "pod_name": pod_name,
        "namespace": namespace, "owner_name": owner_name,
        "label_key": label_key, "label_value": label_value,
        "annotation_key": annotation_key, "annotation_value": annotation_value,
        "ip": ip, "depth": depth,
    }
    return await proxy_to_graph_query("/dependencies/summary", params)


# NOTE: /communications/dependencies/impact is backend-only (requires blast_radius logic).
# External clients should call the backend API directly for impact assessments.

