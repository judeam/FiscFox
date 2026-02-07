"""Thread-safe TTL cache for async functions.

Provides caching with time-based expiration for expensive calculations
like dashboard statistics and tax computations.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TTLCache:
    """Thread-safe TTL cache for async functions.

    Caches results with time-based expiration. Thread-safe through asyncio Lock.

    Example:
        cache = TTLCache(ttl_seconds=300)  # 5 minute cache

        async def get_stats(year: int):
            return await cache.get_or_compute(
                f"stats_{year}",
                lambda: expensive_computation(year)
            )
    """

    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache with TTL.

        Args:
            ttl_seconds: Time-to-live in seconds (default 5 minutes)
        """
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._lock = asyncio.Lock()
        self.ttl = timedelta(seconds=ttl_seconds)
        self._ttl_seconds = ttl_seconds

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[T]],
    ) -> T:
        """Get cached value or compute and cache if missing/expired.

        Args:
            key: Cache key
            compute_fn: Async function to compute value if cache miss

        Returns:
            Cached or computed value
        """
        # Check cache (no lock needed for read)
        if key in self._cache:
            cached_time, value = self._cache[key]
            if datetime.now() - cached_time < self.ttl:
                logger.debug(f"Cache hit for key: {key}")
                return value

        # Compute new value
        logger.debug(f"Cache miss for key: {key}, computing...")
        result = await compute_fn()

        # Store in cache (with lock for thread safety)
        async with self._lock:
            self._cache[key] = (datetime.now(), result)

        return result

    async def get(self, key: str) -> T | None:
        """Get cached value if present and not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if missing/expired
        """
        if key in self._cache:
            cached_time, value = self._cache[key]
            if datetime.now() - cached_time < self.ttl:
                return value
        return None

    async def set(self, key: str, value: T) -> None:
        """Set a cache value.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            self._cache[key] = (datetime.now(), value)

    async def invalidate(self, pattern: str = "*") -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match. Use "*" for all, or substring match.

        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            if pattern == "*":
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"Invalidated all {count} cache entries")
                return count

            keys_to_remove = [k for k in self._cache if pattern in k]
            for k in keys_to_remove:
                del self._cache[k]
            if keys_to_remove:
                logger.info(f"Invalidated {len(keys_to_remove)} cache entries matching '{pattern}'")
            return len(keys_to_remove)

    async def invalidate_key(self, key: str) -> bool:
        """Invalidate a specific cache key.

        Args:
            key: Exact key to invalidate

        Returns:
            True if key was present and removed
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Invalidated cache key: {key}")
                return True
            return False

    def size(self) -> int:
        """Get number of entries in cache."""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache stats (size, ttl, keys)
        """
        now = datetime.now()
        valid_entries = sum(
            1 for cached_time, _ in self._cache.values()
            if now - cached_time < self.ttl
        )
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
            "ttl_seconds": self._ttl_seconds,
            "keys": list(self._cache.keys()),
        }


# =============================================================================
# Global Cache Instances
# =============================================================================

# Dashboard statistics cache (5 minute TTL)
dashboard_cache = TTLCache(ttl_seconds=300)

# Tax prediction cache (15 minute TTL - less volatile)
prediction_cache = TTLCache(ttl_seconds=900)


async def invalidate_financial_caches() -> None:
    """Invalidate all financial data caches.

    Call this when invoices or expenses are created/updated/deleted.
    """
    await dashboard_cache.invalidate("*")
    await prediction_cache.invalidate("*")
    logger.info("All financial caches invalidated")
