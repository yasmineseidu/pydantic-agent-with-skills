"""Unit tests for HotMemoryCache in src/cache/hot_cache.py."""

import json
from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis

from src.cache.client import RedisManager
from src.cache.hot_cache import HotMemoryCache


class TestWarmCache:
    """Tests for HotMemoryCache.warm_cache."""

    @pytest.mark.asyncio
    async def test_warm_cache_stores_memories_in_zset(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that warm_cache stores memories in Redis ZSET."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [
            {"memory": "User prefers dark mode", "final_score": 0.9},
            {"memory": "User lives in SF", "final_score": 0.8},
        ]

        await cache.warm_cache(agent_id, user_id, memories)

        # Verify ZSET exists
        key = f"test:hot:{agent_id}:{user_id}"
        members = await fake_redis.zrevrange(key, 0, -1)
        assert len(members) == 2

        # Verify scores are correct
        deserialized = [json.loads(m) for m in members]
        assert deserialized[0]["final_score"] == 0.9
        assert deserialized[1]["final_score"] == 0.8

    @pytest.mark.asyncio
    async def test_warm_cache_sets_ttl(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that warm_cache sets TTL to 900 seconds."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [{"memory": "test", "final_score": 0.7}]

        await cache.warm_cache(agent_id, user_id, memories)

        key = f"test:hot:{agent_id}:{user_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl == 900

    @pytest.mark.asyncio
    async def test_warm_cache_overwrites_previous_content(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that warm_cache overwrites previous cache content."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        # First warm
        memories_v1 = [{"memory": "old data", "final_score": 0.5}]
        await cache.warm_cache(agent_id, user_id, memories_v1)

        # Second warm (overwrite)
        memories_v2 = [
            {"memory": "new data 1", "final_score": 0.9},
            {"memory": "new data 2", "final_score": 0.8},
        ]
        await cache.warm_cache(agent_id, user_id, memories_v2)

        # Verify only v2 data exists
        key = f"test:hot:{agent_id}:{user_id}"
        members = await fake_redis.zrevrange(key, 0, -1)
        assert len(members) == 2
        deserialized = [json.loads(m) for m in members]
        assert deserialized[0]["memory"] == "new data 1"
        assert deserialized[1]["memory"] == "new data 2"

    @pytest.mark.asyncio
    async def test_warm_cache_empty_list_is_noop(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that warm_cache with empty list is a no-op (no Redis write)."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        await cache.warm_cache(agent_id, user_id, [])

        # Verify no key was created
        key = f"test:hot:{agent_id}:{user_id}"
        exists = await fake_redis.exists(key)
        assert exists == 0

    @pytest.mark.asyncio
    async def test_warm_cache_with_unavailable_redis_returns_gracefully(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """Test that warm_cache returns gracefully when Redis is unavailable."""
        cache = HotMemoryCache(unavailable_redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [{"memory": "test", "final_score": 0.7}]

        # Should not raise, just return
        await cache.warm_cache(agent_id, user_id, memories)

    @pytest.mark.asyncio
    async def test_warm_cache_multiple_users_independent(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that multiple warm_cache calls with different users are independent."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        memories_1 = [{"memory": "user1 data", "final_score": 0.9}]
        memories_2 = [{"memory": "user2 data", "final_score": 0.8}]

        await cache.warm_cache(agent_id, user_id_1, memories_1)
        await cache.warm_cache(agent_id, user_id_2, memories_2)

        # Verify both keys exist independently
        key_1 = f"test:hot:{agent_id}:{user_id_1}"
        key_2 = f"test:hot:{agent_id}:{user_id_2}"

        members_1 = await fake_redis.zrevrange(key_1, 0, -1)
        members_2 = await fake_redis.zrevrange(key_2, 0, -1)

        assert len(members_1) == 1
        assert len(members_2) == 1
        assert json.loads(members_1[0])["memory"] == "user1 data"
        assert json.loads(members_2[0])["memory"] == "user2 data"


class TestGetMemories:
    """Tests for HotMemoryCache.get_memories."""

    @pytest.mark.asyncio
    async def test_get_memories_returns_cached_memories_sorted_by_score_desc(
        self, redis_manager: RedisManager
    ) -> None:
        """Test that get_memories returns cached memories sorted by score DESC."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [
            {"memory": "high score", "final_score": 0.9},
            {"memory": "medium score", "final_score": 0.7},
            {"memory": "low score", "final_score": 0.5},
        ]

        await cache.warm_cache(agent_id, user_id, memories)

        result = await cache.get_memories(agent_id, user_id)

        assert result is not None
        assert len(result) == 3
        assert result[0]["final_score"] == 0.9
        assert result[1]["final_score"] == 0.7
        assert result[2]["final_score"] == 0.5

    @pytest.mark.asyncio
    async def test_get_memories_returns_none_on_cache_miss(
        self, redis_manager: RedisManager
    ) -> None:
        """Test that get_memories returns None on cache miss (empty key)."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        # No warm_cache call, so key doesn't exist
        result = await cache.get_memories(agent_id, user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_memories_respects_limit_parameter(self, redis_manager: RedisManager) -> None:
        """Test that get_memories respects limit parameter."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [
            {"memory": "mem1", "final_score": 0.9},
            {"memory": "mem2", "final_score": 0.8},
            {"memory": "mem3", "final_score": 0.7},
            {"memory": "mem4", "final_score": 0.6},
        ]

        await cache.warm_cache(agent_id, user_id, memories)

        result = await cache.get_memories(agent_id, user_id, limit=2)

        assert result is not None
        assert len(result) == 2
        assert result[0]["final_score"] == 0.9
        assert result[1]["final_score"] == 0.8

    @pytest.mark.asyncio
    async def test_get_memories_with_limit_one_returns_top_scored_memory(
        self, redis_manager: RedisManager
    ) -> None:
        """Test that get_memories with limit=1 returns only top-scored memory."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [
            {"memory": "low", "final_score": 0.5},
            {"memory": "high", "final_score": 0.9},
            {"memory": "medium", "final_score": 0.7},
        ]

        await cache.warm_cache(agent_id, user_id, memories)

        result = await cache.get_memories(agent_id, user_id, limit=1)

        assert result is not None
        assert len(result) == 1
        assert result[0]["final_score"] == 0.9
        assert result[0]["memory"] == "high"

    @pytest.mark.asyncio
    async def test_get_memories_returns_none_when_redis_unavailable(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """Test that get_memories returns None when Redis is unavailable."""
        cache = HotMemoryCache(unavailable_redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        result = await cache.get_memories(agent_id, user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_memories_serialization_round_trip_preserves_fields(
        self, redis_manager: RedisManager
    ) -> None:
        """Test serialization/deserialization round-trip preserves all fields."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [
            {
                "memory": "Complex memory",
                "final_score": 0.85,
                "importance": 7,
                "type": "semantic",
                "metadata": {"key": "value"},
            }
        ]

        await cache.warm_cache(agent_id, user_id, memories)
        result = await cache.get_memories(agent_id, user_id)

        assert result is not None
        assert len(result) == 1
        assert result[0]["memory"] == "Complex memory"
        assert result[0]["final_score"] == 0.85
        assert result[0]["importance"] == 7
        assert result[0]["type"] == "semantic"
        assert result[0]["metadata"] == {"key": "value"}


class TestInvalidate:
    """Tests for HotMemoryCache.invalidate."""

    @pytest.mark.asyncio
    async def test_invalidate_removes_cached_memories_for_specific_user(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that invalidate removes cached memories for specific agent+user."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        memories = [{"memory": "test", "final_score": 0.7}]
        await cache.warm_cache(agent_id, user_id, memories)

        # Verify key exists
        key = f"test:hot:{agent_id}:{user_id}"
        exists_before = await fake_redis.exists(key)
        assert exists_before == 1

        # Invalidate
        await cache.invalidate(agent_id, user_id)

        # Verify key is deleted
        exists_after = await fake_redis.exists(key)
        assert exists_after == 0

    @pytest.mark.asyncio
    async def test_invalidate_with_none_user_id_clears_all_users(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Test that invalidate with user_id=None clears all users for agent (uses SCAN pattern)."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id_1 = uuid4()
        user_id_2 = uuid4()
        user_id_3 = uuid4()

        # Warm cache for 3 different users
        await cache.warm_cache(agent_id, user_id_1, [{"memory": "u1", "final_score": 0.7}])
        await cache.warm_cache(agent_id, user_id_2, [{"memory": "u2", "final_score": 0.8}])
        await cache.warm_cache(agent_id, user_id_3, [{"memory": "u3", "final_score": 0.9}])

        # Invalidate all users for this agent
        await cache.invalidate(agent_id, user_id=None)

        # Verify all keys are deleted
        key_1 = f"test:hot:{agent_id}:{user_id_1}"
        key_2 = f"test:hot:{agent_id}:{user_id_2}"
        key_3 = f"test:hot:{agent_id}:{user_id_3}"

        assert await fake_redis.exists(key_1) == 0
        assert await fake_redis.exists(key_2) == 0
        assert await fake_redis.exists(key_3) == 0

    @pytest.mark.asyncio
    async def test_invalidate_with_unavailable_redis_returns_gracefully(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """Test that invalidate returns gracefully when Redis is unavailable."""
        cache = HotMemoryCache(unavailable_redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        # Should not raise, just return
        await cache.invalidate(agent_id, user_id)
        await cache.invalidate(agent_id, user_id=None)


class TestKeyFormat:
    """Tests for HotMemoryCache._key."""

    @pytest.mark.asyncio
    async def test_cache_key_format(self, redis_manager: RedisManager, key_prefix: str) -> None:
        """Test cache key format is {prefix}hot:{agent_id}:{user_id}."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()

        key = cache._key(agent_id, user_id)

        assert key == f"{key_prefix}hot:{agent_id}:{user_id}"
