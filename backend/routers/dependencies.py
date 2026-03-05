"""
Dependencies router - Dependency graph endpoints
"""

from fastapi import APIRouter, Depends
from utils.jwt_utils import get_current_user, require_permissions

router = APIRouter()

@router.get("/dependencies/graph")
async def get_dependency_graph(current_user: dict = Depends(require_permissions("dependencies.view"))):
    """Get dependency graph - placeholder"""
    return {
        "nodes": [],
        "edges": [],
        "message": "Dependency graph - coming in Sprint 7-8"
    }
