"""Unit tests for memory consolidation (Phase 1+2) in workers/tasks/memory_tasks.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from workers.tasks.memory_tasks import (
    MERGE_SIMILARITY_THRESHOLD,
    _async_consolidate,
    _cosine_similarity,
    _merge_near_duplicates,
    _summarize_old_episodic,
)


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCosineSimilarity:
    """Test _cosine_similarity helper function."""

    def test_identical_vectors_return_one(self) -> None:
        """Identical normalized vectors should produce similarity of 1.0."""
        v = [0.6, 0.8]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self) -> None:
        """Perpendicular vectors should produce similarity of 0.0."""
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_return_negative_one(self) -> None:
        """Opposite vectors should produce similarity of -1.0."""
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        """A zero vector should produce similarity of 0.0."""
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_both_zero_vectors_return_zero(self) -> None:
        """Two zero vectors should produce similarity of 0.0."""
        assert _cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_similar_vectors_above_threshold(self) -> None:
        """Slightly different vectors should exceed the merge threshold."""
        v1 = [0.9, 0.1, 0.0]
        v2 = [0.91, 0.09, 0.01]
        assert _cosine_similarity(v1, v2) > MERGE_SIMILARITY_THRESHOLD

    def test_different_vectors_below_threshold(self) -> None:
        """Sufficiently different vectors should be below the merge threshold."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        assert _cosine_similarity(v1, v2) < MERGE_SIMILARITY_THRESHOLD


# ---------------------------------------------------------------------------
# _merge_near_duplicates (Phase 1)
# ---------------------------------------------------------------------------


def _make_memory_mock(
    memory_id: None = None,
    memory_type: str = "semantic",
    content: str = "test content",
    importance: int = 5,
    embedding: list[float] | None = None,
    version: int = 1,
) -> MagicMock:
    """Create a mock MemoryORM for consolidation tests."""
    mem = MagicMock()
    mem.id = memory_id or uuid4()
    mem.memory_type = memory_type
    mem.content = content
    mem.importance = importance
    mem.embedding = embedding or [0.9, 0.1, 0.0]
    mem.version = version
    mem.status = "active"
    mem.tier = "warm"
    mem.superseded_by = None
    mem.source_type = None
    return mem


