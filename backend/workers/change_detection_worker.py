"""
Change Detection Worker - Background task for periodic change detection

Version: 1.1.2
Last Updated: 2026-01-08
Build: Fix POSTGRES_PASSWORD env var order for K8s substitution

This worker runs as a background task and periodically detects infrastructure
changes for running analyses, recording them to the database.

Features:
- Periodic change detection for active analyses
- Workload and connection change detection
- Risk assessment and blast radius calculation
- Automatic recording of change events
- WebSocket notifications for critical changes
- Circuit breaker pattern for failing clusters
- Graceful degradation on failures
- Leader election support for horizontal scaling

Configuration (via environment variables):
- CHANGE_DETECTION_INTERVAL: Detection interval in seconds (default: 60)
- CHANGE_DETECTION_ENABLED: Enable/disable worker (default: false)
- CHANGE_DETECTION_CIRCUIT_BREAKER_THRESHOLD: Failures before circuit opens (default: 3)
- CHANGE_DETECTION_CIRCUIT_BREAKER_RESET: Seconds before circuit reset (default: 300)
"""

import asyncio
import os
from typing import Dict, Any, Optional, Set, List
from datetime import datetime, timedelta
import structlog

from database.postgresql import database
from services.change_detection_service import ChangeDetectionService, get_change_detection_service

logger = structlog.get_logger(__name__)


