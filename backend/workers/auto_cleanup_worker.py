"""
Auto-Cleanup Worker - Periodic data retention enforcement

Reads DataRetentionSettings from system_settings and deletes expired data
from ClickHouse event tables and PostgreSQL activity logs/runs.

Configuration (via environment variables):
- AUTO_CLEANUP_ENABLED: Enable/disable worker (default: true)
- AUTO_CLEANUP_CHECK_INTERVAL: Check interval in seconds (default: 3600 = 1 hour)
"""

import asyncio
import os
import json
from typing import Optional, Dict, Any
import structlog
import httpx

from database.postgresql import database
from config import settings as app_settings

logger = structlog.get_logger(__name__)

CLICKHOUSE_EVENT_TABLES = [
    'network_flows', 'dns_queries', 'tcp_lifecycle', 'process_events',
    'file_operations', 'capability_checks', 'oom_kills', 'bind_events',
    'sni_events', 'mount_events', 'workload_metadata'
]


class AutoCleanupWorker:
    """
    Background worker that enforces data retention policies by
    periodically deleting expired rows from ClickHouse and PostgreSQL.
    """
    
    def __init__(self):
        self.CHECK_INTERVAL = int(os.getenv("AUTO_CLEANUP_CHECK_INTERVAL", "3600"))
        self.ENABLED = os.getenv("AUTO_CLEANUP_ENABLED", "true").lower() == "true"
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        if not self.ENABLED:
            logger.info("Auto-cleanup worker is disabled")
            return
        
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Auto-cleanup worker started", check_interval=self.CHECK_INTERVAL)
    
    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Auto-cleanup worker stopped")
    
    async def _run_loop(self) -> None:
        await asyncio.sleep(60)
        
        while self._running:
            try:
                await self._perform_cleanup()
            except Exception as e:
                logger.error("Auto-cleanup cycle failed", error=str(e))
            
            await asyncio.sleep(self.CHECK_INTERVAL)
    
    async def _get_retention_settings(self) -> Dict[str, Any]:
        """Load retention settings from system_settings table."""
        try:
            query = "SELECT value FROM system_settings WHERE key = 'data_retention'"
            row = await database.fetch_one(query, {})
            if row and row['value']:
                value = row['value']
                if isinstance(value, str):
                    value = json.loads(value)
                return value
        except Exception as e:
            logger.debug("Could not load retention settings, using defaults", error=str(e))
        
        return {
            "events_retention_days": 30,
            "network_flows_retention_days": 30,
            "dns_queries_retention_days": 30,
            "process_events_retention_days": 30,
            "analysis_retention_days": 90,
            "auto_cleanup_enabled": True,
            "cleanup_schedule": "daily"
        }
    
    async def _perform_cleanup(self) -> None:
        """Run the full cleanup cycle."""
        settings = await self._get_retention_settings()
        
        if not settings.get("auto_cleanup_enabled", True):
            logger.debug("Auto-cleanup disabled in settings, skipping")
            return
        
        default_days = settings.get("events_retention_days", 30)
        
        logger.info("Starting auto-cleanup cycle", retention_days=default_days)
        
        deleted_total = 0
        deleted_total += await self._cleanup_clickhouse(settings, default_days)
        deleted_total += await self._cleanup_postgresql(settings)
        
        logger.info("Auto-cleanup cycle complete", total_deleted=deleted_total)
    
    async def _cleanup_clickhouse(self, settings: dict, default_days: int) -> int:
        """Delete expired rows from all ClickHouse event tables via HTTP API."""
        clickhouse_url = app_settings.CLICKHOUSE_URL
        ch_user = app_settings.CLICKHOUSE_USER
        ch_password = app_settings.CLICKHOUSE_PASSWORD
        ch_database = app_settings.CLICKHOUSE_DATABASE

        per_table_days = {
            'network_flows': settings.get('network_flows_retention_days', default_days),
            'dns_queries': settings.get('dns_queries_retention_days', default_days),
            'process_events': settings.get('process_events_retention_days', default_days),
        }

        total = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for table in CLICKHOUSE_EVENT_TABLES:
                    days = per_table_days.get(table, default_days)
                    query = (
                        f"ALTER TABLE {ch_database}.{table} DELETE "
                        f"WHERE timestamp < now() - INTERVAL {days} DAY"
                    )
                    try:
                        resp = await client.post(
                            f"{clickhouse_url}/",
                            params={
                                "query": query,
                                "user": ch_user,
                                "password": ch_password,
                            }
                        )
                        if resp.status_code == 200:
                            total += 1
                            logger.debug("Cleaned expired data", table=table, retention_days=days)
                        else:
                            logger.warning("ClickHouse DELETE returned non-200",
                                         table=table, status=resp.status_code,
                                         body=resp.text[:200])
                    except Exception as e:
                        logger.warning("Failed to clean table", table=table, error=str(e))
        except Exception as e:
            logger.warning("ClickHouse cleanup failed", error=str(e))

        return total
    
    async def _cleanup_postgresql(self, settings: dict) -> int:
        """Clean old activity logs and completed analysis runs beyond retention."""
        analysis_days = settings.get("analysis_retention_days", 90)
        deleted = 0
        
        try:
            result = await database.execute(
                "DELETE FROM activity_logs WHERE created_at < NOW() - :days * INTERVAL '1 day'",
                {"days": analysis_days}
            )
            deleted += 1
        except Exception as e:
            logger.debug("Activity log cleanup skipped", error=str(e))
        
        return deleted


auto_cleanup_worker = AutoCleanupWorker()
