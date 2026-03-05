"""
Cluster Cache Service - Enterprise caching layer for cluster resources

Uses Redis for distributed caching with Cache-Aside pattern:
1. Check cache first
2. On miss, fetch from source (cluster-manager for in-cluster, direct API for remote)
3. Store in cache with TTL
4. Background refresh for proactive updates

**Multi-Cluster Support:**
- In-cluster connections: Use cluster-manager gRPC service
- Remote clusters (token/kubeconfig): Use cluster_info_service with stored credentials

Cache Keys:
- cluster:info:{cluster_id} - Cluster info (nodes, pods, namespaces count)
- cluster:namespaces:{cluster_id} - List of namespaces
- cluster:deployments:{cluster_id}:{namespace} - List of deployments
- cluster:pods:{cluster_id}:{namespace} - List of pods
- cluster:labels:{cluster_id}:{resource_type}:{namespace} - Labels
- cluster:gadget_health:{cluster_id} - Gadget health status
"""

import json
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

from database.redis import redis_client
from database.postgresql import database
from services.cluster_connection_manager import cluster_connection_manager
# Note: Legacy imports removed - all calls now go through ClusterConnectionManager

logger = structlog.get_logger()


class ClusterCacheService:
    """
    Enterprise caching layer for cluster resources.
    
    Features:
    - Cache-aside pattern with configurable TTL
    - Distributed cache via Redis
    - Automatic cache invalidation
    - Background refresh support
    - Graceful degradation on cache failures
    """
    
    # Cache TTL settings (seconds)
    TTL_CLUSTER_INFO = 60  # 1 minute - changes less frequently
    TTL_NAMESPACES = 120   # 2 minutes - relatively stable
    TTL_DEPLOYMENTS = 30   # 30 seconds - more dynamic
    TTL_PODS = 15          # 15 seconds - highly dynamic
    TTL_LABELS = 120       # 2 minutes - relatively stable
    TTL_GADGET_HEALTH = 30 # 30 seconds - important to be fresh
    
    # Cache key prefixes
    PREFIX = "flowfish:cluster"
    
    def __init__(self):
        self.redis = redis_client
        self._background_tasks = set()
    
    # =========================================================================
    # Cache Key Builders
    # =========================================================================
    
    def _key_cluster_info(self, cluster_id: int) -> str:
        return f"{self.PREFIX}:info:{cluster_id}"
    
    def _key_namespaces(self, cluster_id: int) -> str:
        return f"{self.PREFIX}:namespaces:{cluster_id}"
    
    def _key_deployments(self, cluster_id: int, namespace: Optional[str] = None) -> str:
        ns = namespace or "_all"
        return f"{self.PREFIX}:deployments:{cluster_id}:{ns}"
    
    def _key_pods(self, cluster_id: int, namespace: Optional[str] = None) -> str:
        ns = namespace or "_all"
        return f"{self.PREFIX}:pods:{cluster_id}:{ns}"
    
    def _key_labels(self, cluster_id: int, resource_type: str, namespace: Optional[str] = None) -> str:
        ns = namespace or "_all"
        return f"{self.PREFIX}:labels:{cluster_id}:{resource_type}:{ns}"
    
    def _key_gadget_health(self, cluster_id: int) -> str:
        return f"{self.PREFIX}:gadget_health:{cluster_id}"
    
    # =========================================================================
    # Generic Cache Operations
    # =========================================================================
    
    async def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("Cache get failed", key=key, error=str(e))
            return None
    
    async def _set_cached(self, key: str, value: Any, ttl: int) -> bool:
        """Set value in cache with TTL"""
        try:
            await self.redis.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except Exception as e:
            logger.warning("Cache set failed", key=key, error=str(e))
            return False
    
    async def _delete_cached(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning("Cache delete failed", key=key, error=str(e))
            return False
    
    # =========================================================================
    # Cluster Info
    # =========================================================================
    
    async def get_cluster_info(self, cluster_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get cluster info with caching.
        Supports both in-cluster and remote cluster connections.
        
        Args:
            cluster_id: Cluster ID
            force_refresh: Skip cache and fetch fresh data
            
        Returns:
            Cluster info dict
        """
        cache_key = self._key_cluster_info(cluster_id)
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                logger.debug("Cache hit: cluster info", cluster_id=cluster_id)
                return cached
        
        # Cache miss - fetch from source
        logger.debug("Cache miss: cluster info", cluster_id=cluster_id)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.get_cluster_info(cluster_id)
            
            # Cache successful response
            if not data.get("error"):
                data["_cached_at"] = datetime.utcnow().isoformat()
                await self._set_cached(cache_key, data, self.TTL_CLUSTER_INFO)
            
            return data
        except Exception as e:
            logger.error("Failed to fetch cluster info", cluster_id=cluster_id, error=str(e))
            # Return cached data if available (stale-while-revalidate)
            stale = await self._get_cached(cache_key)
            if stale:
                stale["_stale"] = True
                return stale
            return {"error": str(e)}
    
    # =========================================================================
    # Namespaces
    # =========================================================================
    
    async def get_namespaces(self, cluster_id: int, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get namespaces with caching.
        Supports both in-cluster and remote cluster connections.
        """
        cache_key = self._key_namespaces(cluster_id)
        
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.debug("Cache hit: namespaces", cluster_id=cluster_id, count=len(cached))
                return cached
        
        logger.debug("Cache miss: namespaces", cluster_id=cluster_id)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.get_namespaces(cluster_id)
            
            # Cache even empty lists
            await self._set_cached(cache_key, data, self.TTL_NAMESPACES)
            
            return data
        except Exception as e:
            logger.error("Failed to fetch namespaces", cluster_id=cluster_id, error=str(e))
            # Return cached data if available
            stale = await self._get_cached(cache_key)
            return stale if stale else []
    
    # =========================================================================
    # Deployments
    # =========================================================================
    
    async def get_deployments(self, cluster_id: int, namespace: Optional[str] = None, 
                             force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get deployments with caching.
        Supports both in-cluster and remote cluster connections.
        """
        cache_key = self._key_deployments(cluster_id, namespace)
        
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.debug("Cache hit: deployments", cluster_id=cluster_id, namespace=namespace)
                return cached
        
        logger.debug("Cache miss: deployments", cluster_id=cluster_id, namespace=namespace)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.get_deployments(cluster_id, namespace)
            
            await self._set_cached(cache_key, data, self.TTL_DEPLOYMENTS)
            return data
        except Exception as e:
            logger.error("Failed to fetch deployments", cluster_id=cluster_id, error=str(e))
            stale = await self._get_cached(cache_key)
            return stale if stale else []
    
    # =========================================================================
    # Pods
    # =========================================================================
    
    async def get_pods(self, cluster_id: int, namespace: Optional[str] = None,
                      label_selector: Optional[str] = None,
                      force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get pods with caching.
        Supports both in-cluster and remote cluster connections.
        """
        # Include label_selector in cache key for proper caching
        cache_key = self._key_pods(cluster_id, namespace)
        if label_selector:
            cache_key = f"{cache_key}:labels:{label_selector}"
        
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.debug("Cache hit: pods", cluster_id=cluster_id, namespace=namespace)
                return cached
        
        logger.debug("Cache miss: pods", cluster_id=cluster_id, namespace=namespace)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.get_pods(cluster_id, namespace, label_selector)
            
            await self._set_cached(cache_key, data, self.TTL_PODS)
            return data
        except Exception as e:
            logger.error("Failed to fetch pods", cluster_id=cluster_id, error=str(e))
            stale = await self._get_cached(cache_key)
            return stale if stale else []
    
    # =========================================================================
    # Labels
    # =========================================================================
    
    async def get_labels(self, cluster_id: int, resource_type: str = "pods",
                        namespace: Optional[str] = None,
                        force_refresh: bool = False) -> List[str]:
        """
        Get labels with caching.
        Supports both in-cluster and remote cluster connections.
        """
        cache_key = self._key_labels(cluster_id, resource_type, namespace)
        
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.debug("Cache hit: labels", cluster_id=cluster_id, resource_type=resource_type)
                return cached
        
        logger.debug("Cache miss: labels", cluster_id=cluster_id, resource_type=resource_type)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.get_labels(cluster_id, namespace)
            
            await self._set_cached(cache_key, data, self.TTL_LABELS)
            return data
        except Exception as e:
            logger.error("Failed to fetch labels", cluster_id=cluster_id, error=str(e))
            stale = await self._get_cached(cache_key)
            return stale if stale else []
    
    # =========================================================================
    # Gadget Health
    # =========================================================================
    
    async def get_gadget_health(self, cluster_id: int,
                               force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get gadget health with caching.
        
        Note: gadget_namespace is retrieved from cluster config in database.
        """
        cache_key = self._key_gadget_health(cluster_id)
        
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                logger.debug("Cache hit: gadget health", cluster_id=cluster_id)
                return cached
        
        logger.debug("Cache miss: gadget health", cluster_id=cluster_id)
        
        try:
            # Use unified ClusterConnectionManager
            data = await cluster_connection_manager.check_gadget_health(cluster_id)
            
            if data.get("health_status") != "unknown":
                data["_cached_at"] = datetime.utcnow().isoformat()
                await self._set_cached(cache_key, data, self.TTL_GADGET_HEALTH)
            
            return data
        except Exception as e:
            logger.error("Failed to fetch gadget health", cluster_id=cluster_id, error=str(e))
            stale = await self._get_cached(cache_key)
            if stale:
                stale["_stale"] = True
                return stale
            return {"health_status": "unknown", "error": str(e)}
    
    # =========================================================================
    # Cache Invalidation
    # =========================================================================
    
    async def invalidate_cluster(self, cluster_id: int) -> None:
        """
        Invalidate all cached data for a cluster.
        Use when cluster config changes or on manual refresh.
        """
        patterns = [
            self._key_cluster_info(cluster_id),
            self._key_namespaces(cluster_id),
            self._key_gadget_health(cluster_id),
        ]
        
        # Delete known keys
        for key in patterns:
            await self._delete_cached(key)
        
        # Delete pattern-based keys (deployments, pods, labels with namespace variations)
        try:
            # Use SCAN to find and delete pattern-matched keys
            async for key in self.redis.scan_iter(f"{self.PREFIX}:deployments:{cluster_id}:*"):
                await self.redis.delete(key)
            async for key in self.redis.scan_iter(f"{self.PREFIX}:pods:{cluster_id}:*"):
                await self.redis.delete(key)
            async for key in self.redis.scan_iter(f"{self.PREFIX}:labels:{cluster_id}:*"):
                await self.redis.delete(key)
        except Exception as e:
            logger.warning("Pattern-based cache invalidation failed", cluster_id=cluster_id, error=str(e))
        
        logger.info("Cache invalidated for cluster", cluster_id=cluster_id)
    
    async def invalidate_all(self) -> None:
        """
        Invalidate all cluster cache.
        Use with caution - mainly for debugging/testing.
        """
        try:
            async for key in self.redis.scan_iter(f"{self.PREFIX}:*"):
                await self.redis.delete(key)
            logger.info("All cluster cache invalidated")
        except Exception as e:
            logger.error("Failed to invalidate all cache", error=str(e))
    
    # =========================================================================
    # Background Refresh
    # =========================================================================
    
    async def refresh_cluster_cache(self, cluster_id: int) -> Dict[str, Any]:
        """
        Proactively refresh all cache for a cluster.
        Can be called from background job or sync endpoint.
        
        Returns:
            Summary of refresh results
        """
        results = {
            "cluster_id": cluster_id,
            "refreshed_at": datetime.utcnow().isoformat(),
            "cluster_info": False,
            "namespaces": False,
            "gadget_health": False,
            "errors": []
        }
        
        try:
            # Refresh cluster info
            info = await self.get_cluster_info(cluster_id, force_refresh=True)
            results["cluster_info"] = not info.get("error")
        except Exception as e:
            results["errors"].append(f"cluster_info: {str(e)}")
        
        try:
            # Refresh namespaces
            namespaces = await self.get_namespaces(cluster_id, force_refresh=True)
            results["namespaces"] = len(namespaces) > 0
            results["namespace_count"] = len(namespaces)
        except Exception as e:
            results["errors"].append(f"namespaces: {str(e)}")
        
        try:
            # Refresh gadget health
            health = await self.get_gadget_health(cluster_id, force_refresh=True)
            results["gadget_health"] = health.get("health_status") != "unknown"
        except Exception as e:
            results["errors"].append(f"gadget_health: {str(e)}")
        
        logger.info("Cluster cache refreshed", **results)
        return results
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check cache service health.
        """
        try:
            # Test Redis connectivity
            await self.redis.ping()
            
            # Get cache stats
            info = await self.redis.info("keyspace")
            
            return {
                "healthy": True,
                "redis_connected": True,
                "keyspace_info": info
            }
        except Exception as e:
            return {
                "healthy": False,
                "redis_connected": False,
                "error": str(e)
            }


# Singleton instance
cluster_cache_service = ClusterCacheService()