class ChangeDetectionWorker:
    """
    Background worker that periodically detects changes.
    
    Features:
    - Runs at configurable intervals when analyses are active
    - Compares current state with previous state
    - Creates change_events for detected differences
    - Notifies via WebSocket for critical changes
    
    Uses circuit breaker pattern to avoid overwhelming failing clusters.
    """
    
    def __init__(self):
        # Configuration from environment
        self.DETECTION_INTERVAL = int(os.getenv("CHANGE_DETECTION_INTERVAL", "60"))
        self.ENABLED = os.getenv("CHANGE_DETECTION_ENABLED", "false").lower() == "true"
        self.CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CHANGE_DETECTION_CIRCUIT_BREAKER_THRESHOLD", "3"))
        self.CIRCUIT_BREAKER_RESET_TIME = int(os.getenv("CHANGE_DETECTION_CIRCUIT_BREAKER_RESET", "300"))
        self.LOOKBACK_MINUTES = int(os.getenv("CHANGE_DETECTION_LOOKBACK_MINUTES", "5"))
        
        # Internal state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._detection_service: Optional[ChangeDetectionService] = None
        self._failure_counts: Dict[int, int] = {}  # cluster_id -> failure count
        self._circuit_open_until: Dict[int, datetime] = {}  # cluster_id -> reopen time
        self._last_detection: Dict[int, datetime] = {}  # analysis_id -> last detection time
        self._active_analyses: Set[int] = set()  # Set of active analysis IDs
    
    @property
    def detection_service(self) -> ChangeDetectionService:
        """Lazy-load detection service"""
        if self._detection_service is None:
            self._detection_service = get_change_detection_service()
        return self._detection_service
    
    async def start(self) -> None:
        """Start the background detection task"""
        if not self.ENABLED:
            logger.info("Change detection worker is disabled")
            return
        
        if self._running:
            logger.warning("Change detection worker already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_detection_loop())
        
        logger.info(
            "Change detection worker started",
            interval=self.DETECTION_INTERVAL,
            lookback_minutes=self.LOOKBACK_MINUTES,
            circuit_breaker_threshold=self.CIRCUIT_BREAKER_THRESHOLD
        )
    
    async def stop(self) -> None:
        """Stop the background detection task"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self._task = None
        self._active_analyses.clear()
        
        logger.info("Change detection worker stopped")
    
    async def _run_detection_loop(self) -> None:
        """Main detection loop - runs at configured interval"""
        # Initial delay to let the system stabilize
        await asyncio.sleep(10)
        
        while self._running:
            try:
                await self._run_detection_cycle()
            except Exception as e:
                logger.error("Change detection cycle failed", error=str(e))
            
            await asyncio.sleep(self.DETECTION_INTERVAL)
    
    async def _run_detection_cycle(self) -> None:
        """Run a single detection cycle for all active analyses"""
        # Get active analyses from database
        active_analyses = await self._get_active_analyses()
        
        if not active_analyses:
            logger.debug("No active analyses for change detection")
            return
        
        logger.debug(
            "Starting change detection cycle",
            analysis_count=len(active_analyses)
        )
        
        results = {
            "checked": 0,
            "changes_detected": 0,
            "errors": 0,
            "skipped": 0
        }
        
        # Process each analysis
        for analysis in active_analyses:
            analysis_id = analysis["id"]
            cluster_id = analysis["cluster_id"]
            
            # Check circuit breaker
            if self._is_circuit_open(cluster_id):
                results["skipped"] += 1
                continue
            
            try:
                changes = await self._detect_changes_for_analysis(analysis)
                results["checked"] += 1
                results["changes_detected"] += len(changes)
                
                # Record changes to database
                for change in changes:
                    await self.detection_service.record_change_event(
                        cluster_id=cluster_id,
                        change=change,
                        analysis_id=analysis_id,
                        changed_by="auto-discovery"
                    )
                
                # Notify via WebSocket for critical changes
                critical_changes = [c for c in changes if c.get("risk_level") == "critical"]
                if critical_changes:
                    await self._notify_critical_changes(analysis_id, critical_changes)
                
                # Reset failure count on success
                self._failure_counts[cluster_id] = 0
                self._last_detection[analysis_id] = datetime.utcnow()
                
            except Exception as e:
                logger.error(
                    "Change detection failed for analysis",
                    analysis_id=analysis_id,
                    cluster_id=cluster_id,
                    error=str(e)
                )
                results["errors"] += 1
                self._record_failure(cluster_id)
        
        logger.info(
            "Change detection cycle completed",
            **results
        )
    
    async def _get_active_analyses(self) -> List[Dict[str, Any]]:
        """Get list of active (running) analyses with change detection enabled"""
        query = """
        SELECT 
            a.id,
            a.name,
            a.cluster_id,
            a.status,
            a.started_at
        FROM analyses a
        WHERE a.status = 'running'
          AND a.is_active = true
          AND a.change_detection_enabled = true
        ORDER BY a.id
        """
        
        query_fallback = """
        SELECT 
            a.id,
            a.name,
            a.cluster_id,
            a.status,
            a.started_at
        FROM analyses a
        WHERE a.status = 'running'
          AND a.is_active = true
        ORDER BY a.id
        """
        
        try:
            analyses = await database.fetch_all(query)
            return [dict(a) for a in analyses]
        except Exception as e:
            if "change_detection_enabled" in str(e) or "UndefinedColumn" in str(e):
                logger.warning("change_detection_enabled column not found, using fallback query")
                try:
                    analyses = await database.fetch_all(query_fallback)
                    return [dict(a) for a in analyses]
                except Exception as e2:
                    logger.error("Failed to fetch active analyses (fallback)", error=str(e2))
                    return []
            logger.error("Failed to fetch active analyses", error=str(e))
            return []
    
    async def _detect_changes_for_analysis(
        self, 
        analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect changes for a specific analysis"""
        analysis_id = analysis["id"]
        cluster_id = analysis["cluster_id"]
        
        # Use overlap window to avoid missing changes at boundaries
        lookback = self.LOOKBACK_MINUTES + 1  # Add 1 minute overlap
        
        changes = await self.detection_service.detect_all_changes(
            cluster_id=cluster_id,
            analysis_id=analysis_id,
            since_minutes=lookback
        )
        
        # Filter out already recorded changes (deduplication)
        new_changes = await self._filter_new_changes(changes, cluster_id)
        
        if new_changes:
            logger.info(
                "Changes detected",
                analysis_id=analysis_id,
                cluster_id=cluster_id,
                total_detected=len(changes),
                new_changes=len(new_changes)
            )
        
        return new_changes
    
    async def _filter_new_changes(
        self, 
        changes: List[Dict[str, Any]],
        cluster_id: int
    ) -> List[Dict[str, Any]]:
        """Filter out changes that have already been recorded"""
        if not changes:
            return []
        
        # Get recent change events to check for duplicates
        query = """
        SELECT target, change_type, detected_at
        FROM change_events
        WHERE cluster_id = :cluster_id
          AND detected_at >= NOW() - INTERVAL '15 minutes'
        """
        
        try:
            recent_events = await database.fetch_all(query, {"cluster_id": cluster_id})
            recent_keys = set(
                f"{e['target']}:{e['change_type']}:{e['detected_at'].strftime('%Y%m%d%H%M')}"
                for e in recent_events
            )
            
            # Filter to only new changes
            new_changes = []
            for change in changes:
                key = f"{change.get('target')}:{change.get('change_type')}:{change.get('detected_at', datetime.utcnow()).strftime('%Y%m%d%H%M')}"
                if key not in recent_keys:
                    new_changes.append(change)
            
            return new_changes
            
        except Exception as e:
            logger.warning("Failed to filter duplicates, returning all changes", error=str(e))
            return changes
    
    async def _notify_critical_changes(
        self,
        analysis_id: int,
        critical_changes: List[Dict[str, Any]]
    ) -> None:
        """Send WebSocket notifications for critical changes"""
        try:
            # Import WebSocket manager lazily to avoid circular imports
            from routers.websocket import broadcast_to_analysis
            
            for change in critical_changes:
                notification = {
                    "type": "critical_change",
                    "analysis_id": analysis_id,
                    "change": {
                        "change_type": change.get("change_type"),
                        "target": change.get("target"),
                        "namespace": change.get("namespace"),
                        "risk_level": change.get("risk_level"),
                        "details": change.get("details"),
                        "affected_services": change.get("affected_services", 0)
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await broadcast_to_analysis(analysis_id, notification)
                
                logger.info(
                    "Critical change notification sent",
                    analysis_id=analysis_id,
                    change_type=change.get("change_type"),
                    target=change.get("target")
                )
                
        except ImportError:
            logger.debug("WebSocket module not available for notifications")
        except Exception as e:
            logger.warning("Failed to send WebSocket notification", error=str(e))
    
    def _record_failure(self, cluster_id: int) -> None:
        """Record a failure for circuit breaker logic"""
        self._failure_counts[cluster_id] = self._failure_counts.get(cluster_id, 0) + 1
        
        if self._failure_counts[cluster_id] >= self.CIRCUIT_BREAKER_THRESHOLD:
            # Open circuit breaker
            self._circuit_open_until[cluster_id] = datetime.utcnow() + timedelta(
                seconds=self.CIRCUIT_BREAKER_RESET_TIME
            )
            logger.warning(
                "Circuit breaker opened for cluster",
                cluster_id=cluster_id,
                failure_count=self._failure_counts[cluster_id],
                reopen_at=self._circuit_open_until[cluster_id].isoformat()
            )
    
    def _is_circuit_open(self, cluster_id: int) -> bool:
        """Check if circuit breaker is open for a cluster"""
        if cluster_id not in self._circuit_open_until:
            return False
        
        if datetime.utcnow() >= self._circuit_open_until[cluster_id]:
            # Reset circuit breaker
            del self._circuit_open_until[cluster_id]
            self._failure_counts[cluster_id] = 0
            logger.info("Circuit breaker reset for cluster", cluster_id=cluster_id)
            return False
        
        return True
    
    # ============ Manual Control Methods ============
    
    async def trigger_detection(self, analysis_id: int) -> Dict[str, Any]:
        """
        Manually trigger change detection for a specific analysis.
        Useful for on-demand detection outside the regular schedule.
        """
        # Get analysis info
        query = """
        SELECT id, name, cluster_id, status
        FROM analyses
        WHERE id = :analysis_id
        """
        
        analysis = await database.fetch_one(query, {"analysis_id": analysis_id})
        
        if not analysis:
            return {"error": f"Analysis {analysis_id} not found"}
        
        if analysis["status"] != "running":
            return {"error": f"Analysis {analysis_id} is not running (status: {analysis['status']})"}
        
        # Reset circuit breaker for this cluster
        cluster_id = analysis["cluster_id"]
        if cluster_id in self._circuit_open_until:
            del self._circuit_open_until[cluster_id]
        self._failure_counts[cluster_id] = 0
        
        try:
            changes = await self._detect_changes_for_analysis(dict(analysis))
            
            # Record changes
            for change in changes:
                await self.detection_service.record_change_event(
                    cluster_id=cluster_id,
                    change=change,
                    analysis_id=analysis_id,
                    changed_by="manual-trigger"
                )
            
            return {
                "analysis_id": analysis_id,
                "cluster_id": cluster_id,
                "changes_detected": len(changes),
                "changes": changes[:10],  # Return first 10 for preview
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Manual change detection failed", analysis_id=analysis_id, error=str(e))
            return {"error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the change detection worker"""
        return {
            "running": self._running,
            "enabled": self.ENABLED,
            "config": {
                "detection_interval": self.DETECTION_INTERVAL,
                "lookback_minutes": self.LOOKBACK_MINUTES,
                "circuit_breaker_threshold": self.CIRCUIT_BREAKER_THRESHOLD,
                "circuit_breaker_reset_time": self.CIRCUIT_BREAKER_RESET_TIME
            },
            "last_detections": {
                aid: ts.isoformat()
                for aid, ts in self._last_detection.items()
            },
            "failure_counts": dict(self._failure_counts),
            "circuits_open": {
                cid: ts.isoformat()
                for cid, ts in self._circuit_open_until.items()
            }
        }
    
    async def enable(self) -> Dict[str, Any]:
        """Enable and start the worker"""
        self.ENABLED = True
        await self.start()
        return {"status": "enabled", "running": self._running}
    
    async def disable(self) -> Dict[str, Any]:
        """Disable and stop the worker"""
        self.ENABLED = False
        await self.stop()
        return {"status": "disabled", "running": self._running}


# Singleton instance
change_detection_worker = ChangeDetectionWorker()


# Export public API
__all__ = [
    "ChangeDetectionWorker",
    "change_detection_worker"
]
