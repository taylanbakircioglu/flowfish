"""
Scheduled Simulation Worker - Background task for automatic simulation execution

This worker runs as a background task and periodically checks for scheduled
simulations that are due, executing them automatically.

Features:
- Periodic check for due simulations (every 30 seconds)
- Automatic execution when scheduled_time <= NOW()
- Support for recurring schedules (once, daily, weekly)
- Notification before execution (notify_before_minutes)
- Status updates after execution
- WebSocket notifications for simulation events

Configuration (via environment variables):
- SCHEDULED_SIMULATION_ENABLED: Enable/disable worker (default: true)
- SCHEDULED_SIMULATION_CHECK_INTERVAL: Check interval in seconds (default: 30)
"""

import asyncio
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import structlog

from database.postgresql import database

logger = structlog.get_logger(__name__)


class ScheduledSimulationWorker:
    """
    Background worker that automatically executes scheduled simulations.
    
    Features:
    - Checks for due simulations every 30 seconds
    - Executes simulations when scheduled_time <= NOW()
    - Updates status after execution
    - Handles recurring schedules (daily, weekly)
    - Sends notifications before execution
    """
    
    def __init__(self):
        # Configuration from environment
        self.CHECK_INTERVAL = int(os.getenv("SCHEDULED_SIMULATION_CHECK_INTERVAL", "30"))
        self.ENABLED = os.getenv("SCHEDULED_SIMULATION_ENABLED", "true").lower() == "true"
        
        # Internal state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._notification_task: Optional[asyncio.Task] = None
        self._notified_simulations: set = set()  # Track already notified simulations
    
    async def start(self) -> None:
        """Start the background scheduler task"""
        if not self.ENABLED:
            logger.info("Scheduled simulation worker is disabled")
            return
        
        if self._running:
            logger.warning("Scheduled simulation worker already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler_loop())
        self._notification_task = asyncio.create_task(self._run_notification_loop())
        
        logger.info(
            "Scheduled simulation worker started",
            check_interval=self.CHECK_INTERVAL
        )
    
    async def stop(self) -> None:
        """Stop the background scheduler task"""
        self._running = False
        
        for task in [self._task, self._notification_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._task = None
        self._notification_task = None
        self._notified_simulations.clear()
        
        logger.info("Scheduled simulation worker stopped")
    
    async def _run_scheduler_loop(self) -> None:
        """Main scheduler loop - checks for due simulations"""
        # Initial delay to let the system stabilize
        await asyncio.sleep(15)
        
        while self._running:
            try:
                await self._check_and_execute_due_simulations()
            except Exception as e:
                logger.error("Scheduled simulation check failed", error=str(e))
            
            await asyncio.sleep(self.CHECK_INTERVAL)
    
    async def _run_notification_loop(self) -> None:
        """Notification loop - sends notifications before scheduled time"""
        # Initial delay
        await asyncio.sleep(20)
        
        while self._running:
            try:
                await self._send_upcoming_notifications()
            except Exception as e:
                logger.error("Notification check failed", error=str(e))
            
            # Check every minute for upcoming notifications
            await asyncio.sleep(60)
    
    async def _check_and_execute_due_simulations(self) -> None:
        """Check for simulations that are due and execute them"""
        try:
            # Find simulations where scheduled_time <= NOW() and status = 'scheduled'
            query = """
                SELECT * FROM scheduled_simulations 
                WHERE status = 'scheduled' 
                AND scheduled_time <= NOW()
                ORDER BY scheduled_time ASC
                LIMIT 10
            """
            
            due_simulations = await database.fetch_all(query, {})
            
            if not due_simulations:
                return
            
            logger.info(f"Found {len(due_simulations)} due simulations to execute")
            
            for simulation in due_simulations:
                await self._execute_simulation(simulation)
                
        except Exception as e:
            logger.error("Failed to check due simulations", error=str(e))
    
    async def _execute_simulation(self, simulation: dict) -> None:
        """Execute a single scheduled simulation"""
        simulation_id = simulation['id']
        
        try:
            logger.info(
                "Executing scheduled simulation",
                simulation_id=simulation_id,
                name=simulation['name'],
                target=f"{simulation['target_namespace']}/{simulation['target_name']}"
            )
            
            # Import here to avoid circular imports
            from schemas.simulation import ImpactSimulationRequest, ChangeType
            from routers.simulation import run_impact_simulation
            from services.network_policy_service import NetworkPolicyService
            
            # Create the simulation request
            target_id = simulation['target_name']
            
            request = ImpactSimulationRequest(
                cluster_id=simulation['cluster_id'],
                analysis_id=simulation['analysis_id'],
                target_id=target_id,
                target_name=simulation['target_name'],
                target_namespace=simulation['target_namespace'],
                target_kind=simulation['target_kind'],
                change_type=ChangeType(simulation['change_type'])
            )
            
            # Create a mock user for the automated execution
            system_user = {
                'user_id': 0,
                'username': 'scheduler',
                'roles': ['admin']
            }
            
            # Get service instance
            service = NetworkPolicyService()
            
            # Execute the simulation
            result = await run_impact_simulation(request, system_user, service)
            
            # Update simulation status based on schedule type
            if simulation['schedule_type'] == 'once':
                new_status = 'completed'
                next_run = None
            elif simulation['schedule_type'] == 'daily':
                new_status = 'scheduled'
                next_run = datetime.utcnow() + timedelta(days=1)
            elif simulation['schedule_type'] == 'weekly':
                new_status = 'scheduled'
                next_run = datetime.utcnow() + timedelta(weeks=1)
            else:
                new_status = 'completed'
                next_run = None
            
            # Update the simulation record
            if next_run:
                update_query = """
                    UPDATE scheduled_simulations 
                    SET last_run_at = NOW(), 
                        last_run_result = :result,
                        status = :status,
                        scheduled_time = :next_run
                    WHERE id = :id
                """
                await database.execute(update_query, {
                    'id': simulation_id,
                    'result': 'success' if result.success else 'failed',
                    'status': new_status,
                    'next_run': next_run
                })
            else:
                update_query = """
                    UPDATE scheduled_simulations 
                    SET last_run_at = NOW(), 
                        last_run_result = :result,
                        status = :status
                    WHERE id = :id
                """
                await database.execute(update_query, {
                    'id': simulation_id,
                    'result': 'success' if result.success else 'failed',
                    'status': new_status
                })
            
            logger.info(
                "Scheduled simulation executed successfully",
                simulation_id=simulation_id,
                name=simulation['name'],
                success=result.success,
                affected_count=result.summary.total_affected if result.summary else 0,
                new_status=new_status
            )
            
            # Send WebSocket notification
            await self._send_execution_notification(simulation, result, 'success')
            
        except Exception as e:
            logger.error(
                "Failed to execute scheduled simulation",
                simulation_id=simulation_id,
                error=str(e)
            )
            
            # Update status to failed
            update_query = """
                UPDATE scheduled_simulations 
                SET last_run_at = NOW(), 
                    last_run_result = :result,
                    status = CASE 
                        WHEN schedule_type = 'once' THEN 'failed'
                        ELSE status 
                    END
                WHERE id = :id
            """
            await database.execute(update_query, {
                'id': simulation_id,
                'result': f'error: {str(e)}'
            })
            
            # Send failure notification
            await self._send_execution_notification(simulation, None, 'failed', str(e))
    
    async def _send_upcoming_notifications(self) -> None:
        """Send notifications for simulations that will run soon"""
        try:
            # Find simulations that will run within their notify_before_minutes window
            query = """
                SELECT * FROM scheduled_simulations 
                WHERE status = 'scheduled' 
                AND scheduled_time > NOW()
                AND scheduled_time <= NOW() + (notify_before_minutes || ' minutes')::INTERVAL
            """
            
            upcoming = await database.fetch_all(query, {})
            
            for simulation in upcoming:
                sim_id = simulation['id']
                
                # Skip if already notified
                if sim_id in self._notified_simulations:
                    continue
                
                minutes_until = int((simulation['scheduled_time'] - datetime.utcnow()).total_seconds() / 60)
                
                logger.info(
                    "Sending upcoming simulation notification",
                    simulation_id=sim_id,
                    name=simulation['name'],
                    minutes_until=minutes_until
                )
                
                await self._send_upcoming_notification(simulation, minutes_until)
                self._notified_simulations.add(sim_id)
                
        except Exception as e:
            logger.error("Failed to check upcoming notifications", error=str(e))
    
    async def _send_execution_notification(
        self, 
        simulation: dict, 
        result: Any, 
        status: str, 
        error: str = None
    ) -> None:
        """Send WebSocket notification about simulation execution"""
        try:
            from routers.websocket import broadcast_event
            
            event_data = {
                "type": "SCHEDULED_SIMULATION_EXECUTED",
                "simulation_id": simulation['id'],
                "name": simulation['name'],
                "target": f"{simulation['target_namespace']}/{simulation['target_name']}",
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if result and hasattr(result, 'summary') and result.summary:
                event_data["affected_count"] = result.summary.total_affected
                event_data["high_impact"] = result.summary.high_impact
            
            if error:
                event_data["error"] = error
            
            await broadcast_event("simulation", event_data)
            
        except Exception as e:
            logger.warning("Failed to send execution notification", error=str(e))
    
    async def _send_upcoming_notification(self, simulation: dict, minutes_until: int) -> None:
        """Send WebSocket notification about upcoming simulation"""
        try:
            from routers.websocket import broadcast_event
            
            event_data = {
                "type": "SCHEDULED_SIMULATION_UPCOMING",
                "simulation_id": simulation['id'],
                "name": simulation['name'],
                "target": f"{simulation['target_namespace']}/{simulation['target_name']}",
                "change_type": simulation['change_type'],
                "minutes_until": minutes_until,
                "scheduled_time": simulation['scheduled_time'].isoformat() if simulation['scheduled_time'] else None,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await broadcast_event("simulation", event_data)
            
        except Exception as e:
            logger.warning("Failed to send upcoming notification", error=str(e))
    
    async def get_status(self) -> Dict[str, Any]:
        """Get worker status for health checks"""
        try:
            # Count pending simulations
            query = "SELECT COUNT(*) as count FROM scheduled_simulations WHERE status = 'scheduled'"
            result = await database.fetch_one(query, {})
            pending_count = result['count'] if result else 0
            
            # Count simulations due soon (next hour)
            query_due = """
                SELECT COUNT(*) as count FROM scheduled_simulations 
                WHERE status = 'scheduled' 
                AND scheduled_time <= NOW() + INTERVAL '1 hour'
            """
            result_due = await database.fetch_one(query_due, {})
            due_soon_count = result_due['count'] if result_due else 0
            
            return {
                "enabled": self.ENABLED,
                "running": self._running,
                "check_interval": self.CHECK_INTERVAL,
                "pending_simulations": pending_count,
                "due_within_hour": due_soon_count
            }
        except Exception as e:
            return {
                "enabled": self.ENABLED,
                "running": self._running,
                "error": str(e)
            }


# Global worker instance
scheduled_simulation_worker = ScheduledSimulationWorker()
