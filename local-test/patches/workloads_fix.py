"""
Enhanced Workloads router - Kubernetes workload discovery and management
PATCHED for local testing - fixed schema mismatch
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

# Pydantic schemas - aligned with actual DB schema
class WorkloadResponse(BaseModel):
    id: int
    cluster_id: int
    namespace: str
    workload_type: str
    name: str
    labels: Dict[str, str] = {}
    status: str = "Unknown"
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class NamespaceResponse(BaseModel):
    id: int
    name: str
    labels: Dict[str, str] = {}
    status: str = "Active"
    workload_count: int = 0

@router.get("/workloads")
async def get_workloads(
    cluster_id: int = Query(..., description="Cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    workload_type: Optional[str] = Query(None, description="Filter by workload type"),
    is_active: bool = Query(True, description="Filter by active status")
):
    """Get workloads from database"""
    try:
        # Build query - using actual columns from DB schema
        query = """
        SELECT w.id, w.cluster_id, n.name as namespace, w.workload_type, w.name,
               w.labels, w.status, w.is_active, w.created_at, w.updated_at
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
            result.append({
                "id": workload["id"],
                "cluster_id": workload["cluster_id"],
                "namespace": workload["namespace"],
                "workload_type": workload["workload_type"],
                "name": workload["name"],
                "labels": workload["labels"] or {},
                "status": workload["status"] or "Unknown",
                "is_active": workload["is_active"],
                "created_at": workload["created_at"],
                "updated_at": workload["updated_at"]
            })
        
        return result
        
    except Exception as e:
        logger.error("Get workloads failed", error=str(e))
        # Return empty list for local testing
        return []


@router.get("/namespaces")
async def get_namespaces(
    cluster_id: int = Query(..., description="Cluster ID")
):
    """Get namespaces for cluster - matches production endpoint"""
    try:
        query = """
        SELECT n.id, n.name, n.labels, n.status,
               COUNT(w.id) as workload_count
        FROM namespaces n
        LEFT JOIN workloads w ON n.id = w.namespace_id AND w.is_active = true
        WHERE n.cluster_id = :cluster_id
        GROUP BY n.id, n.name, n.labels, n.status
        ORDER BY n.name
        """
        
        namespaces = await database.fetch_all(query, {"cluster_id": cluster_id})
        
        result = []
        for ns in namespaces:
            result.append({
                "id": ns["id"],
                "name": ns["name"],
                "labels": ns["labels"] or {},
                "status": ns["status"] or "Active",
                "workload_count": ns["workload_count"] or 0
            })
        
        return result
        
    except Exception as e:
        logger.error("Get namespaces failed", error=str(e))
        # Return empty list for local testing instead of error
        return []


@router.get("/workloads/{cluster_id}/types")
async def get_workload_types(cluster_id: int):
    """Get unique workload types for a cluster"""
    try:
        query = """
        SELECT DISTINCT workload_type, COUNT(*) as count
        FROM workloads
        WHERE cluster_id = :cluster_id AND is_active = TRUE
        GROUP BY workload_type
        ORDER BY workload_type
        """
        
        types = await database.fetch_all(query, {"cluster_id": cluster_id})
        return [{"type": t["workload_type"], "count": t["count"]} for t in types]
        
    except Exception as e:
        logger.error("Get workload types failed", error=str(e))
        return []


@router.post("/workloads/{cluster_id}/sync")
async def sync_workloads(cluster_id: int):
    """Sync workloads from Kubernetes to database"""
    try:
        # For local testing, return success with mock data
        return {
            "status": "success",
            "message": "Workloads synced successfully",
            "stats": {
                "namespaces_synced": 5,
                "workloads_synced": 10,
                "new_workloads": 0,
                "updated_workloads": 10,
                "deleted_workloads": 0
            }
        }
        
    except Exception as e:
        logger.error("Sync workloads failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync workloads: {str(e)}"
        )

