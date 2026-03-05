"""
Redis cache connection and utilities
"""

from redis import Redis
import json
from typing import Any, Optional, List, Dict
import structlog
import asyncio

from config import settings

logger = structlog.get_logger()

# Global Redis client (sync, will wrap with async)
redis_client: Optional[Redis] = None

def get_redis_client() -> Redis:
    """Get Redis client"""
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=settings.REDIS_POOL_SIZE
        )
    return redis_client

# Initialize client
redis_client = get_redis_client()

# Simple async wrapper for Redis
class AsyncRedisWrapper:
    """Simple async wrapper for sync Redis client"""
    
    def __init__(self, client: Redis):
        self.client = client
    
    async def ping(self):
        """Async ping"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.ping)
    
    async def get(self, key: str):
        """Async get"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.get, key)
    
    async def set(self, key: str, value: str, ex: int = None, nx: bool = False):
        """Async set with optional TTL and NX (set if not exists)"""
        loop = asyncio.get_running_loop()
        if nx:
            # SET with NX flag (only set if key does not exist)
            return await loop.run_in_executor(None, lambda: self.client.set(key, value, ex=ex, nx=True))
        elif ex is not None:
            return await loop.run_in_executor(None, lambda: self.client.set(key, value, ex=ex))
        return await loop.run_in_executor(None, lambda: self.client.set(key, value))
    
    async def setex(self, key: str, time: int, value: str):
        """Async setex - set with expiration time in seconds"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.client.setex(key, time, value))
    
    async def exists(self, key: str) -> int:
        """Async exists - check if key exists"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.exists, key)
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """Async incr - increment key value"""
        loop = asyncio.get_running_loop()
        if amount == 1:
            return await loop.run_in_executor(None, self.client.incr, key)
        return await loop.run_in_executor(None, lambda: self.client.incrby(key, amount))
    
    async def expire(self, key: str, time: int) -> bool:
        """Async expire - set key expiration time in seconds"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.client.expire(key, time))
    
    async def delete(self, *keys: str):
        """Async delete - delete one or more keys"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.client.delete(*keys))
    
    async def keys(self, pattern: str):
        """Async keys - get keys matching pattern"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.keys, pattern)
    
    async def info(self, section: str = None):
        """Async info - get Redis server info"""
        loop = asyncio.get_running_loop()
        if section:
            return await loop.run_in_executor(None, lambda: self.client.info(section))
        return await loop.run_in_executor(None, self.client.info)
    
    async def close(self):
        """Async close"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.client.close)
    
    async def scan_iter(self, pattern: str):
        """Async scan iterator - yields keys matching pattern"""
        loop = asyncio.get_running_loop()
        # Get all matching keys at once (scan_iter is generator, convert to list)
        keys = await loop.run_in_executor(
            None, 
            lambda: list(self.client.scan_iter(match=pattern))
        )
        for key in keys:
            yield key

# Create async wrapper
redis_client = AsyncRedisWrapper(get_redis_client())

class CacheService:
    """Redis cache service with common operations"""
    
    def __init__(self, client: AsyncRedisWrapper):
        self.client = client
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("Cache get failed", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, ttl: int = settings.CACHE_TTL_SECONDS) -> bool:
        """Set value in cache with TTL"""
        try:
            await self.client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.error("Cache set failed", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error("Cache delete failed", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            logger.error("Cache exists check failed", key=key, error=str(e))
            return False
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        try:
            return await self.client.incr(key, amount)
        except Exception as e:
            logger.error("Cache increment failed", key=key, error=str(e))
            return 0
    
    async def set_if_not_exists(self, key: str, value: Any, ttl: int = settings.CACHE_TTL_SECONDS) -> bool:
        """Set value only if key doesn't exist"""
        try:
            result = await self.client.set(key, json.dumps(value), ex=ttl, nx=True)
            return result is True
        except Exception as e:
            logger.error("Cache set_if_not_exists failed", key=key, error=str(e))
            return False
    
    async def get_pattern(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        try:
            return await self.client.keys(pattern)
        except Exception as e:
            logger.error("Cache pattern search failed", pattern=pattern, error=str(e))
            return []
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern"""
        try:
            keys = await self.get_pattern(pattern)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.error("Cache pattern delete failed", pattern=pattern, error=str(e))
            return 0

# Cache service instance
cache = CacheService(redis_client)

# Pub/Sub for real-time updates
# PubSub temporarily disabled for MVP
# Will be implemented later with full async redis client

# PubSub disabled for MVP
# pubsub = PubSubService(redis_client)

# Common cache keys
class CacheKeys:
    """Cache key patterns"""
    
    USER_SESSION = "session:user:{user_id}"
    USER_PERMISSIONS = "permissions:user:{user_id}"
    CLUSTER_INFO = "cluster:info:{cluster_id}"
    WORKLOAD_LIST = "workloads:cluster:{cluster_id}"
    COMMUNICATION_LIST = "communications:cluster:{cluster_id}"
    ANALYSIS_STATUS = "analysis:status:{analysis_id}"
    GRAPH_DATA = "graph:cluster:{cluster_id}"
    
    # Rate limiting
    RATE_LIMIT_USER = "rate_limit:user:{user_id}"
    RATE_LIMIT_IP = "rate_limit:ip:{ip_address}"

# Connection test
async def test_redis_connection():
    """Test Redis connection"""
    try:
        await redis_client.ping()
        logger.info("Redis connection test successful")
        return True
    except Exception as e:
        logger.error("Redis connection test failed", error=str(e))
        return False
