"""Unit tests for workers/tasks/memory_tasks.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.db.models.memory import MemoryStatusEnum
from workers.tasks.memory_tasks import (
    _async_decay_and_expire,
    _async_extract_memories,
    _cosine_similarity,
    _merge_near_duplicates,
    _summarize_old_episodic,
)


@pytest.mark.unit
class TestAsyncExtractMemories:
    """Test _async_extract_memories async implementation."""

    @pytest.fixture
    def uuids(self) -> dict[str, str]:
        """Generate string UUIDs for test invocations."""
        return {
            "team_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "user_id": str(uuid4()),
            "conversation_id": str(uuid4()),
        }

    @pytest.fixture
    def messages(self) -> list[dict[str, str]]:
        """Sample conversation messages."""
        return [
            {"role": "user", "content": "Remember I prefer dark mode"},
            {"role": "assistant", "content": "Got it!"},
        ]

    @pytest.fixture
    def mock_extraction_result(self) -> MagicMock:
        """Mock ExtractionResult with standard counts."""
        result = MagicMock()
        result.memories_created = 3
        result.memories_versioned = 1
        result.duplicates_skipped = 0
        result.contradictions_found = 0
        return result

    async def test_calls_extractor_with_correct_uuids(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should pass UUID objects to extractor.extract_from_conversation."""
        from uuid import UUID

        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            await _async_extract_memories(messages=messages, **uuids)

        call_kwargs = mock_extractor.extract_from_conversation.call_args.kwargs
        assert call_kwargs["team_id"] == UUID(uuids["team_id"])
        assert call_kwargs["agent_id"] == UUID(uuids["agent_id"])
        assert call_kwargs["user_id"] == UUID(uuids["user_id"])
        assert call_kwargs["conversation_id"] == UUID(uuids["conversation_id"])

    async def test_returns_correct_result_dict(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should return dict with memories_created, versioned, skipped, contradictions."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            result = await _async_extract_memories(messages=messages, **uuids)

        assert result == {
            "memories_created": 3,
            "memories_versioned": 1,
            "duplicates_skipped": 0,
            "contradictions_found": 0,
        }

    async def test_commits_session_after_extraction(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should commit the database session after successful extraction."""
        session = mock_session_factory._mock_session
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            await _async_extract_memories(messages=messages, **uuids)

        session.commit.assert_awaited_once()

    async def test_creates_fresh_services_per_invocation(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should instantiate new EmbeddingService, AuditLog, ContradictionDetector each call."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ) as MockExtractor,
            patch("src.memory.embedding.EmbeddingService") as MockEmbedding,
            patch("src.memory.memory_log.MemoryAuditLog") as MockAuditLog,
            patch("src.memory.contradiction.ContradictionDetector") as MockContradiction,
        ):
            await _async_extract_memories(messages=messages, **uuids)

        MockEmbedding.assert_called_once()
        MockAuditLog.assert_called_once()
        MockContradiction.assert_called_once()
        MockExtractor.assert_called_once()

    async def test_passes_messages_to_extractor(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should forward the messages list to extract_from_conversation."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            await _async_extract_memories(messages=messages, **uuids)

        call_kwargs = mock_extractor.extract_from_conversation.call_args.kwargs
        assert call_kwargs["messages"] == messages

    async def test_propagates_extractor_errors(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        messages: list[dict[str, str]],
    ) -> None:
        """Should let exceptions propagate for Celery retry handling."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(
            side_effect=RuntimeError("LLM API timeout")
        )

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            with pytest.raises(RuntimeError, match="LLM API timeout"):
                await _async_extract_memories(messages=messages, **uuids)

    async def test_handles_empty_messages(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        uuids: dict[str, str],
        mock_extraction_result: MagicMock,
    ) -> None:
        """Should pass empty list to extractor without error."""
        mock_extraction_result.memories_created = 0
        mock_extraction_result.memories_versioned = 0
        mock_extractor = MagicMock()
        mock_extractor.extract_from_conversation = AsyncMock(return_value=mock_extraction_result)

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.memory.storage.MemoryExtractor",
                return_value=mock_extractor,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch("src.memory.memory_log.MemoryAuditLog"),
            patch("src.memory.contradiction.ContradictionDetector"),
        ):
            result = await _async_extract_memories(messages=[], **uuids)

        assert result["memories_created"] == 0
        call_kwargs = mock_extractor.extract_from_conversation.call_args.kwargs
        assert call_kwargs["messages"] == []


