"""
Detection Strategies Module

Provides different strategies for change detection:
- Baseline: Compare current state against initial baseline
- Rolling Window: Compare recent period against previous period
- Run Comparison: Compare current run against previous run

Connection Levels:
- ConnectionKey: Raw TCP flow level (pod-to-pod with port) - LEGACY
- ServiceConnectionKey: Service level (workload-to-service) - RECOMMENDED
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Set, Tuple, Optional, Union, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from .service_port_registry import ServiceConnection

logger = structlog.get_logger(__name__)


@dataclass
class ConnectionKey:
    """
    LEGACY: Represents a unique TCP connection for comparison.
    
    WARNING: This tracks raw TCP flows including ephemeral ports.
    Use ServiceConnectionKey for service-level tracking instead.
    """
    source_pod: str
    dest_pod: str
    dest_port: int
    protocol: str = "TCP"
    
    def __hash__(self):
        return hash((self.source_pod, self.dest_pod, self.dest_port, self.protocol))
    
    def __eq__(self, other):
        if not isinstance(other, ConnectionKey):
            return False
        return (
            self.source_pod == other.source_pod and
            self.dest_pod == other.dest_pod and
            self.dest_port == other.dest_port and
            self.protocol == other.protocol
        )


@dataclass(frozen=True)
class ServiceConnectionKey:
    """
    Service-level connection key for change detection.
    
    This aggregates multiple TCP connections between the same
    source workload and destination service into a single logical connection.
    
    Benefits over ConnectionKey:
    - Ignores ephemeral ports (only tracks service ports)
    - Aggregates connections from different pods of the same deployment
    - Maps to Kubernetes Services instead of raw IPs
    """
    source_workload: str     # Deployment/StatefulSet name
    source_namespace: str
    dest_service: str        # Service name or external endpoint
    dest_namespace: str
    dest_port: int           # Service port (never ephemeral)
    protocol: str = "TCP"
    
    def __hash__(self):
        return hash((
            self.source_workload, 
            self.dest_service, 
            self.dest_port, 
            self.protocol
        ))
    
    def __eq__(self, other):
        if not isinstance(other, ServiceConnectionKey):
            return False
        return (
            self.source_workload == other.source_workload and
            self.dest_service == other.dest_service and
            self.dest_port == other.dest_port and
            self.protocol == other.protocol
        )
    
    def to_display_string(self) -> str:
        """Format for display in UI/logs."""
        src = f"{self.source_namespace}/{self.source_workload}"
        dst = f"{self.dest_namespace}/{self.dest_service}:{self.dest_port}"
        return f"{src} → {dst}"


@dataclass
class ConnectionDiff:
    """Result of comparing two sets of connections (legacy)"""
    added: Set[ConnectionKey]
    removed: Set[ConnectionKey]
    unchanged: Set[ConnectionKey]


@dataclass
class ServiceConnectionDiff:
    """
    Result of comparing two sets of service-level connections.
    
    This is the recommended diff type for change detection as it
    filters out ephemeral port noise.
    """
    added: Set[ServiceConnectionKey]
    removed: Set[ServiceConnectionKey]
    unchanged: Set[ServiceConnectionKey]
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self.added) > 0 or len(self.removed) > 0
    
    @property
    def total_changes(self) -> int:
        """Total number of changes."""
        return len(self.added) + len(self.removed)


class DetectionStrategy(ABC):
    """
    Abstract base class for detection strategies.
    
    Each strategy defines how to compare current state against previous state
    to detect changes.
    """
    
    name: str = "base"
    
    @abstractmethod
    def get_time_windows(
        self,
        analysis_start: datetime,
        current_time: Optional[datetime] = None
    ) -> Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]:
        """
        Get the time windows for comparison.
        
        Args:
            analysis_start: When the analysis started
            current_time: Current time (defaults to now)
            
        Returns:
            Tuple of (baseline_window, current_window) where each window is (start, end)
        """
        pass
    
    def compare_connections(
        self,
        baseline: Set[ConnectionKey],
        current: Set[ConnectionKey]
    ) -> ConnectionDiff:
        """
        LEGACY: Compare two sets of raw TCP connections.
        
        WARNING: This includes ephemeral ports and will produce noise.
        Use compare_service_connections() instead.
        
        Args:
            baseline: The baseline set of connections
            current: The current set of connections
            
        Returns:
            ConnectionDiff with added, removed, and unchanged connections
        """
        added = current - baseline
        removed = baseline - current
        unchanged = baseline & current
        
        return ConnectionDiff(
            added=added,
            removed=removed,
            unchanged=unchanged
        )
    
    def compare_service_connections(
        self,
        baseline: Set[ServiceConnectionKey],
        current: Set[ServiceConnectionKey]
    ) -> ServiceConnectionDiff:
        """
        Compare two sets of service-level connections.
        
        This is the RECOMMENDED method for change detection as it:
        - Ignores ephemeral ports
        - Aggregates pod-level connections to workload level
        - Maps destinations to Kubernetes Services
        
        Args:
            baseline: The baseline set of service connections
            current: The current set of service connections
            
        Returns:
            ServiceConnectionDiff with added, removed, and unchanged connections
        """
        added = current - baseline
        removed = baseline - current
        unchanged = baseline & current
        
        logger.debug(
            "Service connection comparison",
            baseline_count=len(baseline),
            current_count=len(current),
            added=len(added),
            removed=len(removed),
            unchanged=len(unchanged)
        )
        
        return ServiceConnectionDiff(
            added=added,
            removed=removed,
            unchanged=unchanged
        )


class BaselineStrategy(DetectionStrategy):
    """
    Baseline Strategy
    
    Captures connections during the first N minutes as baseline,
    then compares current connections against that baseline.
    
    Best for: Long-running analyses, drift detection
    
    Timeline:
    |-------- baseline (first 10 min) --------|
                                              |---- current (last 5 min) ----|
    
    Auto-adapts:
    - If analysis < 15 min: baseline = first 30%, current = last 30%
    - Minimum windows: 2 minutes each
    """
    
    name = "baseline"
    
    # Default values for longer analyses
    DEFAULT_BASELINE_MINUTES = 10
    DEFAULT_CURRENT_MINUTES = 5
    MIN_WINDOW_MINUTES = 2  # Minimum window size
    
    def __init__(
        self,
        baseline_duration_minutes: int = DEFAULT_BASELINE_MINUTES,
        current_window_minutes: int = DEFAULT_CURRENT_MINUTES
    ):
        self.baseline_duration_minutes = baseline_duration_minutes
        self.current_window_minutes = current_window_minutes
    
    def get_time_windows(
        self,
        analysis_start: datetime,
        current_time: Optional[datetime] = None
    ) -> Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]:
        """
        Get baseline and current time windows.
        
        Auto-adapts based on analysis duration:
        - Short analysis (< 15 min): baseline = first 30%, current = last 30%
        - Long analysis: uses configured defaults
        
        Baseline: [analysis_start, analysis_start + baseline_duration]
        Current: [now - current_window, now]
        """
        now = current_time or datetime.now(timezone.utc)
        
        # Ensure analysis_start is timezone-aware for comparison
        if analysis_start.tzinfo is None:
            analysis_start = analysis_start.replace(tzinfo=timezone.utc)
        
        # Calculate how long the analysis has been running
        analysis_duration = (now - analysis_start).total_seconds() / 60  # in minutes
        
        # Auto-adapt for short analyses
        if analysis_duration < 15:
            # Use percentage-based windows for short analyses
            baseline_minutes = max(self.MIN_WINDOW_MINUTES, analysis_duration * 0.3)
            current_minutes = max(self.MIN_WINDOW_MINUTES, analysis_duration * 0.3)
        else:
            # Use configured values for longer analyses
            baseline_minutes = self.baseline_duration_minutes
            current_minutes = self.current_window_minutes
        
        # Baseline window: first N minutes of analysis
        baseline_start = analysis_start
        baseline_end = analysis_start + timedelta(minutes=baseline_minutes)
        
        # Ensure baseline doesn't extend past current time
        if baseline_end > now:
            baseline_end = now - timedelta(minutes=max(1, current_minutes))
        
        # Current window: last M minutes
        current_start = now - timedelta(minutes=current_minutes)
        current_end = now
        
        # Ensure current doesn't overlap with baseline for very short analyses
        if current_start < baseline_end and analysis_duration > self.MIN_WINDOW_MINUTES * 2:
            # Leave a gap between baseline and current
            gap = timedelta(minutes=1)
            current_start = baseline_end + gap
        
        logger.debug(
            "Baseline strategy windows (auto-adapted)",
            analysis_duration_min=round(analysis_duration, 1),
            baseline_start=baseline_start.isoformat(),
            baseline_end=baseline_end.isoformat(),
            current_start=current_start.isoformat(),
            current_end=current_end.isoformat()
        )
        
        return (
            (baseline_start, baseline_end),
            (current_start, current_end)
        )


class RollingWindowStrategy(DetectionStrategy):
    """
    Rolling Window Strategy
    
    Continuously compares the current time window against the previous
    time window for real-time change detection.
    
    Best for: Continuous monitoring, alerting
    
    Timeline:
    |---- previous (5 min ago) ----|---- current (last 5 min) ----|
    
    Auto-adapts:
    - If analysis < 10 min: window = analysis_duration / 2
    - Minimum window: 2 minutes
    - Requires at least 2x window duration to have valid previous window
    """
    
    name = "rolling_window"
    
    DEFAULT_WINDOW_MINUTES = 5
    MIN_WINDOW_MINUTES = 2
    
    def __init__(self, window_minutes: int = DEFAULT_WINDOW_MINUTES):
        self.window_minutes = window_minutes
    
    def get_time_windows(
        self,
        analysis_start: datetime,
        current_time: Optional[datetime] = None
    ) -> Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]:
        """
        Get rolling time windows.
        
        Auto-adapts based on analysis duration:
        - Short analysis (< 2*window): uses half the duration as window
        - Minimum effective window: 2 minutes
        
        Previous: [now - 2*window, now - window]
        Current: [now - window, now]
        """
        now = current_time or datetime.now(timezone.utc)
        
        # Ensure analysis_start is timezone-aware for comparison
        if analysis_start.tzinfo is None:
            analysis_start = analysis_start.replace(tzinfo=timezone.utc)
        
        # Calculate how long the analysis has been running
        analysis_duration = (now - analysis_start).total_seconds() / 60  # in minutes
        
        # Auto-adapt window size for short analyses
        required_duration = self.window_minutes * 2  # Need 2x window for proper comparison
        
        if analysis_duration < required_duration:
            # Use half the analysis duration as window, with minimum
            effective_window = max(self.MIN_WINDOW_MINUTES, analysis_duration / 2)
        else:
            effective_window = self.window_minutes
        
        # Previous window
        previous_end = now - timedelta(minutes=effective_window)
        previous_start = previous_end - timedelta(minutes=effective_window)
        
        # Current window
        current_start = previous_end
        current_end = now
        
        # Ensure windows don't go before analysis start
        if previous_start < analysis_start:
            previous_start = analysis_start
            # If previous window is too short, adjust
            if (previous_end - previous_start).total_seconds() < 60:  # less than 1 minute
                # Not enough data yet for rolling comparison
                # Return overlapping windows to indicate "warming up"
                logger.info(
                    "Rolling window warming up - not enough data yet",
                    analysis_duration_min=round(analysis_duration, 1),
                    required_min=required_duration
                )
        
        logger.debug(
            "Rolling window strategy (auto-adapted)",
            analysis_duration_min=round(analysis_duration, 1),
            effective_window_min=round(effective_window, 1),
            previous_start=previous_start.isoformat(),
            previous_end=previous_end.isoformat(),
            current_start=current_start.isoformat(),
            current_end=current_end.isoformat()
        )
        
        return (
            (previous_start, previous_end),
            (current_start, current_end)
        )


class RunComparisonStrategy(DetectionStrategy):
    """
    Run Comparison Strategy
    
    Compares the current run against the previous run.
    Ideal for deployment validation and A/B testing.
    
    Best for: Deployment validation, canary deployments
    
    Timeline:
    |-------- Run N-1 --------|
                              |-------- Run N (current) --------|
    
    Fallback behavior:
    - If no previous run exists, falls back to Baseline strategy behavior
    - Compares current run against first 30% of current run as pseudo-baseline
    """
    
    name = "run_comparison"
    
    def __init__(self, previous_run_id: Optional[int] = None):
        self.previous_run_id = previous_run_id
        self._has_previous_run = previous_run_id is not None
    
    def get_time_windows(
        self,
        analysis_start: datetime,
        current_time: Optional[datetime] = None
    ) -> Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]:
        """
        For run comparison, time windows are determined by run boundaries,
        not fixed time intervals.
        
        If previous_run_id is set:
        - Previous window is placeholder (data fetched by run_id)
        - Current window is entire current run
        
        If no previous run (first run):
        - Falls back to baseline-like behavior
        - Previous = first 30% of current run
        - Current = last 30% of current run
        """
        now = current_time or datetime.now(timezone.utc)
        
        # Ensure analysis_start is timezone-aware for comparison
        if analysis_start.tzinfo is None:
            analysis_start = analysis_start.replace(tzinfo=timezone.utc)
        
        analysis_duration = (now - analysis_start).total_seconds() / 60
        
        if self._has_previous_run:
            # Normal run comparison - previous run data fetched separately
            logger.debug(
                "Run comparison with previous run",
                previous_run_id=self.previous_run_id,
                current_start=analysis_start.isoformat(),
                current_end=now.isoformat()
            )
            return (
                (analysis_start, analysis_start),  # Placeholder for previous run
                (analysis_start, now)  # Current run
            )
        else:
            # Fallback: No previous run, use baseline-like behavior
            # This allows run_comparison to work even on the first run
            baseline_duration = max(2, analysis_duration * 0.3)  # First 30%, min 2 min
            current_duration = max(2, analysis_duration * 0.3)   # Last 30%, min 2 min
            
            baseline_start = analysis_start
            baseline_end = analysis_start + timedelta(minutes=baseline_duration)
            
            current_start = now - timedelta(minutes=current_duration)
            current_end = now
            
            # Ensure no overlap
            if current_start < baseline_end:
                mid_point = analysis_start + timedelta(minutes=analysis_duration / 2)
                baseline_end = mid_point - timedelta(minutes=0.5)
                current_start = mid_point + timedelta(minutes=0.5)
            
            logger.info(
                "Run comparison fallback (no previous run) - using baseline-like behavior",
                analysis_duration_min=round(analysis_duration, 1),
                baseline_end=baseline_end.isoformat(),
                current_start=current_start.isoformat()
            )
            
            return (
                (baseline_start, baseline_end),
                (current_start, current_end)
            )


# Strategy factory
def get_strategy(strategy_name: str, **kwargs) -> DetectionStrategy:
    """
    Factory function to get a detection strategy by name.
    
    Args:
        strategy_name: Name of the strategy (baseline, rolling_window, run_comparison)
        **kwargs: Strategy-specific parameters
        
    Returns:
        Configured DetectionStrategy instance
    """
    strategies = {
        'baseline': BaselineStrategy,
        'rolling_window': RollingWindowStrategy,
        'run_comparison': RunComparisonStrategy,
    }
    
    strategy_class = strategies.get(strategy_name, BaselineStrategy)
    return strategy_class(**kwargs)
