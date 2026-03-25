"""Analysis Scheduler using APScheduler"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.config import settings
from app.database import db_manager, AnalysisStatus

logger = logging.getLogger(__name__)

# Set by grpc_server.py after service initialization
_grpc_service_instance = None


class AnalysisScheduler:
    """Manages scheduled analysis execution using APScheduler with CronTrigger."""
    
    def __init__(self):
        jobstores = {
            'default': MemoryJobStore()
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=settings.scheduler_timezone
        )
        
        logger.info("AnalysisScheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        logger.info("Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown")
    
    def schedule_analysis_sync(
        self,
        analysis_id: int,
        cron_expression: str,
        duration_seconds: int = 0,
        max_runs: int = 0
    ) -> Optional[str]:
        """
        Schedule an analysis for recurring execution (sync, for gRPC handlers).
        APScheduler add_job is thread-safe; DB update uses sync session.
        
        Returns:
            ISO-format string of next_run_at, or None on failure
        """
        try:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=settings.scheduler_timezone)
            
            job_id = f"analysis_{analysis_id}"
            
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            self.scheduler.add_job(
                func=self._execute_scheduled_analysis,
                trigger=trigger,
                args=[analysis_id, duration_seconds, max_runs],
                id=job_id,
                name=f"Analysis {analysis_id}",
                replace_existing=True
            )
            
            next_run = self.scheduler.get_job(job_id).next_run_time
            
            db_manager.update_analysis_sync(
                analysis_id,
                {
                    "is_scheduled": True,
                    "schedule_expression": cron_expression,
                    "schedule_duration_seconds": duration_seconds,
                    "max_scheduled_runs": max_runs if max_runs > 0 else None,
                    "next_run_at": next_run
                }
            )
            
            next_run_str = next_run.isoformat() if next_run else None
            logger.info(f"Scheduled analysis {analysis_id} with cron: {cron_expression}, next: {next_run_str}")
            return next_run_str
            
        except Exception as e:
            logger.error(f"Failed to schedule analysis {analysis_id}: {e}")
            raise
    
    def unschedule_analysis_sync(self, analysis_id: int):
        """Remove analysis from schedule (sync, for gRPC handlers)."""
        try:
            job_id = f"analysis_{analysis_id}"
            
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Unscheduled analysis {analysis_id}")
            
            db_manager.update_analysis_sync(
                analysis_id,
                {
                    "is_scheduled": False,
                    "next_run_at": None
                }
            )
        
        except Exception as e:
            logger.error(f"Failed to unschedule analysis {analysis_id}: {e}")
            raise
    
    async def unschedule_analysis(self, analysis_id: int):
        """Remove analysis from schedule (async, for scheduler internal use)."""
        try:
            job_id = f"analysis_{analysis_id}"
            
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Unscheduled analysis {analysis_id}")
            
            await db_manager.update_analysis(
                analysis_id,
                {
                    "is_scheduled": False,
                    "next_run_at": None
                }
            )
        
        except Exception as e:
            logger.error(f"Failed to unschedule analysis {analysis_id}: {e}")
            raise
    
    async def _execute_scheduled_analysis(
        self,
        analysis_id: int,
        duration_seconds: int = 0,
        max_runs: int = 0
    ):
        """
        Execute a scheduled analysis run using the same StartAnalysis code path
        as manual starts, ensuring consistent behavior and auto-stop support.
        """
        logger.info(f"Executing scheduled analysis {analysis_id}")
        
        try:
            analysis = await db_manager.get_analysis(analysis_id)
            if not analysis:
                logger.error(f"Scheduled analysis {analysis_id} not found, unscheduling")
                await self.unschedule_analysis(analysis_id)
                return
            
            if analysis.status == AnalysisStatus.RUNNING.value or analysis.status == AnalysisStatus.RUNNING:
                logger.warning(f"Analysis {analysis_id} is already running, skipping scheduled run")
                return
            
            # Check max_runs limit
            run_count = getattr(analysis, 'schedule_run_count', 0) or 0
            effective_max = max_runs or (getattr(analysis, 'max_scheduled_runs', None) or 0)
            if effective_max > 0 and run_count >= effective_max:
                logger.info(f"Analysis {analysis_id} reached max runs ({run_count}/{effective_max}), unscheduling")
                await self.unschedule_analysis(analysis_id)
                return
            
            # Inject schedule_duration_seconds into time_config so auto-stop monitor
            # will stop this run after the specified duration
            if duration_seconds > 0:
                time_config = analysis.time_config or {}
                time_config['duration_seconds'] = duration_seconds
                await db_manager.update_analysis(analysis_id, {"time_config": time_config})
            
            # Create analysis_run record (mirrors what the backend start endpoint does)
            # Without this, scheduled executions would not appear in run history
            try:
                runs = await db_manager.list_analysis_runs(analysis_id, limit=1)
                next_run_number = (runs[0].run_number + 1) if runs else 1
                await db_manager.create_analysis_run({
                    "analysis_id": analysis_id,
                    "run_number": next_run_number,
                    "status": "running",
                    "start_time": datetime.utcnow(),
                    "events_collected": 0,
                    "workloads_discovered": 0,
                    "communications_discovered": 0,
                    "anomalies_detected": 0,
                    "changes_detected": 0,
                })
            except Exception as run_err:
                logger.warning(f"Failed to create analysis_run for {analysis_id}: {run_err}")
            
            # Use the production StartAnalysis code path via the gRPC service instance
            global _grpc_service_instance
            if _grpc_service_instance is None:
                logger.error("gRPC service instance not set, cannot execute scheduled analysis")
                return
            
            from proto import analysis_orchestrator_pb2
            request = analysis_orchestrator_pb2.StartAnalysisRequest(analysis_id=analysis_id)
            
            class _DummyContext:
                """Minimal gRPC context stub for internal calls."""
                def set_code(self, code): pass
                def set_details(self, details): pass
            
            # StartAnalysis is synchronous (blocking DB + gRPC I/O);
            # run in executor to avoid blocking the scheduler's event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, _grpc_service_instance.StartAnalysis, request, _DummyContext()
            )
            
            if not response.success:
                logger.error(f"Scheduled analysis {analysis_id} StartAnalysis failed: {response.message}")
                # Clean up the analysis_run we just created so it doesn't stay "running" forever
                try:
                    runs = await db_manager.list_analysis_runs(analysis_id, limit=1)
                    if runs and runs[0].status == "running":
                        await db_manager.update_analysis_run(runs[0].id, {
                            "status": "failed",
                            "error_message": f"Scheduled start failed: {response.message}",
                            "end_time": datetime.utcnow()
                        })
                except Exception:
                    pass
                return
            
            # Update run metadata
            new_run_count = run_count + 1
            job_id = f"analysis_{analysis_id}"
            job = self.scheduler.get_job(job_id)
            next_run = job.next_run_time if job else None
            
            await db_manager.update_analysis(
                analysis_id,
                {
                    "last_run_at": datetime.utcnow(),
                    "schedule_run_count": new_run_count,
                    "next_run_at": next_run
                }
            )
            
            logger.info(f"Scheduled analysis {analysis_id} started (run {new_run_count}), next: {next_run}")
        
        except Exception as e:
            logger.error(f"Scheduled analysis execution failed for {analysis_id}: {e}", exc_info=True)
            # Best-effort: mark any orphaned "running" run as failed
            try:
                runs = await db_manager.list_analysis_runs(analysis_id, limit=1)
                if runs and runs[0].status == "running":
                    await db_manager.update_analysis_run(runs[0].id, {
                        "status": "failed",
                        "error_message": f"Scheduled execution error: {str(e)}",
                        "end_time": datetime.utcnow()
                    })
            except Exception:
                pass
    
    def restore_jobs_from_db(self):
        """
        Restore scheduled jobs from database after pod restart.
        Called synchronously during server startup.
        """
        try:
            scheduled = db_manager.get_scheduled_analyses_sync()
            restored = 0
            
            for sa in scheduled:
                analysis_id = sa['id']
                cron_expr = sa.get('schedule_expression')
                duration = sa.get('schedule_duration_seconds', 0) or 0
                max_runs = sa.get('max_scheduled_runs', 0) or 0
                
                if not cron_expr:
                    logger.warning(f"Scheduled analysis {analysis_id} has no cron expression, skipping")
                    continue
                
                try:
                    trigger = CronTrigger.from_crontab(cron_expr, timezone=settings.scheduler_timezone)
                    job_id = f"analysis_{analysis_id}"
                    
                    self.scheduler.add_job(
                        func=self._execute_scheduled_analysis,
                        trigger=trigger,
                        args=[analysis_id, duration, max_runs],
                        id=job_id,
                        name=f"Analysis {analysis_id}",
                        replace_existing=True
                    )
                    restored += 1
                    logger.info(f"Restored scheduled job for analysis {analysis_id}: {cron_expr}")
                except Exception as e:
                    logger.error(f"Failed to restore job for analysis {analysis_id}: {e}")
            
            logger.info(f"Restored {restored}/{len(scheduled)} scheduled jobs from database")
            
        except Exception as e:
            logger.error(f"Failed to restore scheduled jobs: {e}")


# Global scheduler instance
scheduler = AnalysisScheduler()
