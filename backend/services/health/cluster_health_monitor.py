"""
Cluster Health Monitor - Background task for periodic cluster health checks

This service runs as a background task and periodically checks the health
of all active clusters, updating their status in the database.

Features:
- Periodic health checks for all active clusters
- Gadget health monitoring
- Automatic status updates in database
- Graceful degradation on failures
- Circuit breaker pattern for failing clusters
"""

import asyncio
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
import structlog

from config import settings
from database.postgresql import database
from services.cluster_connection_manager import cluster_connection_manager

logger = structlog.get_logger()


class ClusterHealthMonitor:
    """
    Background service for monitoring cluster health.
    
    Runs TWO separate tasks:
    1. Health check (every 2 min) - Lightweight gadget pod status check
    2. Resource sync (every 10 min) - Heavy node/pod/namespace count
    
    Uses circuit breaker pattern to avoid overwhelming failing clusters.
    """
    
    def __init__(self):
        # Configuration from settings
        self.HEALTH_CHECK_INTERVAL = settings.CLUSTER_HEALTH_CHECK_INTERVAL  # 2 min - lightweight
        self.RESOURCE_SYNC_INTERVAL = getattr(settings, 'CLUSTER_RESOURCE_SYNC_INTERVAL', 600)  # 10 min - heavy
        self.CIRCUIT_BREAKER_THRESHOLD = settings.CLUSTER_HEALTH_CIRCUIT_BREAKER_THRESHOLD
        self.CIRCUIT_BREAKER_RESET_TIME = settings.CLUSTER_HEALTH_CIRCUIT_BREAKER_RESET
        self._running = False
        self._health_task: Optional[asyncio.Task] = None
        self._resource_task: Optional[asyncio.Task] = None
        self._failure_counts: Dict[int, int] = {}
        self._circuit_open_until: Dict[int, datetime] = {}
        self._last_check: Dict[int, datetime] = {}
        self._last_resource_sync: Dict[int, datetime] = {}
    
    async def start(self) -> None:
        """Start the background monitoring tasks"""
        if self._running:
            logger.warning("Health monitor already running")
            return
        
        self._running = True
        # Start two separate tasks
        self._health_task = asyncio.create_task(self._run_health_check())
        self._resource_task = asyncio.create_task(self._run_resource_sync())
        logger.info("Cluster health monitor started", 
                   health_interval=self.HEALTH_CHECK_INTERVAL,
                   resource_interval=self.RESOURCE_SYNC_INTERVAL)
    
    async def stop(self) -> None:
        """Stop the background monitoring tasks"""
        self._running = False
        for task in [self._health_task, self._resource_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._health_task = None
        self._resource_task = None
        logger.info("Cluster health monitor stopped")
    
    async def _run_health_check(self) -> None:
        """Lightweight health check loop - only checks gadget pod status"""
        while self._running:
            try:
                await self._check_gadget_health_all()
            except Exception as e:
                logger.error("Health check cycle failed", error=str(e))
            
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
    
    async def _run_resource_sync(self) -> None:
        """Heavy resource sync loop - counts nodes/pods/namespaces"""
        # Initial delay to stagger with health checks
        await asyncio.sleep(30)
        
        while self._running:
            try:
                await self._sync_resources_all()
            except Exception as e:
                logger.error("Resource sync cycle failed", error=str(e))
            
            await asyncio.sleep(self.RESOURCE_SYNC_INTERVAL)
    
    async def _get_active_clusters(self) -> list:
        """Get list of active clusters from database"""
        query = """
            SELECT id, name, connection_type, gadget_namespace
            FROM clusters
            WHERE status = 'active'
            ORDER BY id
        """
        
        try:
            clusters = await database.fetch_all(query)
            return [dict(c) for c in clusters]
        except Exception as e:
            logger.error("Failed to fetch active clusters", error=str(e))
            return []
    
    async def _check_gadget_health_all(self) -> None:
        """LIGHTWEIGHT: Check only gadget health for all clusters (every 2 min)"""
        clusters = await self._get_active_clusters()
        
        if not clusters:
            return
        
        logger.debug("Starting gadget health check", cluster_count=len(clusters))
        
        async def _check_gadget(cluster: Dict[str, Any]) -> None:
            cluster_id = cluster["id"]
            if self._is_circuit_open(cluster_id):
                return
            
            try:
                # Only check gadget health - lightweight operation
                gadget_health = await asyncio.wait_for(
                    cluster_connection_manager.check_gadget_health(cluster_id),
                    timeout=30.0
                )
                
                # Update only gadget health, preserve resource counts
                await database.execute(
                    """UPDATE clusters SET
                        gadget_health_status = :status,
                        gadget_version = :version,
                        gadget_last_check = NOW()
                    WHERE id = :cluster_id""",
                    {
                        "cluster_id": cluster_id,
                        "status": gadget_health.get("health_status", "unknown"),
                        "version": gadget_health.get("version")
                    }
                )
                self._last_check[cluster_id] = datetime.utcnow()
                self._failure_counts[cluster_id] = 0
                
            except asyncio.TimeoutError:
                logger.warning("Gadget health check timed out", cluster_id=cluster_id)
                self._record_failure(cluster_id)
            except Exception as e:
                logger.debug("Gadget health check failed", cluster_id=cluster_id, error=str(e))
                self._record_failure(cluster_id)
        
        # Run all checks concurrently
        await asyncio.gather(*[_check_gadget(c) for c in clusters], return_exceptions=True)
    
    async def _sync_resources_all(self) -> None:
        """HEAVY: Sync resource counts for all clusters (every 10 min)"""
        clusters = await self._get_active_clusters()
        
        if not clusters:
            return
        
        logger.info("Starting resource sync", cluster_count=len(clusters))
        
        async def _sync_resources(cluster: Dict[str, Any]) -> None:
            cluster_id = cluster["id"]
            cluster_name = cluster["name"]
            
            if self._is_circuit_open(cluster_id):
                return
            
            try:
                # Get cluster info - this is the heavy operation
                cluster_info = await asyncio.wait_for(
                    cluster_connection_manager.get_cluster_info(cluster_id),
                    timeout=120.0  # 2 minutes for large clusters
                )
                
                # Only update if no error - preserve existing values on failure
                if not cluster_info.get("error"):
                    await database.execute(
                        """UPDATE clusters SET
                            total_nodes = :nodes,
                            total_pods = :pods,
                            total_namespaces = :namespaces,
                            k8s_version = :version,
                            updated_at = NOW()
                        WHERE id = :cluster_id""",
                        {
                            "cluster_id": cluster_id,
                            "nodes": cluster_info.get("total_nodes", 0),
                            "pods": cluster_info.get("total_pods", 0),
                            "namespaces": cluster_info.get("total_namespaces", 0),
                            "version": cluster_info.get("k8s_version")
                        }
                    )
                    self._last_resource_sync[cluster_id] = datetime.utcnow()
                    logger.info("Resource sync completed", 
                               cluster_id=cluster_id, 
                               cluster_name=cluster_name,
                               nodes=cluster_info.get("total_nodes"),
                               pods=cluster_info.get("total_pods"))
                else:
                    logger.warning("Resource sync failed, preserving existing values",
                                  cluster_id=cluster_id,
                                  error=cluster_info.get("error"))
                    
            except asyncio.TimeoutError:
                logger.warning("Resource sync timed out, preserving existing values", 
                             cluster_id=cluster_id, cluster_name=cluster_name)
            except Exception as e:
                logger.warning("Resource sync error, preserving existing values", 
                             cluster_id=cluster_id, error=str(e))
        
        # Run syncs concurrently but with some throttling for large deployments
        await asyncio.gather(*[_sync_resources(c) for c in clusters], return_exceptions=True)
        logger.info("Resource sync cycle completed")
    
    async def _check_all_clusters(self) -> None:
        """Check health of all active clusters - CONCURRENTLY with timeout"""
        clusters = await self._get_active_clusters()
        
        if not clusters:
            logger.debug("No active clusters to monitor")
            return
        
        logger.info("Starting health check cycle", cluster_count=len(clusters))
        
        results = {
            "checked": 0,
            "healthy": 0,
            "unhealthy": 0,
            "skipped": 0,
            "errors": 0
        }
        
        # Filter clusters with open circuit breakers
        clusters_to_check = []
        for cluster in clusters:
            cluster_id = cluster["id"]
            if self._is_circuit_open(cluster_id):
                results["skipped"] += 1
            else:
                clusters_to_check.append(cluster)
        
        if not clusters_to_check:
            logger.info("All clusters skipped (circuit breakers open)")
            return
        
        # Check all clusters CONCURRENTLY with individual timeouts
        # This prevents one slow cluster from blocking all others
        async def _check_with_timeout(cluster: Dict[str, Any]) -> tuple:
            """Check cluster with timeout - returns (cluster_id, success, error)"""
            cluster_id = cluster["id"]
            cluster_name = cluster["name"]
            try:
                # 120 second timeout per cluster (large clusters with 3000+ pods need more time)
                await asyncio.wait_for(
                    self._check_cluster(cluster),
                    timeout=120.0
                )
                return (cluster_id, True, None)
            except asyncio.TimeoutError:
                logger.warning("Cluster health check timed out", 
                             cluster_id=cluster_id,
                             cluster_name=cluster_name)
                self._record_failure(cluster_id)
                await self._update_cluster_error(cluster_id, "Health check timeout")
                return (cluster_id, False, "timeout")
            except Exception as e:
                logger.error("Cluster health check failed", 
                           cluster_id=cluster_id, 
                           cluster_name=cluster_name,
                           error=str(e))
                self._record_failure(cluster_id)
                return (cluster_id, False, str(e))
        
        # Run all health checks concurrently
        check_results = await asyncio.gather(
            *[_check_with_timeout(c) for c in clusters_to_check],
            return_exceptions=True
        )
        
        # Process results
        for result in check_results:
            if isinstance(result, Exception):
                results["errors"] += 1
            else:
                cluster_id, success, error = result
                results["checked"] += 1
                if success:
                    results["healthy"] += 1
                else:
                    if error == "timeout":
                        results["errors"] += 1  # Count timeouts as errors
                    else:
                        results["unhealthy"] += 1
        
        logger.info("Health check cycle completed", **results)
    
    async def _check_cluster(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of a single cluster"""
        cluster_id = cluster["id"]
        cluster_name = cluster["name"]
        
        result = {
            "cluster_id": cluster_id,
            "cluster_info": None,
            "gadget_health": None,
            "error": None
        }
        
        try:
            # Get cluster info with timeout (60 seconds - large clusters with 3000+ pods need more time)
            try:
                cluster_info = await asyncio.wait_for(
                    cluster_connection_manager.get_cluster_info(cluster_id),
                    timeout=60.0
                )
                result["cluster_info"] = cluster_info
            except asyncio.TimeoutError:
                logger.warning("get_cluster_info timed out", cluster_id=cluster_id)
                # Don't overwrite existing values on timeout - set error flag only
                cluster_info = {"error": "timeout"}
                result["cluster_info"] = cluster_info
            
            # Check gadget health with timeout (30 seconds - pod list is smaller)
            try:
                gadget_health = await asyncio.wait_for(
                    cluster_connection_manager.check_gadget_health(cluster_id),
                    timeout=30.0
                )
                result["gadget_health"] = gadget_health
            except asyncio.TimeoutError:
                logger.warning("check_gadget_health timed out", cluster_id=cluster_id)
                gadget_health = {"health_status": "unknown", "error": "timeout"}
                result["gadget_health"] = gadget_health
            
            # Update database
            await self._update_cluster_status(
                cluster_id=cluster_id,
                cluster_info=cluster_info,
                gadget_health=gadget_health
            )
            
            # Reset failure count on success
            self._failure_counts[cluster_id] = 0
            self._last_check[cluster_id] = datetime.utcnow()
            
            logger.debug("Cluster health check successful", 
                        cluster_id=cluster_id,
                        cluster_name=cluster_name,
                        gadget_status=gadget_health.get("health_status"))
            
        except Exception as e:
            result["error"] = str(e)
            self._record_failure(cluster_id)
            
            # Update cluster as unhealthy
            await self._update_cluster_error(cluster_id, str(e))
        
        return result
    
    async def _update_cluster_status(
        self, 
        cluster_id: int, 
        cluster_info: Dict[str, Any],
        gadget_health: Dict[str, Any]
    ) -> None:
        """Update cluster status in database - preserves existing values on error"""
        
        # Check if cluster_info has error - if so, don't update resource counts
        has_cluster_info_error = cluster_info.get("error") is not None
        
        if has_cluster_info_error:
            # Only update gadget health, preserve existing resource counts
            query = """
                UPDATE clusters SET
                    gadget_health_status = :gadget_health_status,
                    gadget_version = :gadget_version,
                    gadget_last_check = NOW(),
                    updated_at = NOW()
                WHERE id = :cluster_id
            """
            params = {
                "cluster_id": cluster_id,
                "gadget_health_status": gadget_health.get("health_status", "unknown"),
                "gadget_version": gadget_health.get("version")
            }
            logger.warning("Cluster info has error, preserving existing resource counts", 
                          cluster_id=cluster_id, error=cluster_info.get("error"))
        else:
            # Full update - cluster info is valid
            query = """
                UPDATE clusters SET
                    total_nodes = :total_nodes,
                    total_pods = :total_pods,
                    total_namespaces = :total_namespaces,
                    k8s_version = :k8s_version,
                    gadget_health_status = :gadget_health_status,
                    gadget_version = :gadget_version,
                    gadget_last_check = NOW(),
                    updated_at = NOW()
                WHERE id = :cluster_id
            """
            params = {
                "cluster_id": cluster_id,
                "total_nodes": cluster_info.get("total_nodes", 0),
                "total_pods": cluster_info.get("total_pods", 0),
                "total_namespaces": cluster_info.get("total_namespaces", 0),
                "k8s_version": cluster_info.get("k8s_version"),
                "gadget_health_status": gadget_health.get("health_status", "unknown"),
                "gadget_version": gadget_health.get("version")
            }
        
        try:
            await database.execute(query, params)
        except Exception as e:
            logger.error("Failed to update cluster status", cluster_id=cluster_id, error=str(e))
    
    async def _update_cluster_error(self, cluster_id: int, error: str) -> None:
        """Update cluster with error status"""
        query = """
            UPDATE clusters SET
                gadget_health_status = 'unknown',
                gadget_last_check = NOW(),
                updated_at = NOW()
            WHERE id = :cluster_id
        """
        
        try:
            await database.execute(query, {"cluster_id": cluster_id})
        except Exception as e:
            logger.error("Failed to update cluster error status", cluster_id=cluster_id, error=str(e))
    
    def _record_failure(self, cluster_id: int) -> None:
        """Record a failure for circuit breaker logic"""
        self._failure_counts[cluster_id] = self._failure_counts.get(cluster_id, 0) + 1
        
        if self._failure_counts[cluster_id] >= self.CIRCUIT_BREAKER_THRESHOLD:
            # Open circuit
            self._circuit_open_until[cluster_id] = datetime.utcnow() + timedelta(
                seconds=self.CIRCUIT_BREAKER_RESET_TIME
            )
            logger.warning("Circuit breaker opened for cluster", 
                          cluster_id=cluster_id,
                          failure_count=self._failure_counts[cluster_id],
                          reopen_at=self._circuit_open_until[cluster_id].isoformat())
    
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
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the health monitor"""
        return {
            "running": self._running,
            "last_health_checks": {
                cid: ts.isoformat() 
                for cid, ts in self._last_check.items()
            },
            "last_resource_syncs": {
                cid: ts.isoformat() 
                for cid, ts in self._last_resource_sync.items()
            },
            "failure_counts": dict(self._failure_counts),
            "circuits_open": {
                cid: ts.isoformat() 
                for cid, ts in self._circuit_open_until.items()
            },
            "config": {
                "health_check_interval": self.HEALTH_CHECK_INTERVAL,
                "resource_sync_interval": self.RESOURCE_SYNC_INTERVAL,
                "circuit_breaker_threshold": self.CIRCUIT_BREAKER_THRESHOLD,
                "circuit_breaker_reset_time": self.CIRCUIT_BREAKER_RESET_TIME
            }
        }
    
    async def force_check(self, cluster_id: int) -> Dict[str, Any]:
        """Force an immediate health check for a specific cluster"""
        cluster = await database.fetch_one(
            "SELECT id, name, connection_type, gadget_namespace FROM clusters WHERE id = :cluster_id",
            {"cluster_id": cluster_id}
        )
        
        if not cluster:
            return {"error": f"Cluster {cluster_id} not found"}
        
        # Reset circuit breaker for this cluster
        if cluster_id in self._circuit_open_until:
            del self._circuit_open_until[cluster_id]
        self._failure_counts[cluster_id] = 0
        
        return await self._check_cluster(dict(cluster))


# Singleton instance
cluster_health_monitor = ClusterHealthMonitor()

