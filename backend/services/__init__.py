"""
Services Package - Business Logic Layer

This package contains service classes that encapsulate business logic.
Services orchestrate between repositories and provide a unified interface
for controllers.

Design Principles:
- Single Responsibility: Each service handles one domain area
- Dependency Injection: Services receive repositories via constructor
- Orchestration: Services coordinate multiple repository calls
- No HTTP/API concerns: Services are protocol-agnostic
"""

from .event_service import EventService, get_event_service
from .change_detection_service import (
    ChangeDetectionService,
    ChangeType,
    RiskLevel,
    get_change_detection_service
)

__all__ = [
    "EventService",
    "get_event_service",
    "ChangeDetectionService",
    "ChangeType",
    "RiskLevel",
    "get_change_detection_service",
]
