"""Health Check Endpoints"""

from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "flowfish-api-gateway",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/readiness")
async def readiness():
    """Readiness probe"""
    # TODO: Check if all gRPC connections are ready
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/liveness")
async def liveness():
    """Liveness probe"""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }

