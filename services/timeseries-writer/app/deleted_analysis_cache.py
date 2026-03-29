"""
Deleted Analysis Cache

Uses Redis to track which analyses have been deleted.
Writers check this cache before writing events to avoid creating orphaned data.

Key format: flowfish:deleted_analysis:{analysis_id}
TTL: 24 hours (to automatically clean up old entries)

Version: 1.0.1 - Added redis dependency
"""

import logging
import redis
from typing import Set, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Redis key prefix for deleted analyses
DELETED_KEY_PREFIX = "flowfish:deleted_analysis:"
DELETED_TTL_SECONDS = 86400  # 24 hours


class DeletedAnalysisCache:
    """Cache for tracking deleted analyses using Redis"""
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._local_cache: Set[str] = set()  # Fallback if Redis unavailable
        self._connected = False
    
    def _connect(self) -> bool:
        """Connect to Redis"""
        if self._connected and self._client:
            return True
            
        try:
            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self._client.ping()
            self._connected = True
            logger.info(f"✅ Connected to Redis at {settings.redis_host}:{settings.redis_port}")
            return True
            
        except redis.ConnectionError as e:
            logger.warning(f"Cannot connect to Redis: {e}. Using local cache fallback.")
            self._connected = False
            return False
        except Exception as e:
            logger.warning(f"Redis error: {e}. Using local cache fallback.")
            self._connected = False
            return False
    
    def is_deleted(self, analysis_id: str) -> bool:
        """
        Check if an analysis has been deleted.
        
        Multi-cluster support: analysis_id can be in format '{id}' or '{id}-{cluster_id}'
        For multi-cluster, we check both the full ID and the base ID (before '-')
        
        Args:
            analysis_id: Analysis ID to check (may include cluster suffix)
            
        Returns:
            True if analysis is in deleted cache, False otherwise
        """
        if not analysis_id:
            return False
            
        analysis_id_str = str(analysis_id)
        
        # Multi-cluster support: extract base analysis_id if format is '{id}-{cluster_id}'
        base_analysis_id = analysis_id_str.split('-')[0] if '-' in analysis_id_str else analysis_id_str
        
        # Try Redis first
        if self._connect():
            try:
                # Check both the full ID and the base ID (for multi-cluster traces)
                key_full = f"{DELETED_KEY_PREFIX}{analysis_id_str}"
                key_base = f"{DELETED_KEY_PREFIX}{base_analysis_id}"
                
                # Check if either the full analysis_id or base analysis_id is deleted
                if self._client.exists(key_full):
                    logger.debug(f"Analysis {analysis_id_str} is in deleted cache (full match)")
                    return True
                if analysis_id_str != base_analysis_id and self._client.exists(key_base):
                    logger.debug(f"Analysis {analysis_id_str} is in deleted cache (base {base_analysis_id} match)")
                    return True
                return False
            except Exception as e:
                logger.warning(f"Redis check failed: {e}")
        
        # Fallback to local cache - check both full and base ID
        if analysis_id_str in self._local_cache:
            return True
        if analysis_id_str != base_analysis_id and base_analysis_id in self._local_cache:
            return True
        return False
    
    def mark_deleted(self, analysis_id: str) -> bool:
        """
        Mark an analysis as deleted.
        
        Args:
            analysis_id: Analysis ID to mark as deleted
            
        Returns:
            True if successfully marked, False otherwise
        """
        if not analysis_id:
            return False
            
        analysis_id_str = str(analysis_id)
        
        # Always add to local cache as backup
        self._local_cache.add(analysis_id_str)
        
        # Try Redis
        if self._connect():
            try:
                key = f"{DELETED_KEY_PREFIX}{analysis_id_str}"
                self._client.setex(key, DELETED_TTL_SECONDS, "1")
                logger.info(f"Marked analysis {analysis_id_str} as deleted in Redis")
                return True
            except Exception as e:
                logger.warning(f"Redis mark_deleted failed: {e}")
        
        return False
    
    def remove_deleted(self, analysis_id: str) -> bool:
        """
        Remove an analysis from deleted cache (if recreated).
        
        Args:
            analysis_id: Analysis ID to remove from cache
            
        Returns:
            True if successfully removed, False otherwise
        """
        if not analysis_id:
            return False
            
        analysis_id_str = str(analysis_id)
        
        # Remove from local cache
        self._local_cache.discard(analysis_id_str)
        
        # Try Redis
        if self._connect():
            try:
                key = f"{DELETED_KEY_PREFIX}{analysis_id_str}"
                self._client.delete(key)
                logger.info(f"Removed analysis {analysis_id_str} from deleted cache")
                return True
            except Exception as e:
                logger.warning(f"Redis remove_deleted failed: {e}")
        
        return False
    
    def get_all_deleted(self) -> Set[str]:
        """
        Get all deleted analysis IDs.
        
        Returns:
            Set of deleted analysis IDs
        """
        deleted = set(self._local_cache)
        
        if self._connect():
            try:
                pattern = f"{DELETED_KEY_PREFIX}*"
                keys = self._client.keys(pattern)
                for key in keys:
                    # Extract analysis_id from key
                    aid = key.replace(DELETED_KEY_PREFIX, "")
                    deleted.add(aid)
            except Exception as e:
                logger.warning(f"Redis get_all_deleted failed: {e}")
        
        return deleted


# Global instance
deleted_analysis_cache = DeletedAnalysisCache()

