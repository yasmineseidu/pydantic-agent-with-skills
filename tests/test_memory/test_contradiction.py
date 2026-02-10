"""Unit tests for ContradictionDetector in src/memory/contradiction.py."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.memory.contradiction import ContradictionDetector
from src.memory.types import (
    Contradiction,
    ContradictionResult,
    ExtractedMemory,
    ScoredMemory,
)
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


def _make_mock_memory_orm(
    content: str = "Some existing content",
    subject: str = "test.subject",
    importance: int = 5,
    memory_id: UUID | None = None,
) -> MagicMock:
    """Build a MagicMock resembling a MemoryORM row.

    Args:
        content: Memory content text.
        subject: Subject string.
        importance: Importance score 1-10.
        memory_id: Optional UUID; auto-generated if None.

    Returns:
        MagicMock with id, content, subject, importance, and created_at attributes.
    """
    mock = MagicMock()
    mock.id = memory_id or uuid4()
    mock.content = content
    mock.subject = subject
    mock.importance = importance
    mock.created_at = datetime.now(tz=timezone.utc)
    return mock


def _make_scored_memory(
    content: str,
    subject: str | None = None,
    score: float = 0.5,
    memory_id: UUID | None = None,
    team_id: UUID | None = None,
) -> ScoredMemory:
    """Build a ScoredMemory for check_on_retrieve tests.

    Args:
        content: Memory content text.
        subject: Optional subject tag.
        score: Final composite score.
        memory_id: Optional UUID; auto-generated if None.
        team_id: Optional team UUID; auto-generated if None.

    Returns:
        A fully populated ScoredMemory instance.
    """
    now = datetime.now(tz=timezone.utc)
    return ScoredMemory(
        memory=MemoryRecord(
            id=memory_id or uuid4(),
            team_id=team_id or uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content=content,
            subject=subject,
            importance=5,
            confidence=1.0,
            source_type=MemorySource.EXTRACTION,
            version=1,
            tier=MemoryTier.WARM,
            status=MemoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        ),
        final_score=score,
    )


def _make_detector(
    mock_session: AsyncMock,
    mock_embedding_service: AsyncMock,
) -> ContradictionDetector:
    """Create a ContradictionDetector with mocked dependencies.

    Args:
        mock_session: Mock AsyncSession.
        mock_embedding_service: Mock EmbeddingService.

    Returns:
        Initialized ContradictionDetector.
    """
    return ContradictionDetector(
        session=mock_session,
        embedding_service=mock_embedding_service,
    )


def _mock_session_with_results(results: list[MagicMock]) -> AsyncMock:
    """Build a mock session whose execute returns the given ORM results.

    Args:
        results: List of mock MemoryORM objects to return from scalars().all().

    Returns:
        AsyncMock session with execute wired up.
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = results
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _mock_embedding_service() -> AsyncMock:
    """Build a mock EmbeddingService.

    Returns:
        AsyncMock with embed_text returning a 1536-dim zero vector.
    """
    service = AsyncMock()
    service.embed_text = AsyncMock(return_value=[0.0] * 1536)
    return service


# ---------------------------------------------------------------------------
# check_on_store tests
# ---------------------------------------------------------------------------


