"""
Cluster Resources Router - Enterprise caching layer with Redis

Uses cache-aside pattern:
1. Check Redis cache first
2. On cache miss, fetch from cluster-manager gRPC service
3. Store in cache with TTL
4. Return data

Cache TTLs:
- Namespaces: 2 minutes
- Deployments: 30 seconds
- Pods: 15 seconds
- Labels: 2 minutes
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import structlog

from services.cluster_cache_service import cluster_cache_service

logger = structlog.get_logger()

router = APIRouter()


@router.get("/namespaces")
async def get_namespaces(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    refresh: bool = Query(False, description="Force cache refresh")
):
    """
    Get list of namespaces from cluster.
    
    Uses Redis cache with 2-minute TTL.
    Uses cluster-manager service which has ClusterRole permissions.
    """
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
    
    try:
        namespaces = await cluster_cache_service.get_namespaces(
            cluster_id=cluster_id,
            force_refresh=refresh
        )
        
        logger.info("Retrieved namespaces", 
                   cluster_id=cluster_id, 
                   count=len(namespaces),
                   cache_refresh=refresh)
        
        return namespaces
        
    except Exception as e:
        logger.error("Failed to get namespaces", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve namespaces: {str(e)}"
        )


@router.get("/deployments")
async def get_deployments(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    refresh: bool = Query(False, description="Force cache refresh")
):
    """
    Get list of deployments from cluster.
    
    Uses Redis cache with 30-second TTL.
    Uses cluster-manager service which has ClusterRole permissions.
    """
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
    
    try:
        deployments = await cluster_cache_service.get_deployments(
            cluster_id=cluster_id,
            namespace=namespace,
            force_refresh=refresh
        )
        
        logger.info("Retrieved deployments", 
                   cluster_id=cluster_id, 
                   namespace=namespace,
                   count=len(deployments),
                   cache_refresh=refresh)
        
        return deployments
        
    except Exception as e:
        logger.error("Failed to get deployments", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve deployments: {str(e)}"
        )


@router.get("/labels")
async def get_labels(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    resource_type: str = Query("pods", description="Resource type: pods or deployments"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    refresh: bool = Query(False, description="Force cache refresh")
):
    """
    Get unique labels from cluster resources.
    
    Uses Redis cache with 2-minute TTL.
    Uses cluster-manager service which has ClusterRole permissions.
    """
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
    
    try:
        labels = await cluster_cache_service.get_labels(
            cluster_id=cluster_id,
            resource_type=resource_type,
            namespace=namespace,
            force_refresh=refresh
        )
        
        logger.info("Retrieved labels", 
                   cluster_id=cluster_id,
                   resource_type=resource_type,
                   count=len(labels),
                   cache_refresh=refresh)
        
        return labels
        
    except Exception as e:
        logger.error("Failed to get labels", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve labels: {str(e)}"
        )


@router.get("/pods")
async def get_pods(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    label_selector: Optional[str] = Query(None, description="Label selector (e.g., app=nginx)"),
    refresh: bool = Query(False, description="Force cache refresh")
):
    """
    Get list of pods from cluster.
    
    Uses Redis cache with 15-second TTL.
    Uses cluster-manager service which has ClusterRole permissions.
    """
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
    
    try:
        pods = await cluster_cache_service.get_pods(
            cluster_id=cluster_id,
            namespace=namespace,
            label_selector=label_selector,
            force_refresh=refresh
        )
        
        logger.info("Retrieved pods", 
                   cluster_id=cluster_id, 
                   namespace=namespace,
                   count=len(pods),
                   cache_refresh=refresh)
        
        return pods
        
    except Exception as e:
        logger.error("Failed to get pods", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve pods: {str(e)}"
        )


@router.get("/services")
async def get_services(
    cluster_id: Optional[int] = Query(None, description="Filter by cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace")
):
    """
    Get list of services from cluster.
    Uses ClusterConnectionManager for unified cluster access.
    
    Note: Services are not cached as they are less frequently accessed.
    """
    if not cluster_id:
        raise HTTPException(status_code=400, detail="cluster_id is required")
    
    try:
        # Use unified ClusterConnectionManager
        from services.cluster_connection_manager import cluster_connection_manager
        services = await cluster_connection_manager.get_services(cluster_id, namespace)
        
        logger.info("Retrieved services", 
                   cluster_id=cluster_id, 
                   namespace=namespace,
                   count=len(services))
        
        return services
        
    except Exception as e:
        logger.error("Failed to get services", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve services: {str(e)}"
        )


@router.post("/cache/invalidate/{cluster_id}")
async def invalidate_cluster_cache(cluster_id: int):
    """
    Invalidate all cached data for a cluster.
    Use when cluster config changes or for manual refresh.
    """
    try:
        await cluster_cache_service.invalidate_cluster(cluster_id)
        
        return {
            "message": f"Cache invalidated for cluster {cluster_id}",
            "cluster_id": cluster_id
        }
        
    except Exception as e:
        logger.error("Failed to invalidate cache", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invalidate cache: {str(e)}"
        )


@router.get("/cache/health")
async def cache_health():
    """
    Check cache service health.
    """
    try:
        health = await cluster_cache_service.health_check()
        return health
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }

