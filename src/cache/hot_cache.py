"""L1 hot cache for frequently-accessed memories."""

import json
import logging
from typing import Any, Optional
from uuid import UUID

from src.cache.client import RedisManager

logger = logging.getLogger(__name__)

# Hot cache TTL: 15 minutes
_HOT_CACHE_TTL: int = 900


class HotMemoryCache:
    """L1 hot cache for frequently-accessed memories using Redis ZSET.

    Uses Redis sorted sets where score = final_score from 5-signal retrieval.
    TTL: 15 minutes, refreshed on warm_cache.
    Key format: {prefix}hot:{agent_id}:{user_id}

    Attributes:
        _redis_manager: Redis connection manager.
    """

    def __init__(self, redis_manager: RedisManager) -> None:
        """Initialize HotMemoryCache.

        Args:
            redis_manager: Redis connection manager for cache operations.
        """
        self._redis_manager: RedisManager = redis_manager

    async def get_memories(
        self, agent_id: UUID, user_id: UUID, limit: int = 20
    ) -> Optional[list[dict[str, Any]]]:
        """Get pre-warmed memories from Redis.

        Returns None on cache miss (caller falls through to PostgreSQL).
        Returns None when Redis unavailable (graceful degradation).

        Args:
            agent_id: Agent UUID for key scoping.
            user_id: User UUID for key scoping.
            limit: Maximum number of memories to return.

        Returns:
            List of memory dicts sorted by score DESC, or None on miss/unavailable.
        """
        if not self._redis_manager.available:
            return None

        client = await self._redis_manager.get_client()
        if client is None:
            return None

        key = self._key(agent_id, user_id)

        try:
            # ZREVRANGE returns highest-scored members first
            members = await client.zrevrange(key, 0, limit - 1)  # type: ignore[union-attr]

            if not members:
                logger.info(f"hot_cache_miss: agent_id={agent_id}, user_id={user_id}, key={key}")
                return None

            # Deserialize JSON members to dict objects
            memories: list[dict[str, Any]] = []
            for member in members:
                try:
                    memory_dict = json.loads(member)
                    memories.append(memory_dict)
                except json.JSONDecodeError as e:
                    logger.warning(f"hot_cache_deserialize_error: key={key}, error={str(e)}")
                    continue

            logger.info(
                f"hot_cache_hit: agent_id={agent_id}, user_id={user_id}, "
                f"count={len(memories)}, key={key}"
            )
            return memories

        except Exception as e:
            logger.warning(
                f"hot_cache_get_error: agent_id={agent_id}, user_id={user_id}, error={str(e)}"
            )
            return None

    async def warm_cache(
        self, agent_id: UUID, user_id: UUID, memories: list[dict[str, Any]]
    ) -> None:
        """Populate hot cache after a PostgreSQL retrieval.

        Stores each memory as a JSON member in a ZSET with score = final_score.
        Sets TTL to 15 minutes. Previous cache content is overwritten.

        Args:
            agent_id: Agent UUID for key scoping.
            user_id: User UUID for key scoping.
            memories: List of dicts with at least "final_score" and "memory" keys.
        """
        if not self._redis_manager.available:
            return

        client = await self._redis_manager.get_client()
        if client is None:
            return

        if not memories:
            logger.info(
                f"hot_cache_warm_skip: agent_id={agent_id}, user_id={user_id}, "
                f"reason=empty_memories"
            )
            return

        key = self._key(agent_id, user_id)

        try:
            # Use pipeline for atomic operation: DEL + ZADD + EXPIRE
            async with client.pipeline(transaction=True) as pipe:  # type: ignore[union-attr]
                # Clear existing cache
                await pipe.delete(key)

                # Add each memory with its final_score as the ZSET score
                for memory_dict in memories:
                    score = memory_dict.get("final_score", 0.0)
                    member = json.dumps(memory_dict)
                    await pipe.zadd(key, {member: score})  # type: ignore[arg-type]

                # Set TTL
                await pipe.expire(key, _HOT_CACHE_TTL)

                # Execute pipeline
                await pipe.execute()

            logger.info(
                f"hot_cache_warmed: agent_id={agent_id}, user_id={user_id}, "
                f"count={len(memories)}, ttl={_HOT_CACHE_TTL}s, key={key}"
            )

        except Exception as e:
            logger.warning(
                f"hot_cache_warm_error: agent_id={agent_id}, user_id={user_id}, error={str(e)}"
            )

    async def invalidate(self, agent_id: UUID, user_id: Optional[UUID] = None) -> None:
        """Clear hot cache for an agent.

        When user_id is provided, clears only that user's cache.
        When user_id is None, clears cache for all users of the agent
        using pattern-based key scan (SCAN + DELETE).

        Args:
            agent_id: Agent UUID whose cache to clear.
            user_id: Optional user UUID. None clears all users.
        """
        if not self._redis_manager.available:
            return

        client = await self._redis_manager.get_client()
        if client is None:
            return

        try:
            if user_id is not None:
                # Clear single user's cache
                key = self._key(agent_id, user_id)
                deleted = await client.delete(key)  # type: ignore[union-attr]
                logger.info(
                    f"hot_cache_invalidated: agent_id={agent_id}, user_id={user_id}, "
                    f"deleted={deleted}, key={key}"
                )
            else:
                # Clear all users for this agent using SCAN + DELETE
                pattern = f"{self._redis_manager.key_prefix}hot:{agent_id}:*"
                deleted_count = 0

                # Use SCAN to find matching keys
                cursor = 0
                while True:
                    cursor, keys = await client.scan(  # type: ignore[union-attr, misc]
                        cursor, match=pattern, count=100
                    )
                    if keys:
                        deleted_count += await client.delete(*keys)  # type: ignore[union-attr]
                    if cursor == 0:
                        break

                logger.info(
                    f"hot_cache_invalidated_all: agent_id={agent_id}, "
                    f"deleted={deleted_count}, pattern={pattern}"
                )

        except Exception as e:
            logger.warning(
                f"hot_cache_invalidate_error: agent_id={agent_id}, "
                f"user_id={user_id}, error={str(e)}"
            )

    def _key(self, agent_id: UUID, user_id: UUID) -> str:
        """Build Redis key for hot cache.

        Args:
            agent_id: Agent UUID.
            user_id: User UUID.

        Returns:
            Redis key string like "ska:hot:{agent_id}:{user_id}".
        """
        return f"{self._redis_manager.key_prefix}hot:{agent_id}:{user_id}"
