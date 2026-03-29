"""
API Routers Package - Controller Layer

This package contains all API route handlers (controllers).
Each router handles a specific domain area.

Router Responsibilities:
- HTTP request/response handling
- Input validation (via Pydantic)
- Dependency injection
- Error handling with HTTP status codes
- NO business logic (delegate to services)
"""

# Import all routers for easy access
from . import (
    auth,
    clusters,
    analyses,
    workloads,
    event_types,
    namespaces,
    communications,
    websocket,
    events,  # NEW: Layered architecture events router
)

__all__ = [
    "auth",
    "clusters",
    "analyses",
    "workloads",
    "event_types",
    "namespaces",
    "communications",
    "websocket",
    "events",
]
