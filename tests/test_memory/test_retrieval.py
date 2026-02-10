"""Unit tests for the 5-signal MemoryRetriever pipeline in src/memory/retrieval.py."""

import math
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.memory.retrieval import (
    MemoryRetriever,
    _compute_continuity_score,
    _compute_importance_score,
    _compute_recency_score,
    _compute_semantic_score,
    _compute_weighted_score,
    _format_prompt,
)
from src.memory.token_budget import TokenBudgetManager
from src.memory.types import (
    Contradiction,
    RetrievalResult,
    ScoredMemory,
)
from src.models.agent_models import RetrievalWeights
from src.models.memory_models import (
    MemoryRecord,
    MemorySource,
    MemoryStatus,
    MemoryTier,
    MemoryType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory_record(
    content: str = "test memory",
    memory_type: MemoryType = MemoryType.SEMANTIC,
    importance: int = 5,
    is_pinned: bool = False,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    conversation_id: UUID | None = None,
    related_to: list[UUID] | None = None,
    contradicts: list[UUID] | None = None,
    last_accessed_at: datetime | None = None,
    created_at: datetime | None = None,
    memory_id: UUID | None = None,
    team_id: UUID | None = None,
) -> MemoryRecord:
    """Build a MemoryRecord with sensible defaults.

    Args:
        content: The memory content text.
        memory_type: The memory type classification.
        importance: Importance score from 1 to 10.
        is_pinned: Whether the memory is pinned.
        status: Lifecycle status of the memory.
        conversation_id: Source conversation UUID.
        related_to: List of related memory UUIDs.
        contradicts: List of contradicted memory UUIDs.
        last_accessed_at: When the memory was last accessed.
        created_at: When the memory was created.
        memory_id: Explicit UUID for the memory.
        team_id: Explicit team UUID.

    Returns:
        A MemoryRecord instance with all required fields populated.
    """
    now = datetime.now(tz=timezone.utc)
    return MemoryRecord(
        id=memory_id or uuid4(),
        team_id=team_id or uuid4(),
        memory_type=memory_type,
        content=content,
        importance=importance,
        confidence=1.0,
        access_count=3,
        is_pinned=is_pinned,
        source_type=MemorySource.EXTRACTION,
        source_conversation_id=conversation_id,
        source_message_ids=[],
        extraction_model=None,
        version=1,
        superseded_by=None,
        contradicts=contradicts or [],
        related_to=related_to or [],
        metadata={},
        tier=MemoryTier.WARM,
        status=status,
        created_at=created_at or now,
        updated_at=now,
        last_accessed_at=last_accessed_at or now,
        expires_at=None,
    )


def _make_mock_orm(
    content: str = "test memory",
    memory_type: str = "semantic",
    importance: int = 5,
    is_pinned: bool = False,
    status: str = "active",
    subject: str | None = None,
    conversation_id: UUID | None = None,
    related_to: list[str] | None = None,
    contradicts: list[str] | None = None,
    access_count: int = 3,
    last_accessed_at: datetime | None = None,
    created_at: datetime | None = None,
    memory_id: UUID | None = None,
    team_id: UUID | None = None,
) -> MagicMock:
    """Build a MagicMock that mimics a MemoryORM instance.

    Args:
        content: The memory content text.
        memory_type: Memory type string value.
        importance: Importance score 1-10.
        is_pinned: Whether the memory is pinned.
        status: Status string value.
        subject: Optional subject tag.
        conversation_id: Source conversation UUID.
        related_to: List of related memory ID strings.
        contradicts: List of contradicted memory ID strings.
        access_count: Number of times accessed.
        last_accessed_at: When the memory was last accessed.
        created_at: When the memory was created.
        memory_id: Explicit UUID for the memory.
        team_id: Explicit team UUID.

    Returns:
        A MagicMock configured to behave like a MemoryORM.
    """
    now = datetime.now(tz=timezone.utc)
    orm = MagicMock()
    orm.id = memory_id or uuid4()
    orm.team_id = team_id or uuid4()
    orm.agent_id = None
    orm.user_id = None
    orm.memory_type = memory_type
    orm.content = content
    orm.subject = subject
    orm.embedding = [0.0] * 1536
    orm.importance = importance
    orm.confidence = 1.0
    orm.access_count = access_count
    orm.is_pinned = is_pinned
    orm.source_type = "extraction"
    orm.source_conversation_id = conversation_id
    orm.source_message_ids = []
    orm.extraction_model = None
    orm.version = 1
    orm.superseded_by = None
    orm.contradicts = contradicts or []
    orm.related_to = related_to or []
    orm.metadata_json = {}
    orm.tier = "warm"
    orm.status = status
    orm.last_accessed_at = last_accessed_at or now
    orm.created_at = created_at or now
    orm.updated_at = now
    orm.expires_at = None
    return orm


def _build_retriever(
    mock_session: AsyncMock | None = None,
    weights: RetrievalWeights | None = None,
    budget: int = 4000,
) -> MemoryRetriever:
    """Construct a MemoryRetriever with mock dependencies.

    Args:
        mock_session: Optional pre-configured session mock.
        weights: Optional retrieval weights override.
        budget: Token budget for the TokenBudgetManager.

    Returns:
        A MemoryRetriever wired to mock I/O.
    """
    session = mock_session or AsyncMock()
    session.flush = AsyncMock()
    embedding_svc = AsyncMock()
    embedding_svc.embed_text = AsyncMock(return_value=[0.1] * 1536)
    return MemoryRetriever(
        session=session,
        embedding_service=embedding_svc,
        retrieval_weights=weights or RetrievalWeights(),
        token_budget_manager=TokenBudgetManager(total_budget=budget),
    )


# ===========================================================================
# Signal tests (1-5)
# ===========================================================================


class TestSemanticSignal:
    """Tests for the semantic similarity signal."""

    @pytest.mark.unit
    async def test_semantic_signal_returns_memories_by_embedding_similarity(
        self,
    ) -> None:
        """Semantic search returns memories scored by embedding similarity."""
        retriever = _build_retriever()
        team_id = uuid4()

        orm_high = _make_mock_orm(content="highly relevant", memory_id=uuid4())
        orm_low = _make_mock_orm(content="less relevant", memory_id=uuid4())

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [
                (orm_high, 0.95),
                (orm_low, 0.40),
            ]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="test query", team_id=team_id)

        # The high-similarity memory should have a higher semantic score
        scores_by_content = {
            sm.memory.content: sm.signal_scores["semantic"] for sm in result.memories
        }
        assert scores_by_content["highly relevant"] > scores_by_content["less relevant"]

    @pytest.mark.unit
    def test_compute_semantic_score_clamps(self) -> None:
        """Semantic score is clamped to [0.0, 1.0]."""
        assert _compute_semantic_score(1.5) == 1.0
        assert _compute_semantic_score(-0.3) == 0.0
        assert _compute_semantic_score(0.75) == pytest.approx(0.75)


