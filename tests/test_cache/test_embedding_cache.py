"""Unit tests for EmbeddingCache Redis-backed embedding storage."""

import hashlib

import pytest
from fakeredis import FakeAsyncRedis

from src.cache.client import RedisManager
from src.cache.embedding_cache import EmbeddingCache


class TestEmbeddingCache:
    """Tests for EmbeddingCache class."""

    @pytest.mark.asyncio
    async def test_store_and_get_embedding_round_trips(self, redis_manager: RedisManager) -> None:
        """Store and retrieve a float vector - basic round trip."""
        cache = EmbeddingCache(redis_manager)
        text = "Hello world"
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        await cache.store_embedding(text, embedding)
        result = await cache.get_embedding(text)

        assert result is not None
        assert result == embedding

    @pytest.mark.asyncio
    async def test_get_embedding_returns_none_on_cache_miss(
        self, redis_manager: RedisManager
    ) -> None:
        """Get embedding returns None when text not in cache."""
        cache = EmbeddingCache(redis_manager)

        result = await cache.get_embedding("nonexistent text")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_embedding_returns_none_when_redis_unavailable(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """Get embedding returns None when Redis is unavailable."""
        cache = EmbeddingCache(unavailable_redis_manager)

        result = await cache.get_embedding("any text")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_key_is_sha256_of_normalized_text(
        self, redis_manager: RedisManager, key_prefix: str
    ) -> None:
        """Cache key uses SHA-256 of lowercased, stripped text."""
        cache = EmbeddingCache(redis_manager)
        text = "Hello World"

        # Compute expected key
        normalized = text.lower().strip()
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        expected_key = f"{key_prefix}embed:{digest}"

        # Generate actual key
        actual_key = cache._cache_key(text)

        assert actual_key == expected_key

    @pytest.mark.asyncio
    async def test_same_text_different_case_hits_same_cache_key(
        self, redis_manager: RedisManager
    ) -> None:
        """Same text with different case/whitespace produces same cache key."""
        cache = EmbeddingCache(redis_manager)
        embedding = [1.0, 2.0, 3.0]

        # Store with one case
        await cache.store_embedding("Hello World", embedding)

        # Retrieve with different case and whitespace
        result1 = await cache.get_embedding("  hello world  ")
        result2 = await cache.get_embedding("HELLO WORLD")
        result3 = await cache.get_embedding("HeLLo WoRLd")

        assert result1 == embedding
        assert result2 == embedding
        assert result3 == embedding

    @pytest.mark.asyncio
    async def test_ttl_is_set_to_86400_seconds(
        self, redis_manager: RedisManager, fake_redis: FakeAsyncRedis
    ) -> None:
        """Stored embeddings have 24h (86400s) TTL."""
        cache = EmbeddingCache(redis_manager)
        text = "test text"
        embedding = [0.5, 0.6, 0.7]

        await cache.store_embedding(text, embedding)

        # Check TTL via fake_redis directly
        key = cache._cache_key(text)
        ttl = await fake_redis.ttl(key)

        # Allow 1s tolerance for timing between setex and ttl check
        assert 86399 <= ttl <= 86400

    @pytest.mark.asyncio
    async def test_different_texts_produce_different_cache_keys(
        self, redis_manager: RedisManager
    ) -> None:
        """Different texts produce different cache keys (collision check)."""
        cache = EmbeddingCache(redis_manager)

        key1 = cache._cache_key("hello world")
        key2 = cache._cache_key("goodbye world")
        key3 = cache._cache_key("hello")

        # All keys should be unique
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    @pytest.mark.asyncio
    async def test_1536_dimensional_vector_round_trips_without_precision_loss(
        self, redis_manager: RedisManager
    ) -> None:
        """Large embedding (1536 dimensions) round-trips exactly."""
        cache = EmbeddingCache(redis_manager)
        text = "large embedding test"
        # Generate 1536-dimensional vector
        embedding = [0.1 * i for i in range(1536)]

        await cache.store_embedding(text, embedding)
        result = await cache.get_embedding(text)

        assert result is not None
        assert len(result) == 1536
        # Check exact equality (JSON round-trip should preserve floats)
        assert result == embedding

    @pytest.mark.asyncio
    async def test_store_embedding_overwrites_existing_embedding(
        self, redis_manager: RedisManager
    ) -> None:
        """Storing same text twice overwrites the first embedding."""
        cache = EmbeddingCache(redis_manager)
        text = "overwrite test"
        embedding1 = [1.0, 2.0, 3.0]
        embedding2 = [4.0, 5.0, 6.0]

        # Store first embedding
        await cache.store_embedding(text, embedding1)
        result1 = await cache.get_embedding(text)
        assert result1 == embedding1

        # Overwrite with second embedding
        await cache.store_embedding(text, embedding2)
        result2 = await cache.get_embedding(text)
        assert result2 == embedding2

    @pytest.mark.asyncio
    async def test_empty_text_produces_valid_cache_key(
        self, redis_manager: RedisManager, key_prefix: str
    ) -> None:
        """Empty text still produces valid cache key."""
        cache = EmbeddingCache(redis_manager)
        text = ""

        # Empty string normalizes to empty string
        normalized = text.lower().strip()
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        expected_key = f"{key_prefix}embed:{digest}"

        actual_key = cache._cache_key(text)

        assert actual_key == expected_key
        assert "embed:" in actual_key

    @pytest.mark.asyncio
    async def test_store_embedding_when_redis_unavailable_does_nothing(
        self, unavailable_redis_manager: RedisManager
    ) -> None:
        """Store embedding with unavailable Redis does nothing (no error)."""
        cache = EmbeddingCache(unavailable_redis_manager)
        text = "test"
        embedding = [1.0, 2.0]

        # Should not raise exception
        await cache.store_embedding(text, embedding)

        # Verify nothing was stored (get should return None)
        result = await cache.get_embedding(text)
        assert result is None

    @pytest.mark.asyncio
    async def test_normalize_lowercases_and_strips_whitespace(
        self, redis_manager: RedisManager
    ) -> None:
        """_normalize method lowercases and strips whitespace."""
        cache = EmbeddingCache(redis_manager)

        result1 = cache._normalize("  Hello World  ")
        result2 = cache._normalize("HELLO WORLD")
        result3 = cache._normalize("hello world")

        assert result1 == "hello world"
        assert result2 == "hello world"
        assert result3 == "hello world"

    @pytest.mark.asyncio
    async def test_very_long_text_round_trips_correctly(self, redis_manager: RedisManager) -> None:
        """Very long text (10000 chars) round-trips correctly."""
        cache = EmbeddingCache(redis_manager)
        # Generate 10000 character text
        text = "a" * 10000
        embedding = [0.1, 0.2, 0.3]

        await cache.store_embedding(text, embedding)
        result = await cache.get_embedding(text)

        assert result is not None
        assert result == embedding

    @pytest.mark.asyncio
    async def test_cache_key_includes_prefix_and_embed_namespace(
        self, redis_manager: RedisManager, key_prefix: str
    ) -> None:
        """Cache key includes prefix and 'embed:' namespace."""
        cache = EmbeddingCache(redis_manager)
        text = "namespace test"

        key = cache._cache_key(text)

        # Key should start with prefix
        assert key.startswith(key_prefix)
        # Key should include embed namespace
        assert "embed:" in key
        # Key format: {prefix}embed:{hash}
        assert key.count("embed:") == 1
