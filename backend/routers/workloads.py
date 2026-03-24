"""
Enhanced Workloads router - Kubernetes workload discovery and management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from database.postgresql import database
from utils.jwt_utils import get_current_user, require_permissions
from services.kubernetes_service import k8s_service

logger = structlog.get_logger()
router = APIRouter()

# Pydantic schemas
class WorkloadResponse(BaseModel):
    id: int
    cluster_id: int
    namespace: str = "unknown"
    workload_type: str = "unknown"
    name: str = "unknown"
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    status: str = "unknown"
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class NamespaceResponse(BaseModel):
    id: int
    name: str = "unknown"
    labels: Dict[str, str] = {}
    status: str = "active"
    workload_count: int = 0

@router.get("/workloads", response_model=List[WorkloadResponse])
async def get_workloads(
    cluster_id: int = Query(..., description="Cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    workload_type: Optional[str] = Query(None, description="Filter by workload type"),
    is_active: bool = Query(True, description="Filter by active status")
):
    """Get workloads from database"""
    try:
        # Build query
        query = """
        SELECT w.id, w.cluster_id, n.name as namespace, w.workload_type, w.name,
               w.labels, w.annotations, w.status, w.is_active, w.created_at, w.updated_at
        FROM workloads w
        JOIN namespaces n ON w.namespace_id = n.id
        WHERE w.cluster_id = :cluster_id
        """
        
        params = {"cluster_id": cluster_id}
        
        if namespace:
            query += " AND n.name = :namespace"
            params["namespace"] = namespace
        
        if workload_type:
            query += " AND w.workload_type = :workload_type"
            params["workload_type"] = workload_type
        
        if is_active is not None:
            query += " AND w.is_active = :is_active"
            params["is_active"] = is_active
        
        query += " ORDER BY n.name, w.name"
        
        workloads = await database.fetch_all(query, params)
        
        result = []
        for workload in workloads:
            result.append(WorkloadResponse(
                id=workload["id"],
                cluster_id=workload["cluster_id"],
                namespace=workload["namespace"],
                workload_type=workload["workload_type"],
                name=workload["name"],
                labels=workload["labels"] or {},
                annotations=workload["annotations"] or {},
                status=workload["status"],
                is_active=workload["is_active"],
                created_at=workload["created_at"],
                updated_at=workload["updated_at"]
            ))
        
        return result
        
    except Exception as e:
        logger.error("Get workloads failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workloads"
        )

# NOTE: /namespaces endpoint moved to routers/namespaces.py
# Uses Redis cache + cluster-manager gRPC for Kubernetes API access

class WorkloadStatsResponse(BaseModel):
    total_workloads: int
    active_workloads: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    namespace_count: int

@router.get("/workloads/stats/{cluster_id}", response_model=WorkloadStatsResponse)
async def get_workload_stats(
    cluster_id: int,
    analysis_id: Optional[int] = Query(None, description="Optional analysis ID for analysis-specific stats")
):
    """Get workload statistics for a cluster.
    
    When analysis_id is provided, returns stats for workloads observed during that analysis (from Neo4j).
    Otherwise, returns stats for all workloads in the cluster (from PostgreSQL).
    """
    from database.neo4j import neo4j_service
    
    try:
        # When analysis_id is provided, use Neo4j for analysis-specific stats
        if analysis_id:
            try:
                neo4j_workloads = neo4j_service.get_workloads(cluster_id=cluster_id, analysis_id=analysis_id)
                
                # Always use Neo4j results when analysis_id is provided (even if empty list)
                # This ensures users see analysis-specific data, not cluster-wide fallback
                if neo4j_workloads is not None:  # None means error, [] means no workloads observed
                    total_workloads = len(neo4j_workloads)
                    active_workloads = sum(1 for w in neo4j_workloads if w.get('status') in ['Running', 'Active', None])
                    
                    # Count by type
                    by_type: Dict[str, int] = {}
                    for w in neo4j_workloads:
                        wtype = w.get('type') or w.get('kind') or 'Unknown'
                        by_type[wtype] = by_type.get(wtype, 0) + 1
                    
                    # Count by status
                    by_status: Dict[str, int] = {}
                    for w in neo4j_workloads:
                        wstatus = w.get('status') or 'Running'
                        by_status[wstatus] = by_status.get(wstatus, 0) + 1
                    
                    # Count unique namespaces
                    namespaces = set(w.get('namespace') for w in neo4j_workloads if w.get('namespace'))
                    namespace_count = len(namespaces)
                    
                    logger.debug(
                        "Got analysis-specific workload stats from Neo4j",
                        analysis_id=analysis_id,
                        total=total_workloads,
                        active=active_workloads
                    )
                    
                    return WorkloadStatsResponse(
                        total_workloads=total_workloads,
                        active_workloads=active_workloads,
                        by_type=by_type,
                        by_status=by_status,
                        namespace_count=namespace_count
                    )
            except Exception as neo4j_err:
                logger.warning("Neo4j query failed, falling back to PostgreSQL", error=str(neo4j_err))
        
        # Fallback: cluster-wide stats from PostgreSQL
        total_query = """
        SELECT COUNT(*) as count FROM workloads WHERE cluster_id = :cluster_id
        """
        total_result = await database.fetch_one(total_query, {"cluster_id": cluster_id})
        total_workloads = total_result["count"] if total_result else 0
        
        # Active workloads
        active_query = """
        SELECT COUNT(*) as count FROM workloads WHERE cluster_id = :cluster_id AND is_active = true
        """
        active_result = await database.fetch_one(active_query, {"cluster_id": cluster_id})
        active_workloads = active_result["count"] if active_result else 0
        
        # By type
        type_query = """
        SELECT workload_type, COUNT(*) as count 
        FROM workloads WHERE cluster_id = :cluster_id 
        GROUP BY workload_type
        """
        type_results = await database.fetch_all(type_query, {"cluster_id": cluster_id})
        by_type = {row["workload_type"]: row["count"] for row in type_results}
        
        # By status
        status_query = """
        SELECT status, COUNT(*) as count 
        FROM workloads WHERE cluster_id = :cluster_id 
        GROUP BY status
        """
        status_results = await database.fetch_all(status_query, {"cluster_id": cluster_id})
        by_status = {row["status"]: row["count"] for row in status_results}
        
        # Namespace count
        namespace_query = """
        SELECT COUNT(DISTINCT namespace_id) as count FROM workloads WHERE cluster_id = :cluster_id
        """
        namespace_result = await database.fetch_one(namespace_query, {"cluster_id": cluster_id})
        namespace_count = namespace_result["count"] if namespace_result else 0
        
        return WorkloadStatsResponse(
            total_workloads=total_workloads,
            active_workloads=active_workloads,
            by_type=by_type,
            by_status=by_status,
            namespace_count=namespace_count
        )
        
    except Exception as e:
        logger.error("Get workload stats failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workload stats"
        )

@router.post("/discover/{cluster_id}")
async def discover_cluster_workloads(
    cluster_id: int
):
    """Trigger workload discovery for cluster"""
    try:
        # Verify cluster exists
        cluster = await database.fetch_one(
            "SELECT id, name FROM clusters WHERE id = :cluster_id AND status = 'active'",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )
        
        # Start discovery
        logger.info("Starting workload discovery", cluster_id=cluster_id, user=current_user["username"])
        
        discovery_results = await k8s_service.full_cluster_discovery(cluster_id)
        
        return {
            "message": f"Discovery completed for cluster {cluster['name']}",
            "cluster_id": cluster_id,
            "cluster_name": cluster["name"],
            "results": discovery_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Workload discovery failed", cluster_id=cluster_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discovery failed"
        )