class TestRecencySignal:
    """Tests for the recency exponential decay signal."""

    @pytest.mark.unit
    def test_recent_memory_scores_higher_than_old(self) -> None:
        """A memory accessed 1 hour ago scores higher than one 100 hours ago."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(hours=1)
        old = now - timedelta(hours=100)

        recent_score = _compute_recency_score(recent)
        old_score = _compute_recency_score(old)

        assert recent_score > old_score

    @pytest.mark.unit
    def test_recency_formula_matches_exp_decay(self) -> None:
        """Recency score follows exp(-0.01 * hours) formula."""
        now = datetime.now(timezone.utc)
        accessed_at = now - timedelta(hours=50)

        score = _compute_recency_score(accessed_at)
        expected = math.exp(-0.01 * 50)

        assert score == pytest.approx(expected, abs=0.01)

    @pytest.mark.unit
    def test_just_now_memory_scores_near_one(self) -> None:
        """A memory accessed just now scores close to 1.0."""
        score = _compute_recency_score(datetime.now(timezone.utc))
        assert score == pytest.approx(1.0, abs=0.01)


class TestImportanceSignal:
    """Tests for the importance scoring rules."""

    @pytest.mark.unit
    def test_pinned_memory_returns_one(self) -> None:
        """Pinned memory always scores 1.0 importance."""
        mem = _make_memory_record(is_pinned=True, importance=3)
        assert _compute_importance_score(mem) == 1.0

    @pytest.mark.unit
    def test_identity_type_returns_one(self) -> None:
        """Identity memory type always scores 1.0 importance."""
        mem = _make_memory_record(memory_type=MemoryType.IDENTITY, importance=2)
        assert _compute_importance_score(mem) == 1.0

    @pytest.mark.unit
    def test_disputed_status_halves_score(self) -> None:
        """Disputed status multiplies base importance by 0.5."""
        mem = _make_memory_record(importance=8, status=MemoryStatus.DISPUTED)
        expected = (8 / 10.0) * 0.5
        assert _compute_importance_score(mem) == pytest.approx(expected)

    @pytest.mark.unit
    def test_normal_importance_is_divided_by_ten(self) -> None:
        """Normal memory importance is importance / 10."""
        mem = _make_memory_record(importance=7)
        assert _compute_importance_score(mem) == pytest.approx(0.7)


class TestContinuitySignal:
    """Tests for the conversation continuity signal."""

    @pytest.mark.unit
    def test_same_conversation_scores_one(self) -> None:
        """Memory from the same conversation gets continuity 1.0."""
        conv_id = uuid4()
        mem = _make_memory_record(conversation_id=conv_id)
        assert _compute_continuity_score(mem, conv_id) == 1.0

    @pytest.mark.unit
    def test_different_conversation_scores_zero(self) -> None:
        """Memory from a different conversation gets continuity 0.0."""
        mem = _make_memory_record(conversation_id=uuid4())
        assert _compute_continuity_score(mem, uuid4()) == 0.0

    @pytest.mark.unit
    def test_none_conversation_id_scores_zero(self) -> None:
        """When no conversation_id is provided, continuity is 0.0."""
        mem = _make_memory_record(conversation_id=uuid4())
        assert _compute_continuity_score(mem, None) == 0.0


class TestRelationshipSignal:
    """Tests for the relationship bonus signal."""

    @pytest.mark.unit
    async def test_referenced_memory_gets_relationship_bonus(self) -> None:
        """A memory referenced in another memory's related_to gets a 0.5 relationship score."""
        retriever = _build_retriever()
        team_id = uuid4()

        target_id = uuid4()
        referrer_id = uuid4()

        orm_target = _make_mock_orm(
            content="target memory",
            memory_id=target_id,
            team_id=team_id,
        )
        orm_referrer = _make_mock_orm(
            content="referrer memory",
            memory_id=referrer_id,
            team_id=team_id,
            related_to=[str(target_id)],
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [
                (orm_target, 0.80),
                (orm_referrer, 0.80),
            ]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="test", team_id=team_id)

        target_scored = next(sm for sm in result.memories if sm.memory.id == target_id)
        referrer_scored = next(sm for sm in result.memories if sm.memory.id == referrer_id)

        assert target_scored.signal_scores["relationship"] == pytest.approx(0.5)
        assert referrer_scored.signal_scores["relationship"] == pytest.approx(0.0)


