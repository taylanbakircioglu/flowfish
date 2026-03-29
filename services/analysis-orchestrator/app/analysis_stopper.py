"""
Analysis Stopper - Stop running analyses and cleanup
Supports both single-cluster and multi-cluster analyses
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.database import db_manager, AnalysisStatus
from app.gadget_client import get_gadget_client, GadgetClient

logger = logging.getLogger(__name__)


class AnalysisStopper:
    """Stops running analyses and cleans up resources (supports multi-cluster)"""
    
    def __init__(self):
        self.gadget_client = get_gadget_client()
        logger.info("AnalysisStopper initialized")
    
    async def stop_analysis(self, analysis_id: int) -> Dict[str, Any]:
        """
        Stop a running analysis (supports multi-cluster)
        
        This will:
        1. Stop Inspector Gadget trace on each cluster
        2. Wait for RabbitMQ queues to drain
        3. Update analysis status to stopped
        4. Return summary statistics
        
        Args:
            analysis_id: Analysis ID to stop
        
        Returns:
            Dict with stop summary:
            {
                "analysis_id": 123,
                "status": "stopped",
                "stopped_at": "2024-01-20T10:30:00Z",
                "duration_seconds": 1800,
                "events_collected": 12450,
                "cluster_results": {...}  # Per-cluster stop results for multi-cluster
            }
        """
        logger.info(f"🛑 Stopping analysis {analysis_id}")
        
        # Get analysis
        analysis = await db_manager.get_analysis(analysis_id)
        if not analysis:
            raise ValueError(f"Analysis {analysis_id} not found")
        
        if analysis.status != AnalysisStatus.RUNNING:
            raise ValueError(f"Analysis {analysis_id} is not running (status: {analysis.status})")
        
        # Check for multi-cluster analysis
        is_multi_cluster = getattr(analysis, 'is_multi_cluster', False)
        cluster_ids = getattr(analysis, 'cluster_ids', None) or [analysis.cluster_id]
        
        if is_multi_cluster:
            logger.info(f"🌐 Stopping multi-cluster analysis: {len(cluster_ids)} clusters")
        
        # Update status to stopping
        await db_manager.update_analysis(analysis_id, {"status": AnalysisStatus.STOPPING})
        
        try:
            # 🛑 Stop Inspector Gadget traces on all clusters
            stop_results = await self._stop_gadget_traces(analysis_id, cluster_ids)
            
            total_events = sum(r.get("events_collected", 0) for r in stop_results.values())
            
            # Calculate duration
            stopped_at = datetime.utcnow()
            if analysis.started_at:
                duration_seconds = int((stopped_at - analysis.started_at).total_seconds())
            else:
                duration_seconds = 0
            
            # Update analysis status
            await db_manager.update_analysis(analysis_id, {
                "status": AnalysisStatus.STOPPED,
                "stopped_at": stopped_at
            })
            
            # Also update the running analysis_run record
            running_run = await db_manager.get_running_run_for_analysis(analysis_id)
            if running_run:
                await db_manager.update_analysis_run(
                    running_run.id,
                    {
                        "status": "stopped",
                        "end_time": stopped_at,
                        "duration_seconds": duration_seconds
                    }
                )
                logger.info(f"Updated run {running_run.id} status to stopped")
            
            logger.info(f"✅ Analysis {analysis_id} stopped after {duration_seconds}s "
                       f"({total_events} total events from {len(cluster_ids)} clusters)")
            
            result = {
                "analysis_id": analysis_id,
                "status": "stopped",
                "stopped_at": stopped_at.isoformat(),
                "duration_seconds": duration_seconds,
                "events_collected": total_events,
                "is_multi_cluster": is_multi_cluster,
                "cluster_count": len(cluster_ids)
            }
            
            # Add per-cluster results for multi-cluster analyses
            if is_multi_cluster:
                result["cluster_results"] = stop_results
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Failed to stop analysis {analysis_id}: {e}")
            
            # Revert status to running (or mark as error)
            await db_manager.update_analysis(analysis_id, {"status": AnalysisStatus.ERROR})
            
            raise
    
    async def _stop_gadget_traces(
        self,
        analysis_id: int,
        cluster_ids: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Stop Inspector Gadget traces on multiple clusters
        
        Args:
            analysis_id: Analysis ID
            cluster_ids: List of cluster IDs to stop traces on
        
        Returns:
            Dict mapping cluster_id to stop result
        """
        results = {}
        
        for cluster_id in cluster_ids:
            try:
                # Get cluster info to find gadget endpoint
                cluster = await db_manager.get_cluster(cluster_id)
                
                if cluster:
                    # Create cluster-specific gadget client if needed
                    gadget_endpoint = getattr(cluster, 'gadget_endpoint', None)
                    
                    if gadget_endpoint:
                        # Use cluster-specific gadget client
                        cluster_gadget_client = GadgetClient(gadget_endpoint=gadget_endpoint)
                        try:
                            gadget_result = await cluster_gadget_client.stop_trace(
                                f"{analysis_id}-{cluster_id}"
                            )
                        finally:
                            await cluster_gadget_client.close()
                    else:
                        # Use default gadget client (in-cluster)
                        gadget_result = await self.gadget_client.stop_trace(
                            f"{analysis_id}-{cluster_id}"
                        )
                    
                    results[cluster_id] = {
                        "status": "stopped",
                        "events_collected": gadget_result.get("events_collected", 0)
                    }
                    logger.info(f"✅ Gadget trace stopped for cluster {cluster_id}: "
                               f"{gadget_result.get('events_collected', 0)} events")
                else:
                    results[cluster_id] = {
                        "status": "skipped",
                        "error": f"Cluster {cluster_id} not found",
                        "events_collected": 0
                    }
            except Exception as e:
                logger.warning(f"⚠️  Failed to stop Gadget trace for cluster {cluster_id}: {e}")
                results[cluster_id] = {
                    "status": "error",
                    "error": str(e),
                    "events_collected": 0
                }
        
        return results
    
    async def stop_all_analyses(self, cluster_id: int) -> Dict[str, Any]:
        """
        Stop all running analyses for a cluster
        
        Args:
            cluster_id: Cluster ID
        
        Returns:
            Dict with summary:
            {
                "cluster_id": 1,
                "stopped_count": 3,
                "failed_count": 0
            }
        """
        logger.info(f"🛑 Stopping all analyses for cluster {cluster_id}")
        
        # Get all running analyses for cluster
        analyses = await db_manager.list_analyses(cluster_id=cluster_id, status=AnalysisStatus.RUNNING)
        
        stopped_count = 0
        failed_count = 0
        
        for analysis in analyses:
            try:
                await self.stop_analysis(analysis.id)
                stopped_count += 1
            except Exception as e:
                logger.error(f"Failed to stop analysis {analysis.id}: {e}")
                failed_count += 1
        
        logger.info(f"✅ Stopped {stopped_count} analyses ({failed_count} failed)")
        
        return {
            "cluster_id": cluster_id,
            "stopped_count": stopped_count,
            "failed_count": failed_count
        }


# Global singleton
_analysis_stopper = None


def get_analysis_stopper() -> AnalysisStopper:
    """Get or create global AnalysisStopper instance"""
    global _analysis_stopper
    if _analysis_stopper is None:
        _analysis_stopper = AnalysisStopper()
    return _analysis_stopper

