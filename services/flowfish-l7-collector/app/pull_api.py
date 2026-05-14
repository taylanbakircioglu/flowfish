"""Pull API endpoints for Flowfish L7 Ingestion Service to consume."""
import time
from fastapi import APIRouter, Query

from app.config import config

router = APIRouter()

_buffer = None
_start_time = time.time()


def set_buffer(buffer):
    global _buffer
    _buffer = buffer


@router.get("/health")
async def health():
    stats = await _buffer.get_stats()
    return {
        "status": "healthy",
        "buffer_size": stats["buffer_size"],
        "uptime_seconds": int(time.time() - _start_time),
        "protocols": stats["protocols"],
    }


@router.get("/api/v1/events")
async def get_events(
    cursor: str = Query("", description="Opaque cursor from previous response"),
    limit: int = Query(500, ge=1, le=config.MAX_RESPONSE_EVENTS),
):
    events, next_cursor, has_more = await _buffer.get_events(
        cursor=cursor or None, limit=limit
    )
    return {
        "events": events,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/api/v1/stats")
async def get_stats():
    stats = await _buffer.get_stats()
    return {
        "total_events": stats["total_received"],
        "buffer_usage_percent": stats["buffer_usage_percent"],
        "protocols": stats["protocols"],
    }
