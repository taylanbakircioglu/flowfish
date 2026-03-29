"""
Repositories Package - Data Access Layer

This package contains repository classes that handle all database operations.
Repositories abstract away the database implementation details from the service layer.

Design Principles:
- Single Responsibility: Each repository handles one entity/aggregate
- Dependency Injection: Repositories receive database clients via constructor
- Query Building: Complex queries are built within repositories
- No Business Logic: Repositories only handle data access
"""

from .event_repository import EventRepository, ClickHouseEventRepository
from .change_detection_repository import (
    ChangeDetectionRepository,
    ClickHouseChangeDetectionRepository,
    get_change_detection_repository,
    ConnectionRecord,
    TrafficStats,
    DNSRecord,
    ProcessRecord,
    ErrorStats,
)

__all__ = [
    # Event Repository
    "EventRepository",
    "ClickHouseEventRepository",
    
    # Change Detection Repository
    "ChangeDetectionRepository",
    "ClickHouseChangeDetectionRepository",
    "get_change_detection_repository",
    
    # Data classes
    "ConnectionRecord",
    "TrafficStats",
    "DNSRecord",
    "ProcessRecord",
    "ErrorStats",
]

