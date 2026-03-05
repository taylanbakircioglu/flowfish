"""
Auto-Stop Monitor - Automatically stops analyses when limits are exceeded

Monitors running analyses and stops them when:
1. Time limit is exceeded (duration_minutes) - Fixed Duration mode
2. Data size limit is exceeded (max_data_size_mb) - Stop on Limit mode
3. Default duration exceeded for Continuous mode (enterprise feature)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Set
import httpx

from app.config import settings
from app.database import db_manager, AnalysisStatus
from app.ingestion_client import ingestion_client

logger = logging.getLogger(__name__)


class AutoStopMonitor:
    """
    Background monitor that automatically stops analyses when limits are exceeded.
    
    Checks (in order):
    1. Time-based: If (now - started_at) > duration_minutes, stop (Fixed Duration)
    2. Size-based: If collected_data_size > max_data_size_mb, stop (Stop on Limit)
    3. Continuous default: If continuous mode and (now - started_at) > default_duration, stop
    
    Also emits warnings before auto-stop via WebSocket broadcast.
    """
    
    def __init__(self, check_interval_seconds: int = 30):
        """
        Initialize the auto-stop monitor.
        
        Args:
            check_interval_seconds: How often to check running analyses (default: 30s)
        """
        self.check_interval = check_interval_seconds
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Active sessions tracking (analysis_id -> session_ids)
        # This is synced from AnalysisOrchestratorService.active_sessions
        self.active_sessions: Dict[int, str] = {}
        
        # ClickHouse client for size queries
        self.clickhouse_url = f"http://{settings.clickhouse_host}:{settings.clickhouse_http_port}"
        
        # Settings cache with TTL (enterprise feature)
        self._settings_cache: Optional[dict] = None
        self._settings_cache_time: Optional[datetime] = None
        self._settings_cache_ttl: int = 60  # Refresh every 60 seconds
        
        # Warned analyses (to avoid duplicate warnings)
        self._warned_analyses: Set[int] = set()
        
        # Backend URL for settings and WebSocket broadcast
        self._backend_url = f"http://{settings.backend_service_host}:{settings.backend_service_port}"
        
        logger.info(f"AutoStopMonitor initialized (check interval: {check_interval_seconds}s)")
    
    def set_active_sessions(self, sessions: Dict[int, str]):
        """
        Update the active sessions reference.
        Called by gRPC server when sessions change.
        """
        self.active_sessions = sessions
        
        # Clear warnings for analyses that are no longer active
        active_analysis_ids = set(sessions.keys())
        self._warned_analyses = self._warned_analyses.intersection(active_analysis_ids)
    
    async def start(self):
        """Start the background monitoring task"""
        if self.running:
            logger.warning("AutoStopMonitor already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("AutoStopMonitor started")
    
    async def stop(self):
        """Stop the background monitoring task"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoStopMonitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._check_running_analyses()
            except Exception as e:
                logger.error(f"Error in auto-stop monitor: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)
    
    # ============================================
    # Settings Cache (Enterprise Feature)
    # ============================================
    
    async def _get_global_settings(self) -> dict:
        """
        Get global analysis limit settings with caching.
        Falls back to hardcoded defaults if settings unavailable.
        
        Returns:
            dict with keys: continuous_auto_stop_enabled, default_continuous_duration_minutes,
                           max_allowed_duration_minutes, warning_before_minutes
        """
        now = datetime.now(timezone.utc)
        
        # Return cached if fresh
        if (self._settings_cache and self._settings_cache_time and 
            (now - self._settings_cache_time).total_seconds() < self._settings_cache_ttl):
            return self._settings_cache
        
        # Try to fetch from backend API
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._backend_url}/api/v1/settings/analysis-limits/defaults"
                )
                if response.status_code == 200:
                    self._settings_cache = response.json()
                    self._settings_cache_time = now
                    logger.debug(f"Fetched global settings: {self._settings_cache}")
                    return self._settings_cache
        except Exception as e:
            logger.warning(f"Failed to fetch global settings: {e}")
        
        # FALLBACK: Use hardcoded defaults (fail-safe)
        default_settings = {
            "continuous_auto_stop_enabled": True,
            "default_continuous_duration_minutes": 10,
            "max_allowed_duration_minutes": 1440,
            "warning_before_minutes": 2
        }
        
        # Cache the defaults too
        self._settings_cache = default_settings
        self._settings_cache_time = now
        
        return default_settings
    
    # ============================================
    # Analysis Checking
    # ============================================
    
    async def _check_running_analyses(self):
        """Check all running analyses for limit violations"""
        # Get running analyses from database
        running_analyses = await self._get_running_analyses()
        
        if not running_analyses:
            return
        
        logger.debug(f"Checking {len(running_analyses)} running analyses for limits")
        
        for analysis in running_analyses:
            try:
                should_stop, reason = await self._should_stop_analysis(analysis)
                
                if should_stop:
                    logger.info(f"Auto-stopping analysis {analysis['id']}: {reason}")
                    await self._stop_analysis(analysis['id'], reason)
                    
            except Exception as e:
                logger.error(f"Error checking analysis {analysis['id']}: {e}")
    
    async def _get_running_analyses(self) -> List[Dict[str, Any]]:
        """Get all analyses with status 'running'"""
        try:
            # Use sync method wrapped in executor to avoid event loop issues
            loop = asyncio.get_running_loop()
            analyses = await loop.run_in_executor(
                None,
                db_manager.get_running_analyses_sync
            )
            
            # Enrich with full analysis data
            enriched = []
            for a in analyses:
                full_analysis = await db_manager.get_analysis(a['id'])
                if full_analysis:
                    enriched.append({
                        'id': full_analysis.id,
                        'name': full_analysis.name,
                        'cluster_id': full_analysis.cluster_id,
                        'time_config': full_analysis.time_config or {},
                        'output_config': full_analysis.output_config or {},
                        'created_at': full_analysis.created_at,
                        'updated_at': full_analysis.updated_at,
                        'started_at': full_analysis.started_at  # For auto-stop timing
                    })
            
            return enriched
            
        except Exception as e:
            logger.error(f"Failed to get running analyses: {e}")
            return []
    
    async def _should_stop_analysis(self, analysis: Dict[str, Any]) -> tuple[bool, str]:
        """
        Check if analysis should be auto-stopped.
        
        IMPORTANT: This method has 3 separate checks in order:
        1. [EXISTING] Explicit duration_seconds/duration_minutes (Fixed Duration mode)
        2. [EXISTING] max_data_size_mb with stop_on_limit policy
        3. [NEW] Continuous mode with global default duration (enterprise feature)
        
        Returns:
            (should_stop, reason)
        """
        time_config = analysis.get('time_config', {})
        mode = time_config.get('mode', 'continuous')
        analysis_id = analysis['id']
        analysis_name = analysis.get('name', f'Analysis {analysis_id}')
        
        # ============================================
        # CHECK 1: EXISTING - Explicit duration config
        # This handles Fixed Duration mode - DO NOT MODIFY
        # ============================================
        duration_seconds = time_config.get('duration_seconds', 0) or 0
        duration_minutes = time_config.get('duration_minutes', 0) or 0
        total_duration_seconds = duration_seconds + (duration_minutes * 60)
        
        if total_duration_seconds > 0:
            # EXISTING LOGIC - UNCHANGED
            started_at = analysis.get('started_at') or analysis.get('updated_at')
            
            logger.debug(f"Analysis {analysis_id}: duration={total_duration_seconds}s, started_at={started_at}")
            
            if started_at:
                now = datetime.now(timezone.utc)
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = now - started_at
                limit = timedelta(seconds=total_duration_seconds)
                elapsed_secs = elapsed.total_seconds()
                
                logger.info(f"Analysis {analysis_id}: elapsed={elapsed_secs:.0f}s / limit={total_duration_seconds}s (Fixed Duration)")
                
                if elapsed > limit:
                    elapsed_mins = elapsed_secs / 60
                    limit_mins = total_duration_seconds / 60
                    return True, f"Time limit exceeded ({elapsed_mins:.1f}m > {limit_mins:.1f}m)"
                
                # NEW: Check warning threshold for explicit duration
                global_settings = await self._get_global_settings()
                await self._check_and_emit_warning(
                    analysis_id, 
                    analysis_name,
                    elapsed, 
                    limit, 
                    global_settings
                )
            else:
                logger.warning(f"Analysis {analysis_id} has no start time!")
        
        # ============================================
        # CHECK 2: EXISTING - Size-based limit
        # This handles stop_on_limit policy - DO NOT MODIFY
        # ============================================
        data_retention_policy = time_config.get('data_retention_policy', 'unlimited')
        max_data_size_mb = time_config.get('max_data_size_mb', 0) or 0
        
        if data_retention_policy == 'stop_on_limit' and max_data_size_mb > 0:
            current_size_mb = await self._get_analysis_data_size(analysis_id)
            
            if current_size_mb >= max_data_size_mb:
                return True, f"Data size limit exceeded ({current_size_mb:.1f}MB >= {max_data_size_mb}MB)"
        
        # ============================================
        # CHECK 3: NEW - Continuous mode default duration
        # Only applies when:
        # - mode is 'continuous'
        # - no explicit duration is set
        # - feature is enabled in global settings
        # ============================================
        if mode == 'continuous' and total_duration_seconds == 0:
            global_settings = await self._get_global_settings()
            
            # Check if feature is enabled
            if not global_settings.get('continuous_auto_stop_enabled', True):
                return False, ""  # Feature disabled, don't auto-stop
            
            default_duration_minutes = global_settings.get('default_continuous_duration_minutes', 10)
            default_duration_seconds = default_duration_minutes * 60
            
            started_at = analysis.get('started_at') or analysis.get('updated_at')
            if started_at:
                now = datetime.now(timezone.utc)
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = now - started_at
                limit = timedelta(seconds=default_duration_seconds)
                elapsed_secs = elapsed.total_seconds()
                
                logger.info(f"Analysis {analysis_id}: elapsed={elapsed_secs:.0f}s / limit={default_duration_seconds}s (Continuous default)")
                
                if elapsed > limit:
                    elapsed_mins = elapsed_secs / 60
                    return True, f"Continuous mode default limit ({elapsed_mins:.1f}m > {default_duration_minutes}m)"
                
                # Check warning threshold
                await self._check_and_emit_warning(
                    analysis_id, 
                    analysis_name,
                    elapsed, 
                    limit, 
                    global_settings
                )
        
        return False, ""
    
    # ============================================
    # Warning System (Enterprise Feature)
    # ============================================
    
    async def _check_and_emit_warning(
        self, 
        analysis_id: int,
        analysis_name: str,
        elapsed: timedelta, 
        limit: timedelta,
        global_settings: dict
    ):
        """
        Check if warning should be emitted and send via WebSocket.
        
        NEW METHOD - does not affect existing stop logic.
        Warnings are sent independently and failures don't block auto-stop.
        """
        # Don't warn twice for the same analysis
        if analysis_id in self._warned_analyses:
            return
        
        # Get warning threshold from settings
        warning_minutes = global_settings.get('warning_before_minutes', 2)
        warning_threshold = limit - timedelta(minutes=warning_minutes)
        
        if elapsed >= warning_threshold:
            remaining = limit - elapsed
            remaining_minutes = max(0, remaining.total_seconds() / 60)
            
            # Mark as warned (prevent duplicate warnings)
            self._warned_analyses.add(analysis_id)
            
            logger.info(
                f"Emitting auto-stop warning for analysis {analysis_id}: "
                f"{remaining_minutes:.1f}m remaining"
            )
            
            # Emit warning via HTTP callback to backend WebSocket
            await self._emit_warning(analysis_id, analysis_name, remaining_minutes)
    
    async def _emit_warning(self, analysis_id: int, analysis_name: str, remaining_minutes: float):
        """
        Send warning to backend WebSocket broadcast endpoint.
        
        NEW METHOD - independent, failure here doesn't affect auto-stop.
        """
        try:
            payload = {
                "type": "analysis_auto_stop_warning",
                "analysis_id": analysis_id,
                "analysis_name": analysis_name,
                "remaining_minutes": round(remaining_minutes, 1),
                "message": f"Analysis will auto-stop in {remaining_minutes:.0f} minute(s)"
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._backend_url}/api/v1/ws/broadcast",
                    json=payload
                )
                
                if response.status_code == 200:
                    logger.info(f"Warning emitted for analysis {analysis_id}: {remaining_minutes:.1f}m remaining")
                else:
                    logger.warning(
                        f"Warning broadcast returned non-200: {response.status_code}"
                    )
            
        except Exception as e:
            # WARNING FAILURE IS NOT CRITICAL - analysis will still stop on time
            logger.warning(f"Failed to emit warning for analysis {analysis_id}: {e}")
    
    # ============================================
    # Data Size Queries
    # ============================================
    
    async def _get_analysis_data_size(self, analysis_id: int) -> float:
        """
        Query ClickHouse to get the current data size for an analysis.
        
        Uses count(*) as a proxy for data size since actual byte size calculation
        is complex in ClickHouse. Estimates ~1KB per event.
        
        Returns size in MB.
        """
        try:
            # Query ClickHouse for event count
            # Events are stored with analysis_id in format '{analysis_id}-{cluster_id}'
            # Use count as proxy: ~1KB per event average
            query = f"""
                SELECT count(*) as event_count
                FROM flowfish.events
                WHERE analysis_id LIKE '{analysis_id}-%'
            """
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.clickhouse_url}/",
                    params={
                        "query": query,
                        "default_format": "JSON",
                        "user": settings.clickhouse_user,
                        "password": settings.clickhouse_password
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('data') and len(result['data']) > 0:
                        event_count = result['data'][0].get('event_count', 0)
                        # Estimate: 1KB per event average
                        size_mb = float(event_count) / 1024 if event_count else 0.0
                        return size_mb
            
            return 0.0
            
        except Exception as e:
            logger.warning(f"Failed to get analysis data size from ClickHouse: {e}")
            return 0.0
    
    # ============================================
    # Stop Analysis
    # ============================================
    
    async def _stop_analysis(self, analysis_id: int, reason: str):
        """
        Stop an analysis and update its status.
        
        Args:
            analysis_id: Analysis to stop
            reason: Reason for stopping (logged and stored)
        """
        try:
            # Get session IDs for this analysis
            session_ids_str = self.active_sessions.get(analysis_id)
            
            if session_ids_str:
                session_ids = session_ids_str.split(",")
                
                # Stop all sessions in parallel via asyncio.gather
                async def stop_session(sid):
                    try:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, ingestion_client.stop_collection, sid)
                        logger.info(f"Auto-stopped session: {sid}")
                        return True
                    except Exception as e:
                        logger.error(f"Failed to stop session {sid}: {e}")
                        return False
                
                # Run all stops in parallel
                await asyncio.gather(*[stop_session(sid) for sid in session_ids])
                
                # Remove from active sessions
                if analysis_id in self.active_sessions:
                    del self.active_sessions[analysis_id]
            
            # Clear from warned set
            self._warned_analyses.discard(analysis_id)
            
            # Get current analysis to preserve existing output_config
            analysis = await db_manager.get_analysis(analysis_id)
            existing_output_config = analysis.output_config or {} if analysis else {}
            
            # Use timezone-naive UTC datetime (asyncpg doesn't handle timezone-aware well)
            stopped_at = datetime.utcnow()
            
            # Merge auto-stop info with existing output_config
            updated_output_config = {
                **existing_output_config,
                "auto_stopped": True,
                "auto_stop_reason": reason,
                "auto_stopped_at": stopped_at.isoformat()
            }
            
            # Update analysis status to 'completed' (auto-stopped = completed successfully)
            await db_manager.update_analysis(
                analysis_id,
                {
                    "status": AnalysisStatus.COMPLETED.value,
                    "output_config": updated_output_config
                }
            )
            
            # Also update the running analysis_run record
            running_run = await db_manager.get_running_run_for_analysis(analysis_id)
            if running_run:
                # Calculate duration using start_time (both are timezone-naive UTC)
                duration_seconds = 0
                if running_run.start_time:
                    # Ensure both are timezone-naive for subtraction
                    start_time_naive = running_run.start_time.replace(tzinfo=None) if running_run.start_time.tzinfo else running_run.start_time
                    duration_seconds = int((stopped_at - start_time_naive).total_seconds())
                
                await db_manager.update_analysis_run(
                    running_run.id,
                    {
                        "status": "completed",
                        "end_time": stopped_at,
                        "duration_seconds": duration_seconds
                    }
                )
                logger.info(f"Updated run {running_run.id} status to completed")
            
            logger.info(f"Analysis {analysis_id} auto-stopped: {reason}")
            
        except Exception as e:
            logger.error(f"Failed to auto-stop analysis {analysis_id}: {e}")


# Global monitor instance - uses config for check interval
auto_stop_monitor = AutoStopMonitor(check_interval_seconds=settings.auto_stop_check_interval)
