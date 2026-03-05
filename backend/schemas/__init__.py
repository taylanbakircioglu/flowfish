"""
Schemas Package - Data Transfer Objects (DTOs)

This package contains Pydantic models for API request/response validation.
Schemas define the contract between API and clients.

Design Principles:
- Validation: Pydantic handles input validation
- Documentation: Schemas auto-generate OpenAPI docs
- Separation: DTOs are separate from database models
- Versioning: Schema changes are API version changes
"""

from .events import (
    EventType,
    EventQueryParams,
    EventStatsParams,
    EventStats,
    TimeRange,
    NamespaceCount,
    PodCount,
    Event,
    EventsListResponse,
    DnsQueryEvent,
    DnsQueriesResponse,
    SniEvent,
    SniEventsResponse,
)

__all__ = [
    # Enums
    "EventType",
    # Request DTOs
    "EventQueryParams",
    "EventStatsParams",
    # Response DTOs
    "EventStats",
    "TimeRange",
    "NamespaceCount",
    "PodCount",
    "Event",
    "EventsListResponse",
    "DnsQueryEvent",
    "DnsQueriesResponse",
    "SniEvent",
    "SniEventsResponse",
]