# ===========================================================================
# Pipeline tests (6-11)
# ===========================================================================


class TestWeightedScore:
    """Tests for the weighted score computation."""

    @pytest.mark.unit
    def test_final_score_is_weighted_sum(self) -> None:
        """Final score equals the weighted sum of individual signals."""
        weights = RetrievalWeights(
            semantic=0.35,
            recency=0.20,
            importance=0.20,
            continuity=0.15,
            relationship=0.10,
        )
        signals = {
            "semantic": 0.9,
            "recency": 0.7,
            "importance": 0.5,
            "continuity": 1.0,
            "relationship": 0.0,
        }

        expected = 0.9 * 0.35 + 0.7 * 0.20 + 0.5 * 0.20 + 1.0 * 0.15 + 0.0 * 0.10

        result = _compute_weighted_score(signals, weights)
        assert result == pytest.approx(expected)

    @pytest.mark.unit
    def test_weighted_score_clamped_to_unit_range(self) -> None:
        """Weighted score is clamped to [0.0, 1.0]."""
        weights = RetrievalWeights(
            semantic=1.0,
            recency=1.0,
            importance=1.0,
            continuity=1.0,
            relationship=1.0,
        )
        signals = {
            "semantic": 1.0,
            "recency": 1.0,
            "importance": 1.0,
            "continuity": 1.0,
            "relationship": 1.0,
        }
        assert _compute_weighted_score(signals, weights) == 1.0


