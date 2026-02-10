"""Unit tests for WorkingMemoryCache."""

import pytest
from uuid import uuid4

from src.cache.working_memory import WorkingMemoryCache


class TestWorkingMemoryCache:
    """Tests for WorkingMemoryCache class."""

    @pytest.mark.asyncio
    async def test_set_context_get_context_roundtrip(self, redis_manager, key_prefix: str) -> None:
        """Test that set_context and get_context round-trip correctly."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()
        context = {"user_id": "123", "topic": "weather", "language": "en"}

        await cache.set_context(conversation_id, context)
        result = await cache.get_context(conversation_id)

        assert result == context

    @pytest.mark.asyncio
    async def test_get_context_returns_none_on_miss(self, redis_manager) -> None:
        """Test that get_context returns None when key doesn't exist."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        result = await cache.get_context(conversation_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_context_returns_none_when_unavailable(
        self, unavailable_redis_manager
    ) -> None:
        """Test that get_context returns None when Redis is unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        conversation_id = uuid4()

        result = await cache.get_context(conversation_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_append_turn_adds_turn_to_list(self, redis_manager) -> None:
        """Test that append_turn adds a turn to the turns list."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        await cache.append_turn(conversation_id, "user", "Hello!")
        turns = await cache.get_turns(conversation_id)

        assert len(turns) == 1
        assert turns[0] == {"role": "user", "content": "Hello!"}

    @pytest.mark.asyncio
    async def test_append_turn_accumulates_multiple_turns(self, redis_manager) -> None:
        """Test that append_turn accumulates multiple turns in order."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        await cache.append_turn(conversation_id, "user", "Hello!")
        await cache.append_turn(conversation_id, "assistant", "Hi there!")
        await cache.append_turn(conversation_id, "user", "How are you?")
        turns = await cache.get_turns(conversation_id)

        assert len(turns) == 3
        assert turns[0] == {"role": "user", "content": "Hello!"}
        assert turns[1] == {"role": "assistant", "content": "Hi there!"}
        assert turns[2] == {"role": "user", "content": "How are you?"}

    @pytest.mark.asyncio
    async def test_get_turns_returns_empty_list_on_miss(self, redis_manager) -> None:
        """Test that get_turns returns empty list when key doesn't exist."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        turns = await cache.get_turns(conversation_id)

        assert turns == []

    @pytest.mark.asyncio
    async def test_set_field_get_field_for_arbitrary_fields(self, redis_manager) -> None:
        """Test that set_field and get_field work for arbitrary fields."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Test scratchpad field
        await cache.set_field(conversation_id, "scratchpad", "thinking about the problem...")
        scratchpad = await cache.get_field(conversation_id, "scratchpad")
        assert scratchpad == "thinking about the problem..."

        # Test summary field
        await cache.set_field(
            conversation_id, "summary", "Discussing weather forecasts and travel plans"
        )
        summary = await cache.get_field(conversation_id, "summary")
        assert summary == "Discussing weather forecasts and travel plans"

    @pytest.mark.asyncio
    async def test_delete_removes_key_entirely(self, redis_manager, fake_redis) -> None:
        """Test that delete removes the entire key."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Set multiple fields
        await cache.set_context(conversation_id, {"user_id": "123"})
        await cache.append_turn(conversation_id, "user", "Hello!")
        await cache.set_field(conversation_id, "summary", "Test conversation")

        # Verify data exists
        assert await cache.get_context(conversation_id) is not None
        assert len(await cache.get_turns(conversation_id)) == 1
        assert await cache.get_field(conversation_id, "summary") is not None

        # Delete
        await cache.delete(conversation_id)

        # Verify all data is gone
        assert await cache.get_context(conversation_id) is None
        assert await cache.get_turns(conversation_id) == []
        assert await cache.get_field(conversation_id, "summary") is None

    @pytest.mark.asyncio
    async def test_ttl_is_set_to_7200_seconds(
        self, redis_manager, fake_redis, key_prefix: str
    ) -> None:
        """Test that TTL is set to 7200 seconds (2 hours)."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        await cache.set_context(conversation_id, {"user_id": "123"})

        key = f"{key_prefix}working:{conversation_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl == 7200

    @pytest.mark.asyncio
    async def test_append_turn_refreshes_ttl(
        self, redis_manager, fake_redis, key_prefix: str
    ) -> None:
        """Test that append_turn refreshes the TTL."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Set initial context
        await cache.set_context(conversation_id, {"user_id": "123"})

        # Manually set a lower TTL
        key = f"{key_prefix}working:{conversation_id}"
        await fake_redis.expire(key, 100)
        ttl_before = await fake_redis.ttl(key)
        assert ttl_before <= 100

        # Append turn should refresh TTL to 7200
        await cache.append_turn(conversation_id, "user", "Hello!")
        ttl_after = await fake_redis.ttl(key)
        assert ttl_after == 7200

    @pytest.mark.asyncio
    async def test_set_context_overwrites_existing_context(self, redis_manager) -> None:
        """Test that set_context overwrites existing context."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Set initial context
        await cache.set_context(conversation_id, {"user_id": "123", "topic": "weather"})
        result1 = await cache.get_context(conversation_id)
        assert result1 == {"user_id": "123", "topic": "weather"}

        # Overwrite context
        await cache.set_context(conversation_id, {"user_id": "456", "topic": "sports"})
        result2 = await cache.get_context(conversation_id)
        assert result2 == {"user_id": "456", "topic": "sports"}

    @pytest.mark.asyncio
    async def test_key_format(self, redis_manager, fake_redis, key_prefix: str) -> None:
        """Test that key format is {prefix}working:{conversation_id}."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        await cache.set_context(conversation_id, {"test": "data"})

        expected_key = f"{key_prefix}working:{conversation_id}"
        keys = await fake_redis.keys("*")
        assert expected_key in keys

    @pytest.mark.asyncio
    async def test_large_context_dict_roundtrip(self, redis_manager) -> None:
        """Test that large nested context dict round-trips correctly."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Create large nested context
        large_context = {
            "user_id": "user_12345",
            "session_id": "session_67890",
            "topic": "advanced_AI_discussion",
            "language": "en",
            "preferences": {
                "theme": "dark",
                "notifications": True,
                "history_length": 100,
            },
            "metadata": {
                "created_at": "2026-02-09T12:00:00Z",
                "updated_at": "2026-02-09T14:30:00Z",
                "tags": ["ai", "machine-learning", "nlp"],
            },
            "context_data": {
                "previous_topics": ["weather", "sports", "technology"],
                "mentioned_entities": ["OpenAI", "Anthropic", "Google"],
                "sentiment": "positive",
            },
            "stats": {"turn_count": 42, "total_tokens": 8500, "duration_seconds": 3600},
            "flags": {"is_new_user": False, "requires_review": True, "is_premium": True},
        }

        await cache.set_context(conversation_id, large_context)
        result = await cache.get_context(conversation_id)

        assert result == large_context

    @pytest.mark.asyncio
    async def test_get_turns_when_redis_unavailable(self, unavailable_redis_manager) -> None:
        """Test that get_turns returns empty list when Redis unavailable."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        conversation_id = uuid4()

        turns = await cache.get_turns(conversation_id)

        assert turns == []

    @pytest.mark.asyncio
    async def test_set_field_when_redis_unavailable(self, unavailable_redis_manager) -> None:
        """Test that set_field does nothing when Redis unavailable (no error)."""
        cache = WorkingMemoryCache(unavailable_redis_manager)
        conversation_id = uuid4()

        # Should not raise exception
        await cache.set_field(conversation_id, "test_field", "test_value")

        # Verify nothing was set (returns None)
        result = await cache.get_field(conversation_id, "test_field")
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_conversations_are_independent(self, redis_manager) -> None:
        """Test that multiple conversations are independent."""
        cache = WorkingMemoryCache(redis_manager)
        conv_id_1 = uuid4()
        conv_id_2 = uuid4()

        # Set different contexts for two conversations
        await cache.set_context(conv_id_1, {"user_id": "user1", "topic": "weather"})
        await cache.set_context(conv_id_2, {"user_id": "user2", "topic": "sports"})

        # Set different turns
        await cache.append_turn(conv_id_1, "user", "What's the weather?")
        await cache.append_turn(conv_id_2, "user", "Who won the game?")

        # Verify contexts are independent
        context1 = await cache.get_context(conv_id_1)
        context2 = await cache.get_context(conv_id_2)
        assert context1 == {"user_id": "user1", "topic": "weather"}
        assert context2 == {"user_id": "user2", "topic": "sports"}

        # Verify turns are independent
        turns1 = await cache.get_turns(conv_id_1)
        turns2 = await cache.get_turns(conv_id_2)
        assert len(turns1) == 1
        assert len(turns2) == 1
        assert turns1[0]["content"] == "What's the weather?"
        assert turns2[0]["content"] == "Who won the game?"

    @pytest.mark.asyncio
    async def test_get_field_returns_none_on_miss(self, redis_manager) -> None:
        """Test that get_field returns None when field doesn't exist."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        result = await cache.get_field(conversation_id, "nonexistent_field")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_field_refreshes_ttl(
        self, redis_manager, fake_redis, key_prefix: str
    ) -> None:
        """Test that set_field refreshes the TTL."""
        cache = WorkingMemoryCache(redis_manager)
        conversation_id = uuid4()

        # Set initial context
        await cache.set_context(conversation_id, {"user_id": "123"})

        # Manually set a lower TTL
        key = f"{key_prefix}working:{conversation_id}"
        await fake_redis.expire(key, 100)
        ttl_before = await fake_redis.ttl(key)
        assert ttl_before <= 100

        # Set field should refresh TTL to 7200
        await cache.set_field(conversation_id, "summary", "Test summary")
        ttl_after = await fake_redis.ttl(key)
        assert ttl_after == 7200