class TestCheckOnStore:
    """Tests for ContradictionDetector.check_on_store."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_supersede_when_new_has_higher_importance(self) -> None:
        """Same subject, different content, new importance > existing -> supersede."""
        existing = _make_mock_memory_orm(
            content="The sky is blue",
            subject="sky.color",
            importance=5,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="The sky is red at sunset",
            subject="sky.color",
            importance=8,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert isinstance(result, ContradictionResult)
        assert result.action == "supersede"
        assert len(result.contradicts) == 1
        assert result.contradicts[0] == existing.id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispute_when_new_has_equal_importance(self) -> None:
        """Same subject, different content, equal importance -> dispute."""
        existing = _make_mock_memory_orm(
            content="Python is the best language",
            subject="language.preference",
            importance=7,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="Rust is the best language",
            subject="language.preference",
            importance=7,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "dispute"
        assert len(result.contradicts) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispute_when_new_has_lower_importance(self) -> None:
        """Same subject, different content, lower importance -> dispute."""
        existing = _make_mock_memory_orm(
            content="Use tabs for indentation",
            subject="style.indentation",
            importance=8,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="Use spaces for indentation",
            subject="style.indentation",
            importance=3,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "dispute"
        assert len(result.contradicts) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coexist_when_same_content(self) -> None:
        """Same subject, same content (after normalization) -> coexist."""
        existing = _make_mock_memory_orm(
            content="The user prefers dark mode",
            subject="user.theme",
            importance=5,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="  The User Prefers Dark Mode  ",
            subject="user.theme",
            importance=5,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "coexist"
        assert len(result.contradicts) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coexist_when_no_subject_on_new_memory(self) -> None:
        """No subject on new memory -> coexist immediately (no DB query)."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="Some random fact",
            subject=None,
            importance=5,
        )

        result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "coexist"
        assert len(result.contradicts) == 0
        assert "No subject" in result.reason
        # Verify no DB call was made
        session.execute.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coexist_when_no_existing_memories_with_same_subject(self) -> None:
        """No existing memories match the subject -> coexist."""
        session = _mock_session_with_results([])  # empty result
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="A brand new topic",
            subject="new.topic",
            importance=5,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "coexist"
        assert len(result.contradicts) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_semantic_similarity_detects_contradiction(self) -> None:
        """Semantic similarity in range (0.7-0.92) with different content -> contradiction."""
        # No subject-based matches
        session = _mock_session_with_results([])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="Cats are the best pets",
            subject="pet.preference",
            importance=5,
        )

        # Build a semantic match: similarity 0.85 (between 0.7 and 0.92), different content
        sem_match = _make_mock_memory_orm(
            content="Dogs are the best pets",
            subject="pet.preference",
            importance=5,
        )
        semantic_results: list[tuple[MagicMock, float]] = [(sem_match, 0.85)]

        with patch.object(
            detector._repo,
            "search_by_embedding",
            new_callable=AsyncMock,
            return_value=semantic_results,
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert result.action == "dispute"
        assert sem_match.id in result.contradicts

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_semantic_similarity_above_dedup_threshold_ignored(self) -> None:
        """Similarity >= 0.92 is a near-duplicate and should not flag contradiction."""
        session = _mock_session_with_results([])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="The server runs on port 8080",
            subject="server.port",
            importance=5,
        )

        near_dup = _make_mock_memory_orm(
            content="Server is on port 8080 actually",
            subject="server.port",
            importance=5,
        )
        semantic_results: list[tuple[MagicMock, float]] = [(near_dup, 0.95)]

        with patch.object(
            detector._repo,
            "search_by_embedding",
            new_callable=AsyncMock,
            return_value=semantic_results,
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert near_dup.id not in result.contradicts

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_semantic_similarity_below_threshold_ignored(self) -> None:
        """Similarity below 0.7 should not flag contradiction."""
        session = _mock_session_with_results([])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="The database uses PostgreSQL",
            subject="db.engine",
            importance=5,
        )

        low_sim = _make_mock_memory_orm(
            content="We use Redis for caching",
            subject="cache.engine",
            importance=5,
        )
        semantic_results: list[tuple[MagicMock, float]] = [(low_sim, 0.4)]

        with patch.object(
            detector._repo,
            "search_by_embedding",
            new_callable=AsyncMock,
            return_value=semantic_results,
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert low_sim.id not in result.contradicts

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_semantic_skips_already_flagged_ids(self) -> None:
        """Semantic check skips IDs already flagged by subject match."""
        existing = _make_mock_memory_orm(
            content="Use Python 3.11",
            subject="python.version",
            importance=5,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="Use Python 3.13",
            subject="python.version",
            importance=8,
        )

        # Same ID appears in semantic results -- should be skipped
        semantic_results: list[tuple[MagicMock, float]] = [(existing, 0.8)]

        with patch.object(
            detector._repo,
            "search_by_embedding",
            new_callable=AsyncMock,
            return_value=semantic_results,
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        # existing.id should appear only once (from subject match, not duplicated from semantic)
        assert result.contradicts.count(existing.id) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_supersede_reason_includes_importance_values(self) -> None:
        """Verify supersede reason contains both importance values."""
        existing = _make_mock_memory_orm(
            content="Old approach",
            subject="approach",
            importance=3,
        )
        session = _mock_session_with_results([existing])
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        new_memory = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="New approach",
            subject="approach",
            importance=9,
        )

        with patch.object(
            detector._repo, "search_by_embedding", new_callable=AsyncMock, return_value=[]
        ):
            result = await detector.check_on_store(new_memory=new_memory, team_id=uuid4())

        assert "importance=9" in result.reason
        assert "importance=3" in result.reason


# ---------------------------------------------------------------------------
# check_on_retrieve tests
# ---------------------------------------------------------------------------


class TestCheckOnRetrieve:
    """Tests for ContradictionDetector.check_on_retrieve."""

    @pytest.mark.unit
    def test_contradiction_detected_same_subject_different_content(self) -> None:
        """Two memories with same subject, different content -> 1 contradiction."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("The sky is blue", subject="sky.color")
        mem_b = _make_scored_memory("The sky is green", subject="sky.color")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 1
        assert isinstance(contradictions[0], Contradiction)
        ids = {contradictions[0].memory_a, contradictions[0].memory_b}
        assert ids == {mem_a.memory.id, mem_b.memory.id}

    @pytest.mark.unit
    def test_no_contradiction_same_subject_same_content(self) -> None:
        """Two memories with same subject, same content -> no contradiction."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("The sky is blue", subject="sky.color")
        mem_b = _make_scored_memory("  the sky is blue  ", subject="sky.color")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_no_contradiction_different_subjects(self) -> None:
        """Memories with different subjects -> no contradiction."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("The sky is blue", subject="sky.color")
        mem_b = _make_scored_memory("The grass is green", subject="grass.color")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_no_contradiction_no_subject(self) -> None:
        """Memories with no subject -> no contradiction (skipped during grouping)."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Some fact A", subject=None)
        mem_b = _make_scored_memory("Some fact B", subject=None)

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_multiple_contradictions_three_memories_same_subject(self) -> None:
        """Three memories, same subject, all different content -> 3 contradictions (pairwise)."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Python is version 3.11", subject="python.version")
        mem_b = _make_scored_memory("Python is version 3.12", subject="python.version")
        mem_c = _make_scored_memory("Python is version 3.13", subject="python.version")

        contradictions = detector.check_on_retrieve([mem_a, mem_b, mem_c])

        # C(3,2) = 3 pairwise contradictions
        assert len(contradictions) == 3

    @pytest.mark.unit
    def test_subject_grouping_is_case_insensitive(self) -> None:
        """Subjects are normalized (lowercased, stripped) for grouping."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Value A", subject="User.Theme")
        mem_b = _make_scored_memory("Value B", subject="  user.theme  ")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 1

    @pytest.mark.unit
    def test_empty_memories_list_returns_no_contradictions(self) -> None:
        """Empty input list returns empty contradictions list."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        contradictions = detector.check_on_retrieve([])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_single_memory_returns_no_contradictions(self) -> None:
        """A single memory cannot contradict itself."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem = _make_scored_memory("Only memory", subject="solo.topic")

        contradictions = detector.check_on_retrieve([mem])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_contradiction_reason_contains_content_snippets(self) -> None:
        """Contradiction reason should include truncated content from both memories."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Apples are red", subject="fruit.color")
        mem_b = _make_scored_memory("Apples are green", subject="fruit.color")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 1
        assert "Apples are red" in contradictions[0].reason
        assert "Apples are green" in contradictions[0].reason

    @pytest.mark.unit
    def test_empty_string_subject_is_skipped(self) -> None:
        """Memories with empty-string subject are treated as no-subject."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Fact A", subject="")
        mem_b = _make_scored_memory("Fact B", subject="   ")

        contradictions = detector.check_on_retrieve([mem_a, mem_b])

        assert len(contradictions) == 0

    @pytest.mark.unit
    def test_mixed_subjects_only_same_subject_contradicts(self) -> None:
        """Only memories sharing a subject are compared; cross-subject pairs are ignored."""
        session = AsyncMock()
        embedding_svc = _mock_embedding_service()
        detector = _make_detector(session, embedding_svc)

        mem_a = _make_scored_memory("Dark mode enabled", subject="ui.theme")
        mem_b = _make_scored_memory("Light mode enabled", subject="ui.theme")
        mem_c = _make_scored_memory("Uses PostgreSQL", subject="db.engine")
        mem_d = _make_scored_memory("Uses MySQL", subject="db.engine")

        contradictions = detector.check_on_retrieve([mem_a, mem_b, mem_c, mem_d])

        assert len(contradictions) == 2
        subjects_in_reasons = [c.reason for c in contradictions]
        assert any("ui.theme" in r for r in subjects_in_reasons)
        assert any("db.engine" in r for r in subjects_in_reasons)