class TestDeduplication:
    """Tests for deduplication during merge."""

    @pytest.mark.unit
    async def test_same_memory_from_multiple_sources_keeps_highest_score(
        self,
    ) -> None:
        """When the same memory appears in both semantic and recency results,
        it is deduplicated and the highest semantic similarity is kept.
        """
        retriever = _build_retriever()
        team_id = uuid4()
        shared_id = uuid4()

        orm_semantic = _make_mock_orm(
            content="shared memory",
            memory_id=shared_id,
            team_id=team_id,
        )
        orm_recency = _make_mock_orm(
            content="shared memory",
            memory_id=shared_id,
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [(orm_semantic, 0.85)]
            mock_get_team.return_value = [orm_recency]

            result = await retriever.retrieve(query="test", team_id=team_id)

        # Should be deduplicated to a single entry
        ids = [sm.memory.id for sm in result.memories]
        assert ids.count(shared_id) == 1

        # The semantic similarity 0.85 should be used (not 0.0 from recency)
        scored = result.memories[0]
        assert scored.signal_scores["semantic"] == pytest.approx(0.85)


class TestTokenBudget:
    """Tests for token budget trimming in the pipeline."""

    @pytest.mark.unit
    async def test_memories_over_budget_are_trimmed(self) -> None:
        """Memories that exceed the token budget are excluded from the result."""
        # Use a very tight budget
        retriever = _build_retriever(budget=20)
        team_id = uuid4()

        # Short memory fits; long memory does not
        orm_short = _make_mock_orm(
            content="hi",
            memory_id=uuid4(),
            team_id=team_id,
        )
        orm_long = _make_mock_orm(
            content="x" * 500,
            memory_id=uuid4(),
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [
                (orm_short, 0.90),
                (orm_long, 0.85),
            ]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="test", team_id=team_id)

        contents = [sm.memory.content for sm in result.memories]
        assert "hi" in contents
        assert ("x" * 500) not in contents


class TestFormattedPrompt:
    """Tests for the formatted prompt output."""

    @pytest.mark.unit
    def test_formatted_prompt_has_section_headers_grouped_by_type(self) -> None:
        """Formatted prompt groups memories by type with section headers."""
        mem_semantic = _make_memory_record(
            content="fact one",
            memory_type=MemoryType.SEMANTIC,
        )
        mem_episodic = _make_memory_record(
            content="episode one",
            memory_type=MemoryType.EPISODIC,
        )

        scored = [
            ScoredMemory(
                memory=mem_semantic,
                final_score=0.8,
                signal_scores={"semantic": 0.8},
            ),
            ScoredMemory(
                memory=mem_episodic,
                final_score=0.6,
                signal_scores={"semantic": 0.6},
            ),
        ]

        prompt = _format_prompt(scored, [])

        assert "### Semantic Memories" in prompt
        assert "### Episodic Memories" in prompt
        assert "- fact one" in prompt
        assert "- episode one" in prompt

    @pytest.mark.unit
    def test_formatted_prompt_includes_disputed_facts_section(self) -> None:
        """Contradictions are appended as a Disputed Facts section."""
        contradictions = [
            Contradiction(
                memory_a=uuid4(),
                memory_b=uuid4(),
                reason="A says X, B says Y",
            ),
        ]

        prompt = _format_prompt([], contradictions)

        assert "### Disputed Facts" in prompt
        assert "[FACT DISPUTED]:" in prompt
        assert "A says X, B says Y" in prompt

    @pytest.mark.unit
    def test_formatted_prompt_empty_when_no_memories(self) -> None:
        """Empty memories and no contradictions produce an empty string."""
        assert _format_prompt([], []) == ""


class TestIdentityAlwaysIncluded:
    """Tests that identity memories are never trimmed."""

    @pytest.mark.unit
    async def test_identity_memories_always_in_result_regardless_of_score(
        self,
    ) -> None:
        """Identity memories are included even with a tiny token budget."""
        retriever = _build_retriever(budget=5)
        team_id = uuid4()

        orm_identity = _make_mock_orm(
            content="I am the agent identity",
            memory_type="identity",
            importance=1,
            memory_id=uuid4(),
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [(orm_identity, 0.10)]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="who are you", team_id=team_id)

        types = [sm.memory.memory_type for sm in result.memories]
        assert MemoryType.IDENTITY in types


class TestEmptyQuery:
    """Tests for edge case of an empty query."""

    @pytest.mark.unit
    async def test_empty_query_returns_empty_result(self) -> None:
        """An empty query string returns no memories in the result."""
        retriever = _build_retriever()
        team_id = uuid4()

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = []
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="", team_id=team_id)

        assert result.memories == []
        assert result.formatted_prompt == ""


# ===========================================================================
# Cache tests (12)
# ===========================================================================