@pytest.mark.unit
class TestMergeNearDuplicates:
    """Test _merge_near_duplicates (Phase 1 consolidation)."""

    async def test_skips_when_fewer_than_two_memories(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should return 0 merges when fewer than 2 active memories exist."""
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [_make_memory_mock()]
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_embedding = MagicMock()

        count = await _merge_near_duplicates(
            session=mock_session,
            embedding_service=mock_embedding,
            settings=mock_settings,
            agent_id=uuid4(),
            team_id=uuid4(),
        )
        assert count == 0

    async def test_merges_high_similarity_pair(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should merge a pair of memories with similarity > 0.92."""
        # Two nearly identical embeddings
        emb_a = [0.9, 0.1, 0.0]
        emb_b = [0.91, 0.09, 0.01]
        mem_a = _make_memory_mock(content="User likes dark mode", importance=5, embedding=emb_a)
        mem_b = _make_memory_mock(content="User prefers dark mode", importance=7, embedding=emb_b)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem_a, mem_b]
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_embedding = MagicMock()
        mock_embedding.embed_text = AsyncMock(return_value=[0.91, 0.09, 0.005])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="User prefers dark mode in their interface",
        ):
            count = await _merge_near_duplicates(
                session=mock_session,
                embedding_service=mock_embedding,
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 1
        # Winner should be mem_b (higher importance)
        assert mem_b.content == "User prefers dark mode in their interface"
        assert mem_a.superseded_by == mem_b.id

    async def test_no_merge_for_low_similarity(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should not merge memories with similarity below threshold."""
        emb_a = [1.0, 0.0, 0.0]
        emb_b = [0.0, 1.0, 0.0]
        mem_a = _make_memory_mock(content="Topic A", embedding=emb_a)
        mem_b = _make_memory_mock(content="Topic B", embedding=emb_b)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem_a, mem_b]
        mock_session.execute = AsyncMock(return_value=result_mock)

        count = await _merge_near_duplicates(
            session=mock_session,
            embedding_service=MagicMock(),
            settings=mock_settings,
            agent_id=uuid4(),
            team_id=uuid4(),
        )

        assert count == 0

    async def test_llm_failure_skips_pair(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should skip merge when LLM call fails."""
        emb = [0.9, 0.1, 0.0]
        mem_a = _make_memory_mock(content="A", embedding=emb)
        mem_b = _make_memory_mock(content="B", embedding=emb)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem_a, mem_b]
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            count = await _merge_near_duplicates(
                session=mock_session,
                embedding_service=MagicMock(),
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 0

    async def test_embed_failure_skips_pair(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should skip merge when re-embedding fails."""
        emb = [0.9, 0.1, 0.0]
        mem_a = _make_memory_mock(content="A", embedding=emb)
        mem_b = _make_memory_mock(content="B", embedding=emb)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem_a, mem_b]
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_embedding = MagicMock()
        mock_embedding.embed_text = AsyncMock(side_effect=RuntimeError("Embed API down"))

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Merged content",
        ):
            count = await _merge_near_duplicates(
                session=mock_session,
                embedding_service=mock_embedding,
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 0

    async def test_winner_is_higher_importance(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """When merging, the memory with higher importance should be the winner."""
        emb = [0.9, 0.1, 0.0]
        mem_low = _make_memory_mock(content="Low", importance=3, embedding=emb)
        mem_high = _make_memory_mock(content="High", importance=8, embedding=emb)

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem_low, mem_high]
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_embedding = MagicMock()
        mock_embedding.embed_text = AsyncMock(return_value=[0.9, 0.1, 0.0])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Merged",
        ):
            await _merge_near_duplicates(
                session=mock_session,
                embedding_service=mock_embedding,
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        # mem_high is the winner, mem_low is superseded
        assert mem_low.superseded_by == mem_high.id
        assert mem_high.content == "Merged"


# ---------------------------------------------------------------------------
# _summarize_old_episodic (Phase 2)
# ---------------------------------------------------------------------------


def _make_episodic_mock(
    content: str = "episodic memory",
    embedding: list[float] | None = None,
    created_at: datetime | None = None,
    access_count: int = 1,
    importance: int = 5,
) -> MagicMock:
    """Create a mock MemoryORM for episodic summarization tests."""
    mem = MagicMock()
    mem.id = uuid4()
    mem.memory_type = "episodic"
    mem.content = content
    mem.embedding = embedding or [0.8, 0.2, 0.0]
    mem.created_at = created_at or (datetime.now(timezone.utc) - timedelta(days=10))
    mem.access_count = access_count
    mem.importance = importance
    mem.status = "active"
    mem.tier = "warm"
    mem.superseded_by = None
    return mem


@pytest.mark.unit
class TestSummarizeOldEpisodic:
    """Test _summarize_old_episodic (Phase 2 consolidation)."""

    async def test_skips_when_fewer_than_min_cluster_size(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should return 0 when fewer than 3 eligible memories exist."""
        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            _make_episodic_mock(),
            _make_episodic_mock(),
        ]
        mock_session.execute = AsyncMock(return_value=result_mock)

        count = await _summarize_old_episodic(
            session=mock_session,
            embedding_service=MagicMock(),
            settings=mock_settings,
            agent_id=uuid4(),
            team_id=uuid4(),
        )
        assert count == 0

    async def test_creates_summary_for_similar_cluster(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should create 1 summary for a cluster of 3+ similar episodic memories."""
        # All very similar embeddings (will cluster together)
        emb = [0.8, 0.2, 0.0]
        mems = [_make_episodic_mock(content=f"Event {i}", embedding=emb) for i in range(4)]

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = mems
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.embed_text = AsyncMock(return_value=[0.8, 0.2, 0.0])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Summary of 4 events",
        ):
            count = await _summarize_old_episodic(
                session=mock_session,
                embedding_service=mock_embedding,
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 1
        mock_session.add.assert_called_once()
        # All originals should be superseded
        for mem in mems:
            assert mem.status == "superseded"

    async def test_no_cluster_when_embeddings_differ(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should create 0 summaries when embeddings are too different to cluster."""
        mems = [
            _make_episodic_mock(content="A", embedding=[1.0, 0.0, 0.0]),
            _make_episodic_mock(content="B", embedding=[0.0, 1.0, 0.0]),
            _make_episodic_mock(content="C", embedding=[0.0, 0.0, 1.0]),
        ]

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = mems
        mock_session.execute = AsyncMock(return_value=result_mock)

        count = await _summarize_old_episodic(
            session=mock_session,
            embedding_service=MagicMock(),
            settings=mock_settings,
            agent_id=uuid4(),
            team_id=uuid4(),
        )
        assert count == 0

    async def test_llm_failure_skips_cluster(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should skip cluster when LLM summarization fails."""
        emb = [0.8, 0.2, 0.0]
        mems = [_make_episodic_mock(embedding=emb) for _ in range(3)]

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = mems
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM API down"),
        ):
            count = await _summarize_old_episodic(
                session=mock_session,
                embedding_service=MagicMock(),
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 0

    async def test_uses_max_importance_from_cluster(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Should set the new memory's importance to the max in the cluster."""
        emb = [0.8, 0.2, 0.0]
        mems = [
            _make_episodic_mock(embedding=emb, importance=3),
            _make_episodic_mock(embedding=emb, importance=7),
            _make_episodic_mock(embedding=emb, importance=5),
        ]

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = mems
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_embedding = MagicMock()
        mock_embedding.embed_text = AsyncMock(return_value=[0.8, 0.2, 0.0])

        with patch(
            "workers.tasks.memory_tasks._call_llm",
            new_callable=AsyncMock,
            return_value="Consolidated summary",
        ):
            count = await _summarize_old_episodic(
                session=mock_session,
                embedding_service=mock_embedding,
                settings=mock_settings,
                agent_id=uuid4(),
                team_id=uuid4(),
            )

        assert count == 1
        # Verify the new memory passed to session.add has importance=7
        added_memory = mock_session.add.call_args[0][0]
        assert added_memory.importance == 7


# ---------------------------------------------------------------------------
# _async_consolidate (orchestrator)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsyncConsolidate:
    """Test _async_consolidate orchestrator."""

    async def test_calls_merge_and_summarize(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should call both _merge_near_duplicates and _summarize_old_episodic."""
        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch(
                "workers.tasks.memory_tasks._merge_near_duplicates",
                new_callable=AsyncMock,
                return_value=3,
            ) as mock_merge,
            patch(
                "workers.tasks.memory_tasks._summarize_old_episodic",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_summarize,
        ):
            result = await _async_consolidate(
                team_id=str(uuid4()),
                agent_id=str(uuid4()),
            )

        mock_merge.assert_awaited_once()
        mock_summarize.assert_awaited_once()
        assert result == {"merges": 3, "summaries": 1}

    async def test_commits_session(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should commit the session after both operations complete."""
        session = mock_session_factory._mock_session

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch(
                "workers.tasks.memory_tasks._merge_near_duplicates",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "workers.tasks.memory_tasks._summarize_old_episodic",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            await _async_consolidate(
                team_id=str(uuid4()),
                agent_id=str(uuid4()),
            )

        session.commit.assert_awaited_once()

    async def test_passes_uuid_objects_to_helpers(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Should convert string UUIDs to UUID objects for merge/summarize."""
        from uuid import UUID

        team_str = str(uuid4())
        agent_str = str(uuid4())

        with (
            patch(
                "workers.tasks.memory_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.memory_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("src.memory.embedding.EmbeddingService"),
            patch(
                "workers.tasks.memory_tasks._merge_near_duplicates",
                new_callable=AsyncMock,
                return_value=0,
            ) as mock_merge,
            patch(
                "workers.tasks.memory_tasks._summarize_old_episodic",
                new_callable=AsyncMock,
                return_value=0,
            ) as mock_summarize,
        ):
            await _async_consolidate(team_id=team_str, agent_id=agent_str)

        merge_kwargs = mock_merge.call_args.kwargs
        assert merge_kwargs["agent_id"] == UUID(agent_str)
        assert merge_kwargs["team_id"] == UUID(team_str)

        summarize_kwargs = mock_summarize.call_args.kwargs
        assert summarize_kwargs["agent_id"] == UUID(agent_str)
        assert summarize_kwargs["team_id"] == UUID(team_str)
