import asyncio
import time
from collections import deque
from typing import Tuple, List, Optional


class EventBuffer:
    """Thread-safe circular buffer with cursor-based pagination."""

    def __init__(self, max_size: int = 100_000, ttl_seconds: int = 3600):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._buffer: deque = deque(maxlen=max_size)
        self._cursor: int = 0
        self._lock = asyncio.Lock()
        self._stats = {
            "total_received": 0,
            "total_evicted": 0,
            "http": 0,
            "grpc": 0,
            "dns": 0,
        }

    async def add(self, event: dict) -> None:
        async with self._lock:
            self._cursor += 1
            entry = {
                "_id": self._cursor,
                "_ts": time.time(),
                "event": event,
            }
            if len(self._buffer) == self._max_size:
                self._stats["total_evicted"] += 1
            self._buffer.append(entry)
            self._stats["total_received"] += 1
            event_type = event.get("event_type", "")
            if "http" in event_type:
                self._stats["http"] += 1
            elif "grpc" in event_type:
                self._stats["grpc"] += 1
            elif "dns" in event_type:
                self._stats["dns"] += 1

    async def get_events(
        self, cursor: Optional[str] = None, limit: int = 500
    ) -> Tuple[List[dict], str, bool]:
        """Return (events, next_cursor, has_more)."""
        async with self._lock:
            self._evict_expired()
            if cursor:
                try:
                    start_id = int(cursor)
                except (ValueError, TypeError):
                    start_id = -1
                if start_id < 0:
                    return [], str(self._cursor), False
            else:
                start_id = 0

            oldest_id = self._buffer[0]["_id"] if self._buffer else self._cursor
            if start_id > 0 and start_id < oldest_id:
                start_id = oldest_id - 1

            events = []
            next_cursor = str(start_id)
            hit_limit = False
            for entry in self._buffer:
                if entry["_id"] <= start_id:
                    continue
                events.append(entry["event"])
                next_cursor = str(entry["_id"])
                if len(events) >= limit:
                    hit_limit = True
                    break
            has_more = hit_limit and len(self._buffer) > 0 and int(next_cursor) < self._cursor
            return events, next_cursor, has_more

    def _evict_expired(self) -> None:
        now = time.time()
        while self._buffer and (now - self._buffer[0]["_ts"]) > self._ttl_seconds:
            self._buffer.popleft()
            self._stats["total_evicted"] += 1

    async def get_stats(self) -> dict:
        async with self._lock:
            self._evict_expired()
            return {
                "buffer_size": len(self._buffer),
                "buffer_max_size": self._max_size,
                "buffer_usage_percent": round(
                    len(self._buffer) / self._max_size * 100, 1
                )
                if self._max_size
                else 0,
                "total_received": self._stats["total_received"],
                "total_evicted": self._stats["total_evicted"],
                "protocols": {
                    "http": self._stats["http"],
                    "grpc": self._stats["grpc"],
                    "dns": self._stats["dns"],
                },
            }