@pytest.mark.unit
class TestAsyncDecayAndExpire:
    """Test _async_decay_and_expire async implementation."""

    async def test_archives_expired_memories(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should archive expired memories and return archived count."""
        session = mock_session_factory._mock_session

        # First execute: expired agents query (distinct agent_ids)
        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = [(uuid4(),)]

        # Second execute: archive update
        archive_result = MagicMock()
        archive_result.rowcount = 5

        # Third execute: stale agents query
        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = []

        # Fourth execute: demote update
        demote_result = MagicMock()
        demote_result.rowcount = 0

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.cache.client.RedisManager"),
            patch("src.cache.hot_cache.HotMemoryCache") as MockCache,
        ):
            mock_cache_instance = AsyncMock()
            MockCache.return_value = mock_cache_instance
            result = await _async_decay_and_expire()

        assert result["archived"] == 5
        session.commit.assert_awaited_once()

    async def test_demotes_stale_warm_memories(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should demote stale warm memories to cold tier."""
        session = mock_session_factory._mock_session

        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = []

        archive_result = MagicMock()
        archive_result.rowcount = 0

        agent_id = uuid4()
        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = [(agent_id,)]

        demote_result = MagicMock()
        demote_result.rowcount = 8

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.cache.client.RedisManager"),
            patch("src.cache.hot_cache.HotMemoryCache") as MockCache,
        ):
            mock_cache_instance = AsyncMock()
            MockCache.return_value = mock_cache_instance
            result = await _async_decay_and_expire()

        assert result["demoted"] == 8

    async def test_returns_count_dict(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should return dict with archived, demoted, and cache_invalidated keys."""
        session = mock_session_factory._mock_session

        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = []

        archive_result = MagicMock()
        archive_result.rowcount = 2

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = []

        demote_result = MagicMock()
        demote_result.rowcount = 3

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _async_decay_and_expire()

        assert result == {"archived": 2, "demoted": 3, "cache_invalidated": 0}

    async def test_invalidates_cache_for_affected_agents(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should call cache.invalidate for each affected agent_id."""
        session = mock_session_factory._mock_session

        agent_1, agent_2 = uuid4(), uuid4()

        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = [(agent_1,)]

        archive_result = MagicMock()
        archive_result.rowcount = 1

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = [(agent_2,)]

        demote_result = MagicMock()
        demote_result.rowcount = 1

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        mock_cache_instance = AsyncMock()

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.cache.client.RedisManager"),
            patch("src.cache.hot_cache.HotMemoryCache", return_value=mock_cache_instance),
        ):
            result = await _async_decay_and_expire()

        assert result["cache_invalidated"] == 2
        assert mock_cache_instance.invalidate.await_count == 2

    async def test_handles_redis_unavailable_gracefully(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should continue without error when Redis import or connection fails."""
        session = mock_session_factory._mock_session

        agent_id = uuid4()
        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = [(agent_id,)]

        archive_result = MagicMock()
        archive_result.rowcount = 1

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = []

        demote_result = MagicMock()
        demote_result.rowcount = 0

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch(
                "src.cache.client.RedisManager",
                side_effect=ConnectionError("Redis down"),
            ),
        ):
            result = await _async_decay_and_expire()

        # Should complete with 0 cache_invalidated, no exception raised
        assert result["archived"] == 1
        assert result["cache_invalidated"] == 0

    async def test_no_changes_returns_zero_counts(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should return all zeros when no memories need decay or expiration."""
        session = mock_session_factory._mock_session

        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = []

        archive_result = MagicMock()
        archive_result.rowcount = 0

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = []

        demote_result = MagicMock()
        demote_result.rowcount = 0

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _async_decay_and_expire()

        assert result == {"archived": 0, "demoted": 0, "cache_invalidated": 0}

    async def test_cache_invalidation_skipped_when_no_redis_url(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should skip cache invalidation when settings.redis_url is empty."""
        mock_settings.redis_url = ""
        session = mock_session_factory._mock_session

        agent_id = uuid4()
        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = [(agent_id,)]

        archive_result = MagicMock()
        archive_result.rowcount = 1

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = []

        demote_result = MagicMock()
        demote_result.rowcount = 0

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.cache.client.RedisManager") as MockRedis,
        ):
            result = await _async_decay_and_expire()

        # RedisManager should never be instantiated
        MockRedis.assert_not_called()
        assert result["cache_invalidated"] == 0

    async def test_deduplicates_affected_agents(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should invalidate cache once per agent even if affected by both archive and demote."""
        session = mock_session_factory._mock_session

        shared_agent = uuid4()

        expired_agents_result = MagicMock()
        expired_agents_result.all.return_value = [(shared_agent,)]

        archive_result = MagicMock()
        archive_result.rowcount = 2

        stale_agents_result = MagicMock()
        stale_agents_result.all.return_value = [(shared_agent,)]

        demote_result = MagicMock()
        demote_result.rowcount = 3

        session.execute.side_effect = [
            expired_agents_result,
            archive_result,
            stale_agents_result,
            demote_result,
        ]

        mock_cache_instance = AsyncMock()

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.cache.client.RedisManager"),
            patch("src.cache.hot_cache.HotMemoryCache", return_value=mock_cache_instance),
        ):
            result = await _async_decay_and_expire()

        # Same agent in both sets: should only invalidate once
        assert result["cache_invalidated"] == 1
        mock_cache_instance.invalidate.assert_awaited_once_with(shared_agent)


@pytest.mark.unit
class TestCosineSimilarity:
    """Test _cosine_similarity helper function."""

    def test_identical_vectors(self) -> None:
        """Should return 1.0 for identical vectors."""
        vec = [1.0, 2.0, 3.0]
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        """Should return 0.0 for orthogonal vectors."""
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector(self) -> None:
        """Should return 0.0 when either vector is zero."""
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert _cosine_similarity([1.0, 1.0], [0.0, 0.0]) == 0.0


@pytest.mark.unit
class TestMergeNearDuplicates:
    """Test _merge_near_duplicates consolidation (Phase 1)."""

    def _make_memory(
        self,
        memory_type: str = "PREFERENCE",
        importance: int = 5,
        embedding: list[float] | None = None,
    ) -> MagicMock:
        """Create a mock MemoryORM for merge testing."""
        mem = MagicMock()
        mem.id = uuid4()
        mem.memory_type = memory_type
        mem.importance = importance
        mem.embedding = embedding or [1.0, 0.0, 0.0]
        mem.content = f"Memory {mem.id}"
        mem.version = 1
        mem.status = "ACTIVE"
        mem.tier = "WARM"
        mem.source_type = "CONVERSATION"
        mem.superseded_by = None
        return mem

    async def test_skips_when_fewer_than_two_memories(self) -> None:
        """Should return 0 when fewer than 2 active memories exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [self._make_memory()]
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        count = await _merge_near_duplicates(
            session=session,
            embedding_service=MagicMock(),
            settings=MagicMock(),
            agent_id=uuid4(),
            team_id=uuid4(),
        )

        assert count == 0

    async def test_merges_similar_pair(self) -> None:
        """Should merge two memories with similarity > 0.92."""
        # Near-identical embeddings
        mem_a = self._make_memory(importance=5, embedding=[1.0, 0.0, 0.0])
        mem_b = self._make_memory(importance=7, embedding=[0.99, 0.05, 0.0])

        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [mem_a, mem_b]
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        embedding_service = MagicMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.99, 0.02, 0.0])

        settings = MagicMock()
        settings.llm_base_url = "https://openrouter.ai/api/v1"
        settings.llm_api_key = "test"
        settings.llm_model = "test-model"

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Merged content",
        ):
            count = await _merge_near_duplicates(
                session=session,
                embedding_service=embedding_service,
                settings=settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 1
        # Higher importance (mem_b=7) is winner
        assert mem_b.content == "Merged content"
        assert mem_b.version == 2
        assert mem_a.superseded_by == mem_b.id

    async def test_winner_has_higher_importance(self) -> None:
        """Should keep the memory with higher importance as the winner."""
        mem_low = self._make_memory(importance=3, embedding=[1.0, 0.0, 0.0])
        mem_high = self._make_memory(importance=9, embedding=[1.0, 0.0, 0.0])

        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [mem_low, mem_high]
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        embedding_service = MagicMock()
        embedding_service.embed_text = AsyncMock(return_value=[1.0, 0.0, 0.0])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Winner content",
        ):
            await _merge_near_duplicates(
                session=session,
                embedding_service=embedding_service,
                settings=MagicMock(),
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        # mem_high (importance=9) should be the winner
        assert mem_high.content == "Winner content"
        assert mem_low.superseded_by == mem_high.id

    async def test_no_merge_below_threshold(self) -> None:
        """Should not merge memories with similarity below 0.92."""
        # Orthogonal embeddings = similarity ~0
        mem_a = self._make_memory(embedding=[1.0, 0.0, 0.0])
        mem_b = self._make_memory(embedding=[0.0, 1.0, 0.0])

        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [mem_a, mem_b]
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        count = await _merge_near_duplicates(
            session=session,
            embedding_service=MagicMock(),
            settings=MagicMock(),
            agent_id=uuid4(),
            team_id=uuid4(),
        )

        assert count == 0
        assert mem_a.superseded_by is None
        assert mem_b.superseded_by is None


@pytest.mark.unit
class TestSummarizeOldEpisodic:
    """Test _summarize_old_episodic consolidation (Phase 2)."""

    def _make_episodic(
        self,
        embedding: list[float] | None = None,
        access_count: int = 1,
        importance: int = 5,
    ) -> MagicMock:
        """Create a mock episodic MemoryORM for summarize testing."""
        mem = MagicMock()
        mem.id = uuid4()
        mem.memory_type = "EPISODIC"
        mem.importance = importance
        mem.embedding = embedding or [1.0, 0.0, 0.0]
        mem.content = f"Episodic memory {mem.id}"
        mem.access_count = access_count
        mem.status = "ACTIVE"
        mem.tier = "WARM"
        mem.superseded_by = None
        return mem

    async def test_skips_when_too_few_memories(self) -> None:
        """Should return 0 when fewer than 3 eligible memories."""
        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [self._make_episodic(), self._make_episodic()]
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        count = await _summarize_old_episodic(
            session=session,
            embedding_service=MagicMock(),
            settings=MagicMock(),
            agent_id=uuid4(),
            team_id=uuid4(),
        )

        assert count == 0

    async def test_creates_summary_for_cluster(self) -> None:
        """Should create a consolidation summary for a cluster of 3+ similar memories."""
        # 3 similar episodic memories
        similar_embedding = [1.0, 0.0, 0.0]
        mems = [self._make_episodic(embedding=similar_embedding) for _ in range(3)]

        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = mems
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result
        session.add = MagicMock()
        session.flush = AsyncMock()

        embedding_service = MagicMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.9, 0.1, 0.0])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Consolidated summary",
        ):
            count = await _summarize_old_episodic(
                session=session,
                embedding_service=embedding_service,
                settings=MagicMock(),
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 1
        session.add.assert_called_once()
        # All originals should be marked superseded
        for mem in mems:
            assert mem.status == MemoryStatusEnum.SUPERSEDED

    async def test_skips_small_clusters(self) -> None:
        """Should not summarize clusters smaller than 3 members."""
        # 2 similar + 1 dissimilar = no cluster reaches 3
        mems = [
            self._make_episodic(embedding=[1.0, 0.0, 0.0]),
            self._make_episodic(embedding=[1.0, 0.0, 0.0]),
            self._make_episodic(embedding=[0.0, 1.0, 0.0]),  # dissimilar
        ]

        session = AsyncMock()
        mock_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = mems
        mock_result.scalars.return_value = scalars
        session.execute.return_value = mock_result

        count = await _summarize_old_episodic(
            session=session,
            embedding_service=MagicMock(),
            settings=MagicMock(),
            agent_id=uuid4(),
            team_id=uuid4(),
        )

        assert count == 0
