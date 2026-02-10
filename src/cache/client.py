"""Async Redis connection manager with graceful fallback."""

import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis connection pool with graceful fallback.

    Manages a Redis connection pool. When Redis is unavailable or not
    configured, all operations return safe defaults (None, False).

    Attributes:
        _redis_url: Redis connection URL, or None if not configured.
        _key_prefix: Namespace prefix for all Redis keys.
        _client: Cached async Redis client instance.
        _available: Whether Redis is currently reachable.
    """

    def __init__(self, redis_url: Optional[str] = None, key_prefix: str = "ska:") -> None:
        """Initialize RedisManager.

        Args:
            redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
                When None, Redis is disabled and all operations return safe defaults.
            key_prefix: Namespace prefix for all Redis keys.
        """
        self._redis_url: Optional[str] = redis_url
        self._key_prefix: str = key_prefix
        self._client: Optional[aioredis.Redis] = None
        self._available: bool = False

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Get an async Redis client, creating the connection pool if needed.

        Returns:
            Async Redis client, or None if Redis is unavailable or not configured.
        """
        if self._redis_url is None:
            return None

        if self._client is not None and self._available:
            return self._client

        try:
            self._client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5.0,
                socket_timeout=5.0,
                retry_on_timeout=True,
            )
            await self._client.ping()  # type: ignore[misc, union-attr]
            self._available = True
            logger.info(f"redis_connected: url={self._redis_url[:20]}...")
            return self._client
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as e:
            logger.warning(f"redis_unavailable: error={str(e)}")
            self._available = False
            self._client = None
            return None

    @property
    def available(self) -> bool:
        """Check if Redis is currently available.

        Returns:
            True if Redis is connected and responding, False otherwise.
        """
        return self._available and self._redis_url is not None

    @property
    def key_prefix(self) -> str:
        """Get the Redis key namespace prefix.

        Returns:
            The key prefix string (e.g. "ska:").
        """
        return self._key_prefix

    async def close(self) -> None:
        """Close the Redis connection pool gracefully."""
        if self._client is not None:
            try:
                await self._client.aclose()
                logger.info("redis_closed: pool closed gracefully")
            except Exception as e:
                logger.warning(f"redis_close_error: error={str(e)}")
            finally:
                self._client = None
                self._available = False

    async def health_check(self) -> dict[str, Any]:
        """Check Redis health and measure latency.

        Returns:
            Dict with "status" ("ok" or "unavailable") and "latency_ms" (float).
        """
        if self._redis_url is None:
            return {"status": "not_configured", "latency_ms": 0.0}

        start = time.monotonic()
        try:
            client = await self.get_client()
            if client is None:
                return {"status": "unavailable", "latency_ms": 0.0}
            await client.ping()  # type: ignore[misc, union-attr]
            latency_ms = (time.monotonic() - start) * 1000.0
            return {"status": "ok", "latency_ms": round(latency_ms, 2)}
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000.0
            logger.warning(f"redis_health_check_failed: error={str(e)}")
            self._available = False
            return {"status": "unavailable", "latency_ms": round(latency_ms, 2)}
