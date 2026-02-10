"""Unit tests for Phase 2 memory Pydantic models in src/memory/types.py."""

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.memory.types import (
    BudgetAllocation,
    CompactionResult,
    Contradiction,
    ContradictionResult,
    ExtractionResult,
    ExtractedMemory,
    MemorySnapshot,
    RetrievalResult,
    RetrievalStats,
    ScoredMemory,
)
from src.models.memory_models import (
    MemoryRecord,
    MemoryType,
)


# ---------------------------------------------------------------------------
# ScoredMemory
# ---------------------------------------------------------------------------


class TestScoredMemory:
    """Tests for ScoredMemory model."""

    @pytest.mark.unit
    def test_scored_memory_wraps_record(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that ScoredMemory wraps a MemoryRecord correctly."""
        record = sample_memory_record()
        scored = ScoredMemory(memory=record, final_score=0.85)

        assert scored.memory is record
        assert scored.memory.content == record.content
        assert scored.memory.id == record.id

    @pytest.mark.unit
    def test_scored_memory_final_score_boundaries(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that final_score accepts 0.0 and 1.0."""
        record = sample_memory_record()
        low = ScoredMemory(memory=record, final_score=0.0)
        high = ScoredMemory(memory=record, final_score=1.0)
        assert low.final_score == 0.0
        assert high.final_score == 1.0

    @pytest.mark.unit
    def test_scored_memory_final_score_too_low(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that final_score < 0.0 raises ValidationError."""
        record = sample_memory_record()
        with pytest.raises(ValidationError):
            ScoredMemory(memory=record, final_score=-0.1)

    @pytest.mark.unit
    def test_scored_memory_final_score_too_high(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that final_score > 1.0 raises ValidationError."""
        record = sample_memory_record()
        with pytest.raises(ValidationError):
            ScoredMemory(memory=record, final_score=1.1)

    @pytest.mark.unit
    def test_scored_memory_signal_scores_default_empty(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that signal_scores defaults to empty dict."""
        record = sample_memory_record()
        scored = ScoredMemory(memory=record, final_score=0.5)
        assert scored.signal_scores == {}

    @pytest.mark.unit
    def test_scored_memory_signal_scores_populated(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that signal_scores can hold per-signal breakdown."""
        record = sample_memory_record()
        signals = {
            "semantic": 0.9,
            "recency": 0.7,
            "importance": 0.8,
            "continuity": 0.3,
            "relationship": 0.1,
        }
        scored = ScoredMemory(memory=record, final_score=0.72, signal_scores=signals)
        assert scored.signal_scores == signals
        assert scored.signal_scores["semantic"] == 0.9

    @pytest.mark.unit
    def test_scored_memory_missing_required_memory(self) -> None:
        """Test that missing memory field raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoredMemory(final_score=0.5)  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_scored_memory_missing_required_final_score(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test that missing final_score raises ValidationError."""
        record = sample_memory_record()
        with pytest.raises(ValidationError):
            ScoredMemory(memory=record)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RetrievalStats
# ---------------------------------------------------------------------------


class TestRetrievalStats:
    """Tests for RetrievalStats model."""

    @pytest.mark.unit
    def test_retrieval_stats_creation(self) -> None:
        """Test basic creation with required fields."""
        stats = RetrievalStats(signals_hit=3, cache_hit=False, total_ms=42.5, query_tokens=15)
        assert stats.signals_hit == 3
        assert stats.cache_hit is False
        assert stats.total_ms == 42.5
        assert stats.query_tokens == 15

    @pytest.mark.unit
    def test_retrieval_stats_cache_hit_default(self) -> None:
        """Test that cache_hit defaults to False."""
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        assert stats.cache_hit is False

    @pytest.mark.unit
    def test_retrieval_stats_signals_hit_ge_zero(self) -> None:
        """Test that signals_hit=0 is valid."""
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        assert stats.signals_hit == 0

    @pytest.mark.unit
    def test_retrieval_stats_signals_hit_negative(self) -> None:
        """Test that signals_hit < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalStats(signals_hit=-1, total_ms=10.0, query_tokens=5)

    @pytest.mark.unit
    def test_retrieval_stats_total_ms_negative(self) -> None:
        """Test that total_ms < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalStats(signals_hit=1, total_ms=-1.0, query_tokens=5)

    @pytest.mark.unit
    def test_retrieval_stats_query_tokens_negative(self) -> None:
        """Test that query_tokens < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=-1)

    @pytest.mark.unit
    def test_retrieval_stats_missing_required_fields(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalStats(signals_hit=1, total_ms=10.0)  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            RetrievalStats(signals_hit=1, query_tokens=5)  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            RetrievalStats(total_ms=10.0, query_tokens=5)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Contradiction
# ---------------------------------------------------------------------------


class TestContradiction:
    """Tests for Contradiction model."""

    @pytest.mark.unit
    def test_contradiction_creation(self) -> None:
        """Test basic creation with two memory UUIDs and a reason."""
        a_id = uuid4()
        b_id = uuid4()
        c = Contradiction(memory_a=a_id, memory_b=b_id, reason="Conflicting user preferences")
        assert c.memory_a == a_id
        assert c.memory_b == b_id
        assert c.reason == "Conflicting user preferences"

    @pytest.mark.unit
    def test_contradiction_missing_required_fields(self) -> None:
        """Test that all three fields are required."""
        with pytest.raises(ValidationError):
            Contradiction(memory_a=uuid4(), memory_b=uuid4())  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            Contradiction(memory_a=uuid4(), reason="test")  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            Contradiction(memory_b=uuid4(), reason="test")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RetrievalResult
# ---------------------------------------------------------------------------


class TestRetrievalResult:
    """Tests for RetrievalResult model."""

    @pytest.mark.unit
    def test_retrieval_result_requires_stats(self) -> None:
        """Test that stats field is required."""
        with pytest.raises(ValidationError):
            RetrievalResult()  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_retrieval_result_with_stats(self) -> None:
        """Test creation with required stats and defaults."""
        stats = RetrievalStats(signals_hit=2, total_ms=35.0, query_tokens=10)
        result = RetrievalResult(stats=stats)
        assert result.stats is stats
        assert result.memories == []
        assert result.formatted_prompt == ""
        assert result.contradictions == []

    @pytest.mark.unit
    def test_retrieval_result_with_memories(
        self, sample_memory_record: Callable[..., MemoryRecord]
    ) -> None:
        """Test RetrievalResult populated with scored memories."""
        record = sample_memory_record()
        scored = ScoredMemory(memory=record, final_score=0.9)
        stats = RetrievalStats(signals_hit=5, total_ms=50.0, query_tokens=20)
        result = RetrievalResult(
            memories=[scored],
            formatted_prompt="## Memory\nUser prefers dark mode.",
            stats=stats,
        )
        assert len(result.memories) == 1
        assert result.memories[0].final_score == 0.9
        assert "dark mode" in result.formatted_prompt

    @pytest.mark.unit
    def test_retrieval_result_with_contradictions(self) -> None:
        """Test RetrievalResult with contradictions populated."""
        stats = RetrievalStats(signals_hit=3, total_ms=25.0, query_tokens=8)
        contradiction = Contradiction(memory_a=uuid4(), memory_b=uuid4(), reason="Conflicting info")
        result = RetrievalResult(stats=stats, contradictions=[contradiction])
        assert len(result.contradictions) == 1
        assert result.contradictions[0].reason == "Conflicting info"


# ---------------------------------------------------------------------------
# ContradictionResult
# ---------------------------------------------------------------------------


class TestContradictionResult:
    """Tests for ContradictionResult model."""

    @pytest.mark.unit
    def test_contradiction_result_supersede(self) -> None:
        """Test creation with action='supersede'."""
        cr = ContradictionResult(
            contradicts=[uuid4()],
            action="supersede",
            reason="New information is more recent",
        )
        assert cr.action == "supersede"
        assert len(cr.contradicts) == 1

    @pytest.mark.unit
    def test_contradiction_result_dispute(self) -> None:
        """Test creation with action='dispute'."""
        cr = ContradictionResult(contradicts=[], action="dispute", reason="Sources disagree")
        assert cr.action == "dispute"
        assert cr.contradicts == []

    @pytest.mark.unit
    def test_contradiction_result_coexist(self) -> None:
        """Test creation with action='coexist'."""
        cr = ContradictionResult(contradicts=[], action="coexist", reason="Both can be true")
        assert cr.action == "coexist"

    @pytest.mark.unit
    def test_contradiction_result_invalid_action(self) -> None:
        """Test that an invalid action value raises ValidationError."""
        with pytest.raises(ValidationError):
            ContradictionResult(
                contradicts=[],
                action="delete",
                reason="Invalid",  # type: ignore[arg-type]
            )

    @pytest.mark.unit
    def test_contradiction_result_missing_required_fields(self) -> None:
        """Test that action and reason are required."""
        with pytest.raises(ValidationError):
            ContradictionResult(contradicts=[], reason="Missing action")  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            ContradictionResult(contradicts=[], action="supersede")  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_contradiction_result_contradicts_default(self) -> None:
        """Test that contradicts defaults to empty list."""
        cr = ContradictionResult(action="coexist", reason="No conflict")
        assert cr.contradicts == []


# ---------------------------------------------------------------------------
# CompactionResult
# ---------------------------------------------------------------------------


class TestCompactionResult:
    """Tests for CompactionResult model."""

    @pytest.mark.unit
    def test_compaction_result_creation(self) -> None:
        """Test basic creation with valid values."""
        cr = CompactionResult(
            memories_extracted=5,
            summary="Extracted 5 memories from conversation.",
            pass1_count=3,
            pass2_additions=2,
        )
        assert cr.memories_extracted == 5
        assert cr.pass1_count == 3
        assert cr.pass2_additions == 2
        assert "Extracted" in cr.summary

    @pytest.mark.unit
    def test_compaction_result_zero_values(self) -> None:
        """Test that all ge=0 fields accept zero."""
        cr = CompactionResult(
            memories_extracted=0,
            summary="Nothing to compact.",
            pass1_count=0,
            pass2_additions=0,
        )
        assert cr.memories_extracted == 0
        assert cr.pass1_count == 0
        assert cr.pass2_additions == 0

    @pytest.mark.unit
    def test_compaction_result_negative_memories_extracted(self) -> None:
        """Test that memories_extracted < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CompactionResult(
                memories_extracted=-1,
                summary="Bad",
                pass1_count=0,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_compaction_result_negative_pass1_count(self) -> None:
        """Test that pass1_count < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CompactionResult(
                memories_extracted=0,
                summary="Bad",
                pass1_count=-1,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_compaction_result_negative_pass2_additions(self) -> None:
        """Test that pass2_additions < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CompactionResult(
                memories_extracted=0,
                summary="Bad",
                pass1_count=0,
                pass2_additions=-1,
            )

    @pytest.mark.unit
    def test_compaction_result_missing_summary(self) -> None:
        """Test that summary is required."""
        with pytest.raises(ValidationError):
            CompactionResult(memories_extracted=0, pass1_count=0, pass2_additions=0)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    @pytest.mark.unit
    def test_extraction_result_creation(self) -> None:
        """Test basic creation with valid values."""
        er = ExtractionResult(
            memories_created=3,
            memories_versioned=1,
            duplicates_skipped=2,
            contradictions_found=0,
            pass1_count=4,
            pass2_additions=2,
        )
        assert er.memories_created == 3
        assert er.memories_versioned == 1
        assert er.duplicates_skipped == 2
        assert er.contradictions_found == 0
        assert er.pass1_count == 4
        assert er.pass2_additions == 2

    @pytest.mark.unit
    def test_extraction_result_all_zeros(self) -> None:
        """Test that all fields accept zero."""
        er = ExtractionResult(
            memories_created=0,
            memories_versioned=0,
            duplicates_skipped=0,
            contradictions_found=0,
            pass1_count=0,
            pass2_additions=0,
        )
        assert er.memories_created == 0

    @pytest.mark.unit
    def test_extraction_result_negative_memories_created(self) -> None:
        """Test that memories_created < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                memories_created=-1,
                memories_versioned=0,
                duplicates_skipped=0,
                contradictions_found=0,
                pass1_count=0,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_extraction_result_negative_memories_versioned(self) -> None:
        """Test that memories_versioned < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                memories_created=0,
                memories_versioned=-1,
                duplicates_skipped=0,
                contradictions_found=0,
                pass1_count=0,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_extraction_result_negative_duplicates_skipped(self) -> None:
        """Test that duplicates_skipped < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                memories_created=0,
                memories_versioned=0,
                duplicates_skipped=-1,
                contradictions_found=0,
                pass1_count=0,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_extraction_result_negative_contradictions_found(self) -> None:
        """Test that contradictions_found < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                memories_created=0,
                memories_versioned=0,
                duplicates_skipped=0,
                contradictions_found=-1,
                pass1_count=0,
                pass2_additions=0,
            )

    @pytest.mark.unit
    def test_extraction_result_missing_required_fields(self) -> None:
        """Test that all 6 fields are required."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                memories_created=0,
                memories_versioned=0,
                duplicates_skipped=0,
                contradictions_found=0,
                pass1_count=0,
                # missing pass2_additions
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ExtractedMemory
# ---------------------------------------------------------------------------


class TestExtractedMemory:
    """Tests for ExtractedMemory model."""

    @pytest.mark.unit
    def test_extracted_memory_creation(self) -> None:
        """Test basic creation with required fields."""
        em = ExtractedMemory(
            type=MemoryType.SEMANTIC,
            content="User likes Python.",
        )
        assert em.type == MemoryType.SEMANTIC
        assert em.content == "User likes Python."

    @pytest.mark.unit
    def test_extracted_memory_defaults(self) -> None:
        """Test default values: importance=5, confidence=1.0, subject=None."""
        em = ExtractedMemory(
            type=MemoryType.EPISODIC,
            content="Had a meeting.",
        )
        assert em.importance == 5
        assert em.confidence == 1.0
        assert em.subject is None

    @pytest.mark.unit
    def test_extracted_memory_importance_range_1_to_10(self) -> None:
        """Test that importance accepts boundary values 1 and 10."""
        low = ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", importance=1)
        high = ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", importance=10)
        assert low.importance == 1
        assert high.importance == 10

    @pytest.mark.unit
    def test_extracted_memory_importance_too_low(self) -> None:
        """Test that importance < 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", importance=0)

    @pytest.mark.unit
    def test_extracted_memory_importance_too_high(self) -> None:
        """Test that importance > 10 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", importance=11)

    @pytest.mark.unit
    def test_extracted_memory_confidence_range_0_to_1(self) -> None:
        """Test that confidence accepts boundary values 0.0 and 1.0."""
        low = ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", confidence=0.0)
        high = ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", confidence=1.0)
        assert low.confidence == 0.0
        assert high.confidence == 1.0

    @pytest.mark.unit
    def test_extracted_memory_confidence_too_low(self) -> None:
        """Test that confidence < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", confidence=-0.1)

    @pytest.mark.unit
    def test_extracted_memory_confidence_too_high(self) -> None:
        """Test that confidence > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ExtractedMemory(type=MemoryType.SEMANTIC, content="Test", confidence=1.1)

    @pytest.mark.unit
    def test_extracted_memory_with_subject(self) -> None:
        """Test creation with optional subject field."""
        em = ExtractedMemory(
            type=MemoryType.USER_PROFILE,
            content="User prefers dark mode",
            subject="preferences",
        )
        assert em.subject == "preferences"

    @pytest.mark.unit
    def test_extracted_memory_all_memory_types(self) -> None:
        """Test that all 7 MemoryType values are accepted."""
        for mt in MemoryType:
            em = ExtractedMemory(type=mt, content=f"Test {mt.value}")
            assert em.type == mt


# ---------------------------------------------------------------------------
# MemorySnapshot
# ---------------------------------------------------------------------------


class TestMemorySnapshot:
    """Tests for MemorySnapshot model."""

    @pytest.mark.unit
    def test_memory_snapshot_creation(self) -> None:
        """Test basic creation with all required fields."""
        now = datetime.now(tz=timezone.utc)
        ms = MemorySnapshot(
            memory_id=uuid4(),
            content="Snapshot content",
            status="active",
            tier="warm",
            timestamp=now,
        )
        assert ms.content == "Snapshot content"
        assert ms.status == "active"
        assert ms.tier == "warm"
        assert ms.timestamp == now

    @pytest.mark.unit
    def test_memory_snapshot_missing_required_fields(self) -> None:
        """Test that all fields are required."""
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError):
            MemorySnapshot(content="Test", status="active", tier="warm", timestamp=now)  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            MemorySnapshot(memory_id=uuid4(), status="active", tier="warm", timestamp=now)  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_memory_snapshot_accepts_any_status_string(self) -> None:
        """Test that status accepts any string (not restricted to enum)."""
        now = datetime.now(tz=timezone.utc)
        ms = MemorySnapshot(
            memory_id=uuid4(),
            content="Test",
            status="superseded",
            tier="cold",
            timestamp=now,
        )
        assert ms.status == "superseded"
        assert ms.tier == "cold"


# ---------------------------------------------------------------------------
# BudgetAllocation
# ---------------------------------------------------------------------------


class TestBudgetAllocation:
    """Tests for BudgetAllocation model."""

    @pytest.mark.unit
    def test_budget_allocation_creation(self) -> None:
        """Test basic creation with valid values."""
        ba = BudgetAllocation(
            identity_tokens=200,
            pinned_tokens=100,
            profile_tokens=150,
            remaining_tokens=550,
            total_tokens=1000,
            memories_included=8,
            memories_trimmed=3,
        )
        assert ba.identity_tokens == 200
        assert ba.pinned_tokens == 100
        assert ba.profile_tokens == 150
        assert ba.remaining_tokens == 550
        assert ba.total_tokens == 1000
        assert ba.memories_included == 8
        assert ba.memories_trimmed == 3

    @pytest.mark.unit
    def test_budget_allocation_all_zeros(self) -> None:
        """Test that all fields accept zero."""
        ba = BudgetAllocation(
            identity_tokens=0,
            pinned_tokens=0,
            profile_tokens=0,
            remaining_tokens=0,
            total_tokens=0,
            memories_included=0,
            memories_trimmed=0,
        )
        assert ba.total_tokens == 0
        assert ba.memories_included == 0

    @pytest.mark.unit
    def test_budget_allocation_negative_identity_tokens(self) -> None:
        """Test that identity_tokens < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=-1,
                pinned_tokens=0,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=0,
                memories_included=0,
                memories_trimmed=0,
            )

    @pytest.mark.unit
    def test_budget_allocation_negative_pinned_tokens(self) -> None:
        """Test that pinned_tokens < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=0,
                pinned_tokens=-1,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=0,
                memories_included=0,
                memories_trimmed=0,
            )

    @pytest.mark.unit
    def test_budget_allocation_negative_total_tokens(self) -> None:
        """Test that total_tokens < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=0,
                pinned_tokens=0,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=-1,
                memories_included=0,
                memories_trimmed=0,
            )

    @pytest.mark.unit
    def test_budget_allocation_negative_memories_included(self) -> None:
        """Test that memories_included < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=0,
                pinned_tokens=0,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=0,
                memories_included=-1,
                memories_trimmed=0,
            )

    @pytest.mark.unit
    def test_budget_allocation_negative_memories_trimmed(self) -> None:
        """Test that memories_trimmed < 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=0,
                pinned_tokens=0,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=0,
                memories_included=0,
                memories_trimmed=-1,
            )

    @pytest.mark.unit
    def test_budget_allocation_missing_required_fields(self) -> None:
        """Test that all 7 fields are required (no defaults)."""
        with pytest.raises(ValidationError):
            BudgetAllocation(
                identity_tokens=0,
                pinned_tokens=0,
                profile_tokens=0,
                remaining_tokens=0,
                total_tokens=0,
                memories_included=0,
                # missing memories_trimmed
            )  # type: ignore[call-arg]
