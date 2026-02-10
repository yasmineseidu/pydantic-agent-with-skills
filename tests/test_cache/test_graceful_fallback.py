"""Tests for graceful degradation when Redis is unavailable."""

import logging
from uuid import uuid4

import pytest

from src.cache.embedding_cache import EmbeddingCache
from src.cache.hot_cache import HotMemoryCache
from src.cache.rate_limiter import RateLimiter
from src.cache.working_memory import WorkingMemoryCache


class TestHotMemoryCacheFallback:
    """HotMemoryCache graceful degradation when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_get_memories_returns_none(self, unavailable_redis_manager):
        """get_memories returns None when Redis unavailable."""
        cache = HotMemoryCache(unavailable_redis_manager)
        result = await cache.get_memories(uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_warm_cache_is_silent_noop(self, unavailable_redis_manager):
        """warm_cache does nothing when Redis unavailable (no error)."""
        cache = HotMemoryCache(unavailable_redis_manager)
        # Should not raise
        await cache.warm_cache(uuid4(), uuid4(), [{"final_score": 0.9, "data": "test"}])

    @pytest.mark.asyncio
    async def test_invalidate_is_silent_noop_with_user_id(self, unavailable_redis_manager):
        """invalidate does nothing when Redis unavailable (no error) - with user_id."""
        cache = HotMemoryCache(unavailable_redis_manager)
        # Should not raise - with user_id
        await cache.invalidate(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_invalidate_is_silent_noop_without_user_id(self, unavailable_redis_manager):
        """invalidate does nothing when Redis unavailable (no error) - pattern scan path."""
        cache = HotMemoryCache(unavailable_redis_manager)
        # Should not raise - without user_id (pattern scan path)
        await cache.invalidate(uuid4())


class TestWorkingMemoryCacheFallback:
    """WorkingMemoryCache graceful degradation when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_get_context_returns_none(self, unavailable_redis_manager):
        """get_context returns None when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        result = await cache.get_context(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_set_context_is_silent_noop(self, unavailable_redis_manager):
        """set_context does nothing when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        await cache.set_context(uuid4(), {"key": "value"})

    @pytest.mark.asyncio
    async def test_append_turn_is_silent_noop(self, unavailable_redis_manager):
        """append_turn does nothing when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        await cache.append_turn(uuid4(), "user", "test")

    @pytest.mark.asyncio
    async def test_get_turns_returns_empty_list(self, unavailable_redis_manager):
        """get_turns returns empty list when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        result = await cache.get_turns(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_delete_is_silent_noop(self, unavailable_redis_manager):
        """delete does nothing when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        await cache.delete(uuid4())


class TestEmbeddingCacheFallback:
    """EmbeddingCache graceful degradation when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_get_embedding_returns_none(self, unavailable_redis_manager):
        """get_embedding returns None when Redis unavailable."""
        cache = EmbeddingCache(unavailable_redis_manager)
        result = await cache.get_embedding("test text")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_embedding_is_silent_noop(self, unavailable_redis_manager):
        """store_embedding does nothing when Redis unavailable."""
        cache = EmbeddingCache(unavailable_redis_manager)
        await cache.store_embedding("test text", [0.1, 0.2, 0.3])


class TestRateLimiterFallback:
    """RateLimiter graceful degradation when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_allowed_true(self, unavailable_redis_manager):
        """check_rate_limit returns allowed=True when Redis unavailable (degraded mode)."""
        limiter = RateLimiter(unavailable_redis_manager)
        result = await limiter.check_rate_limit(uuid4(), "api", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 10
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_check_rate_limit_degraded_mode_logs_warning(
        self, unavailable_redis_manager, caplog
    ):
        """check_rate_limit logs a warning in degraded mode."""
        with caplog.at_level(logging.WARNING):
            limiter = RateLimiter(unavailable_redis_manager)
            await limiter.check_rate_limit(uuid4(), "api", limit=5, window_seconds=30)
        assert "rate_limit_degraded_mode" in caplog.text


class TestNoExceptionsPropagation:
    """Ensures no exceptions propagate from any cache module when Redis is down."""

    @pytest.mark.asyncio
    async def test_all_operations_are_exception_free(self, unavailable_redis_manager):
        """Every cache operation with unavailable Redis completes without raising."""
        hot = HotMemoryCache(unavailable_redis_manager)
        working = WorkingMemoryCache(unavailable_redis_manager)
        embed = EmbeddingCache(unavailable_redis_manager)
        limiter = RateLimiter(unavailable_redis_manager)

        agent_id = uuid4()
        user_id = uuid4()
        conv_id = uuid4()
        team_id = uuid4()

        # None of these should raise
        await hot.get_memories(agent_id, user_id)
        await hot.warm_cache(agent_id, user_id, [{"score": 1.0}])
        await hot.invalidate(agent_id, user_id)
        await hot.invalidate(agent_id)

        await working.get_context(conv_id)
        await working.set_context(conv_id, {"data": "test"})
        await working.append_turn(conv_id, "user", "hi")
        await working.get_turns(conv_id)
        await working.delete(conv_id)

        await embed.get_embedding("text")
        await embed.store_embedding("text", [0.1])

        await limiter.check_rate_limit(team_id, "api", limit=10, window_seconds=60)