class TestCacheHit:
    """Tests for the L1 hot cache."""

    @pytest.mark.unit
    async def test_cache_hit_returns_same_result_without_db_call(self) -> None:
        """Repeating the same query within 60s returns a cached result
        without a second database call.
        """
        retriever = _build_retriever()
        team_id = uuid4()

        orm = _make_mock_orm(
            content="cached memory",
            memory_id=uuid4(),
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [(orm, 0.9)]
            mock_get_team.return_value = []

            # First call -- populates cache
            result1 = await retriever.retrieve(query="cache test", team_id=team_id)
            call_count_after_first = mock_search.call_count

            # Second call -- should hit cache
            result2 = await retriever.retrieve(query="cache test", team_id=team_id)
            call_count_after_second = mock_search.call_count

        # DB should not have been called again
        assert call_count_after_second == call_count_after_first

        # Both results should contain the same memory content
        assert len(result1.memories) == len(result2.memories)
        assert result2.stats.cache_hit is True

    @pytest.mark.unit
    async def test_cache_expired_entry_triggers_new_db_call(self) -> None:
        """An expired cache entry is evicted and a fresh DB call is made."""
        retriever = _build_retriever()
        team_id = uuid4()

        orm = _make_mock_orm(
            content="expirable memory",
            memory_id=uuid4(),
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [(orm, 0.9)]
            mock_get_team.return_value = []

            # First call -- populates cache
            await retriever.retrieve(query="expire test", team_id=team_id)
            first_count = mock_search.call_count

            # Manually expire the cache entry
            for entry in retriever._cache.values():
                entry.created_at = time.monotonic() - 120  # 120s ago > 60s TTL

            # Second call -- cache expired, should trigger new DB call
            await retriever.retrieve(query="expire test", team_id=team_id)
            second_count = mock_search.call_count

        assert second_count > first_count


# ===========================================================================
# Integration-level pipeline tests
# ===========================================================================


class TestFullPipeline:
    """End-to-end pipeline tests combining multiple signals."""

    @pytest.mark.unit
    async def test_full_pipeline_produces_valid_retrieval_result(self) -> None:
        """A complete retrieval returns a valid RetrievalResult with stats."""
        retriever = _build_retriever()
        team_id = uuid4()
        conv_id = uuid4()

        orm = _make_mock_orm(
            content="full pipeline memory",
            memory_type="semantic",
            importance=8,
            memory_id=uuid4(),
            team_id=team_id,
            conversation_id=conv_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [(orm, 0.85)]
            mock_get_team.return_value = []

            result = await retriever.retrieve(
                query="pipeline test",
                team_id=team_id,
                conversation_id=conv_id,
            )

        assert isinstance(result, RetrievalResult)
        assert len(result.memories) == 1
        assert result.stats.cache_hit is False
        assert result.stats.total_ms >= 0.0
        assert result.stats.signals_hit > 0

        # Verify all 5 signal scores are present
        scored = result.memories[0]
        expected_signals = {
            "semantic",
            "recency",
            "importance",
            "continuity",
            "relationship",
        }
        assert set(scored.signal_scores.keys()) == expected_signals

    @pytest.mark.unit
    async def test_pipeline_with_custom_weights(self) -> None:
        """Pipeline respects custom retrieval weights for scoring."""
        # Heavily weight semantic, zero everything else
        weights = RetrievalWeights(
            semantic=1.0,
            recency=0.0,
            importance=0.0,
            continuity=0.0,
            relationship=0.0,
        )
        retriever = _build_retriever(weights=weights)
        team_id = uuid4()

        orm_high = _make_mock_orm(
            content="high sim",
            memory_id=uuid4(),
            team_id=team_id,
        )
        orm_low = _make_mock_orm(
            content="low sim",
            memory_id=uuid4(),
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [
                (orm_high, 0.95),
                (orm_low, 0.30),
            ]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="test", team_id=team_id)

        # With only semantic weight, high similarity should rank first
        assert result.memories[0].memory.content == "high sim"
        assert result.memories[0].final_score > result.memories[1].final_score

    @pytest.mark.unit
    async def test_contradiction_detection_in_pipeline(self) -> None:
        """Pipeline detects contradictions between memories."""
        retriever = _build_retriever()
        team_id = uuid4()

        id_a = uuid4()
        id_b = uuid4()

        orm_a = _make_mock_orm(
            content="The user likes cats",
            memory_id=id_a,
            team_id=team_id,
            contradicts=[str(id_b)],
        )
        orm_b = _make_mock_orm(
            content="The user dislikes cats",
            memory_id=id_b,
            team_id=team_id,
        )

        with (
            patch.object(
                retriever._repo, "search_by_embedding", new_callable=AsyncMock
            ) as mock_search,
            patch.object(retriever._repo, "get_by_team", new_callable=AsyncMock) as mock_get_team,
        ):
            mock_search.return_value = [
                (orm_a, 0.80),
                (orm_b, 0.80),
            ]
            mock_get_team.return_value = []

            result = await retriever.retrieve(query="cats", team_id=team_id)

        assert len(result.contradictions) >= 1
        # Check both IDs appear in the contradiction (order-independent)
        contradiction_id_sets = {frozenset({c.memory_a, c.memory_b}) for c in result.contradictions}
        assert frozenset({id_a, id_b}) in contradiction_id_sets
