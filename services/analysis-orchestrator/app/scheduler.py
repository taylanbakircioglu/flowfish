"""Analysis Scheduler using APScheduler"""

import logging
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.config import settings
from app.database import db_manager, AnalysisStatus
from app.analysis_executor import AnalysisExecutor

logger = logging.getLogger(__name__)


class AnalysisScheduler:
    """Manages scheduled analysis execution"""
    
    def __init__(self):
        jobstores = {
            'default': MemoryJobStore()
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=settings.scheduler_timezone
        )
        
        self.executor = AnalysisExecutor()
        
        logger.info("AnalysisScheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        logger.info("✅ Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown")
    
    async def schedule_analysis(self, analysis_id: int, cron_expression: str):
        """
        Schedule an analysis to run periodically
        
        Args:
            analysis_id: Analysis ID
            cron_expression: Cron expression (e.g., "0 0 * * *" for daily at midnight)
        """
        try:
            # Create cron trigger
            trigger = CronTrigger.from_crontab(cron_expression, timezone=settings.scheduler_timezone)
            
            # Add job to scheduler
            job_id = f"analysis_{analysis_id}"
            
            # Remove existing job if any
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Add new job
            self.scheduler.add_job(
                func=self._execute_scheduled_analysis,
                trigger=trigger,
                args=[analysis_id],
                id=job_id,
                name=f"Analysis {analysis_id}",
                replace_existing=True
            )
            
            # Update next run time in database
            next_run = self.scheduler.get_job(job_id).next_run_time
            await db_manager.update_analysis(
                analysis_id,
                {
                    "is_scheduled": True,
                    "schedule_expression": cron_expression,
                    "next_run_at": next_run
                }
            )
            
            logger.info(f"✅ Scheduled analysis {analysis_id} with cron: {cron_expression}")
            logger.info(f"   Next run: {next_run}")
            
        except Exception as e:
            logger.error(f"Failed to schedule analysis {analysis_id}: {e}")
            raise
    
    async def unschedule_analysis(self, analysis_id: int):
        """Remove analysis from schedule"""
        try:
            job_id = f"analysis_{analysis_id}"
            
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Unscheduled analysis {analysis_id}")
            
            # Update database
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
    
    async def _execute_scheduled_analysis(self, analysis_id: int):
        """
        Execute a scheduled analysis
        
        Args:
            analysis_id: Analysis ID
        """
        logger.info(f"🚀 Executing scheduled analysis {analysis_id}")
        
        try:
            # Get analysis
            analysis = await db_manager.get_analysis(analysis_id)
            if not analysis:
                logger.error(f"Analysis {analysis_id} not found")
                return
            
            # Check if already running
            if analysis.status == AnalysisStatus.RUNNING:
                logger.warning(f"Analysis {analysis_id} is already running, skipping")
                return
            
            # Execute analysis
            await self.executor.execute_analysis(analysis_id)
            
            # Update last run time and run count
            await db_manager.update_analysis(
                analysis_id,
                {
                    "last_run_at": datetime.utcnow(),
                    "run_count": analysis.run_count + 1
                }
            )
            
            # Update next run time
            job_id = f"analysis_{analysis_id}"
            job = self.scheduler.get_job(job_id)
            if job:
                await db_manager.update_analysis(
                    analysis_id,
                    {"next_run_at": job.next_run_time}
                )
        
        except Exception as e:
            logger.error(f"Scheduled analysis execution failed: {e}")


# Global scheduler instance
scheduler = AnalysisScheduler()

