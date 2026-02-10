"""Integration tests for the Redis cache layer modules."""

import pytest
from uuid import uuid4

from src.cache.client import RedisManager
from src.cache.hot_cache import HotMemoryCache
from src.cache.working_memory import WorkingMemoryCache
from src.cache.embedding_cache import EmbeddingCache
from src.cache.rate_limiter import RateLimiter


class TestRedisManagerIntegration:
    """Integration tests for RedisManager."""

    @pytest.mark.asyncio
    async def test_redis_manager_with_fakeredis_is_available(
        self, redis_manager: RedisManager
    ) -> None:
        """RedisManager with injected FakeRedis reports available=True."""
        assert redis_manager.available is True
        client = await redis_manager.get_client()
        assert client is not None

    @pytest.mark.asyncio
    async def test_redis_manager_with_none_url_is_unavailable(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """RedisManager with None URL reports available=False."""
        assert unavailable_redis_manager.available is False
        client = await unavailable_redis_manager.get_client()
        assert client is None

    @pytest.mark.asyncio
    async def test_health_check_returns_status_dict(self, redis_manager: RedisManager) -> None:
        """health_check() returns a dict with status and latency_ms keys."""
        result = await redis_manager.health_check()
        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "ok"
        assert "latency_ms" in result


class TestHotMemoryCacheLifecycle:
    """Full lifecycle test for HotMemoryCache."""

    @pytest.mark.asyncio
    async def test_warm_get_invalidate_lifecycle(self, redis_manager: RedisManager) -> None:
        """warm_cache -> get_memories -> invalidate -> get_memories returns None."""
        cache = HotMemoryCache(redis_manager)
        agent_id = uuid4()
        user_id = uuid4()
        memories = [
            {"final_score": 0.9, "memory": {"content": "Test memory 1"}},
            {"final_score": 0.7, "memory": {"content": "Test memory 2"}},
        ]

        # Warm
        await cache.warm_cache(agent_id, user_id, memories)

        # Get
        result = await cache.get_memories(agent_id, user_id)
        assert result is not None
        assert len(result) == 2

        # Invalidate
        await cache.invalidate(agent_id, user_id)

        # Get after invalidation
        result_after = await cache.get_memories(agent_id, user_id)
        assert result_after is None


class TestWorkingMemoryCacheLifecycle:
    """Full lifecycle test for WorkingMemoryCache."""

    @pytest.mark.asyncio
    async def test_set_context_append_turns_get_turns_lifecycle(
        self, redis_manager: RedisManager
    ) -> None:
        """set_context -> append_turn x3 -> get_turns returns all turns in order."""
        cache = WorkingMemoryCache(redis_manager)
        conv_id = uuid4()

        # Set context
        context = {"topic": "testing", "mode": "integration"}
        await cache.set_context(conv_id, context)

        # Append turns
        await cache.append_turn(conv_id, "user", "Hello")
        await cache.append_turn(conv_id, "assistant", "Hi there")
        await cache.append_turn(conv_id, "user", "How are you?")

        # Get turns
        turns = await cache.get_turns(conv_id)
        assert len(turns) == 3
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"
        assert turns[2]["content"] == "How are you?"

        # Get context
        ctx = await cache.get_context(conv_id)
        assert ctx is not None
        assert ctx["topic"] == "testing"

        # Delete
        await cache.delete(conv_id)
        assert await cache.get_context(conv_id) is None


class TestEmbeddingCacheLifecycle:
    """Full lifecycle test for EmbeddingCache."""

    @pytest.mark.asyncio
    async def test_store_get_different_text_miss_lifecycle(
        self, redis_manager: RedisManager
    ) -> None:
        """store -> get (hit) -> get different text (miss)."""
        cache = EmbeddingCache(redis_manager)

        # Store
        await cache.store_embedding("hello world", [0.1, 0.2, 0.3])

        # Hit
        result = await cache.get_embedding("hello world")
        assert result == [0.1, 0.2, 0.3]

        # Miss for different text
        result_miss = await cache.get_embedding("goodbye world")
        assert result_miss is None


class TestRateLimiterLifecycle:
    """Full lifecycle test for RateLimiter."""

    @pytest.mark.asyncio
    async def test_allow_up_to_limit_then_deny(self, redis_manager: RedisManager) -> None:
        """Allow requests up to limit, then deny."""
        limiter = RateLimiter(redis_manager)
        team_id = uuid4()

        # Allow 3 requests
        for _ in range(3):
            result = await limiter.check_rate_limit(team_id, "test", limit=3, window_seconds=60)
            assert result.allowed is True

        # 4th request should be denied
        result = await limiter.check_rate_limit(team_id, "test", limit=3, window_seconds=60)
        assert result.allowed is False
        assert result.remaining == 0


class TestCrossModuleIntegration:
    """Tests for multiple cache modules sharing one RedisManager."""

    @pytest.mark.asyncio
    async def test_all_caches_share_same_redis_manager(self, redis_manager: RedisManager) -> None:
        """All cache modules can operate on the same RedisManager without interference."""
        hot = HotMemoryCache(redis_manager)
        working = WorkingMemoryCache(redis_manager)
        embed = EmbeddingCache(redis_manager)
        limiter = RateLimiter(redis_manager)

        agent_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()
        team_id = uuid4()

        # Use all caches
        await hot.warm_cache(agent_id, user_id, [{"final_score": 0.5, "data": "hot"}])
        await working.set_context(conv_id, {"key": "value"})
        await embed.store_embedding("test text", [1.0, 2.0])
        result = await limiter.check_rate_limit(team_id, "api", limit=10, window_seconds=60)

        # Verify each cache independently
        hot_result = await hot.get_memories(agent_id, user_id)
        assert hot_result is not None
        assert len(hot_result) == 1

        working_result = await working.get_context(conv_id)
        assert working_result is not None
        assert working_result["key"] == "value"

        embed_result = await embed.get_embedding("test text")
        assert embed_result == [1.0, 2.0]

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_cache_modules_handle_close_gracefully(self, redis_manager: RedisManager) -> None:
        """Cache modules handle RedisManager.close() gracefully."""
        hot = HotMemoryCache(redis_manager)
        embed = EmbeddingCache(redis_manager)

        # Store some data
        agent_id = uuid4()
        user_id = uuid4()
        await hot.warm_cache(agent_id, user_id, [{"final_score": 0.8, "data": "test"}])
        await embed.store_embedding("text", [0.1])

        # Close the manager
        await redis_manager.close()

        # After close, manager should report unavailable
        assert redis_manager.available is False

        # Operations after close should fail gracefully (return None, not raise)
        hot_result = await hot.get_memories(agent_id, user_id)
        assert hot_result is None

        embed_result = await embed.get_embedding("text")
        assert embed_result is None

    @pytest.mark.asyncio
    async def test_feature_flag_gates_initialization(self) -> None:
        """enable_redis_cache=False means RedisManager reports unavailable."""
        # When redis_url is None (feature flag off), manager is unavailable
        manager = RedisManager(redis_url=None, key_prefix="ska:")
        assert manager.available is False

        hot = HotMemoryCache(manager)
        result = await hot.get_memories(uuid4(), uuid4())
        assert result is None  # Graceful degradation
