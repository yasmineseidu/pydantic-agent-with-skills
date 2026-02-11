"""Token-bucket rate limiter using Redis counters."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from src.cache.client import RedisManager

logger = logging.getLogger(__name__)


class RateLimitResult(BaseModel):
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed.
        remaining: Number of remaining requests in the window.
        reset_at: When the rate limit window resets.
        limit: The maximum number of requests allowed.
    """

    allowed: bool
    remaining: int = Field(ge=0)
    reset_at: datetime
    limit: int = Field(gt=0)


class RateLimiter:
    """Token-bucket rate limiter using Redis counters.

    Uses Redis INCR + EXPIRE for atomic counter increment.
    When Redis unavailable: returns allowed=True (degraded mode, logs warning).
    Key format: {prefix}rate:{team_id}:{resource}

    Attributes:
        _redis_manager: RedisManager instance for Redis operations.
    """

    def __init__(self, redis_manager: RedisManager) -> None:
        """Initialize the rate limiter.

        Args:
            redis_manager: RedisManager instance for Redis operations.
        """
        self._redis_manager: RedisManager = redis_manager

    async def check_rate_limit(
        self,
        team_id: UUID,
        resource: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check if request is within rate limit.

        Algorithm:
        1. INCR the counter key
        2. If result == 1 (first request), SET EXPIRE to window_seconds
        3. If count > limit, deny

        When Redis unavailable: returns allowed=True (degraded mode).

        Args:
            team_id: Team UUID for rate limit scoping.
            resource: Resource name (e.g., "chat", "api", "search").
            limit: Maximum requests per window.
            window_seconds: Window duration in seconds.

        Returns:
            RateLimitResult with allowed, remaining, reset_at, limit.
        """
        if not self._redis_manager.available:
            logger.warning(
                f"rate_limit_degraded_mode: team_id={team_id}, "
                f"resource={resource}, redis_unavailable=True"
            )
            now = datetime.now(timezone.utc)
            reset_at = now + timedelta(seconds=window_seconds)
            return RateLimitResult(allowed=True, remaining=limit, reset_at=reset_at, limit=limit)

        try:
            client = await self._redis_manager.get_client()
            if client is None:
                logger.warning(
                    f"rate_limit_degraded_mode: team_id={team_id}, "
                    f"resource={resource}, client_none=True"
                )
                now = datetime.now(timezone.utc)
                reset_at = now + timedelta(seconds=window_seconds)
                return RateLimitResult(
                    allowed=True, remaining=limit, reset_at=reset_at, limit=limit
                )

            key: str = self._key(team_id, resource)

            # Use pipeline to make INCR + EXPIRE atomic (prevents orphaned keys
            # if the process crashes between the two commands).
            async with client.pipeline(transaction=True) as pipe:  # type: ignore[union-attr]
                pipe.incr(key)  # type: ignore[union-attr]
                pipe.expire(key, window_seconds)  # type: ignore[union-attr]
                results = await pipe.execute()  # type: ignore[union-attr]
            count: int = results[0]

            # Check TTL to determine reset time
            ttl: int = await client.ttl(key)  # type: ignore[misc, union-attr]
            if ttl == -1:
                # No TTL set (shouldn't happen, but handle gracefully)
                await client.expire(key, window_seconds)  # type: ignore[misc, union-attr]
                ttl = window_seconds

            now = datetime.now(timezone.utc)
            reset_at = now + timedelta(seconds=max(ttl, 0))

            allowed = count <= limit
            remaining = max(0, limit - count)

            logger.info(
                f"rate_limit_check: team_id={team_id}, resource={resource}, "
                f"count={count}, limit={limit}, allowed={allowed}, "
                f"remaining={remaining}, ttl={ttl}"
            )

            return RateLimitResult(
                allowed=allowed, remaining=remaining, reset_at=reset_at, limit=limit
            )

        except Exception as e:
            logger.warning(
                f"rate_limit_check_error: team_id={team_id}, resource={resource}, error={str(e)}"
            )
            # Degraded mode on error
            now = datetime.now(timezone.utc)
            reset_at = now + timedelta(seconds=window_seconds)
            return RateLimitResult(allowed=True, remaining=limit, reset_at=reset_at, limit=limit)

    def _key(self, team_id: UUID, resource: str) -> str:
        """Build Redis key for rate limit counter.

        Args:
            team_id: Team UUID.
            resource: Resource name.

        Returns:
            Redis key with prefix.
        """
        return f"{self._redis_manager.key_prefix}rate:{team_id}:{resource}"
