"""Unit tests for TokenBudgetManager in src/memory/token_budget.py."""

import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.memory.token_budget import TokenBudgetManager
from src.memory.types import BudgetAllocation, ScoredMemory
from src.models.memory_models import (
    MemoryRecord,
    MemorySource,
    MemoryStatus,
    MemoryTier,
    MemoryType,
)


def _make_scored_memory(
    memory_type: MemoryType = MemoryType.SEMANTIC,
    content: str = "test content",
    score: float = 0.5,
    is_pinned: bool = False,
) -> ScoredMemory:
    """Build a ScoredMemory with sensible defaults.

    Args:
        memory_type: The memory type classification.
        content: The memory content text.
        score: The composite retrieval score.
        is_pinned: Whether the memory is pinned.

    Returns:
        A ScoredMemory instance.
    """
    now = datetime.now(tz=timezone.utc)
    return ScoredMemory(
        memory=MemoryRecord(
            id=uuid4(),
            team_id=uuid4(),
            memory_type=memory_type,
            content=content,
            importance=5,
            confidence=1.0,
            source_type=MemorySource.EXTRACTION,
            version=1,
            tier=MemoryTier.WARM,
            status=MemoryStatus.ACTIVE,
            is_pinned=is_pinned,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        ),
        final_score=score,
    )


class TestEstimateTokens:
    """Tests for TokenBudgetManager.estimate_tokens."""

    @pytest.mark.unit
    def test_estimate_tokens_accuracy(self) -> None:
        """Test that 'hello world' (11 chars) yields ceil(11/3.5) = 4 tokens."""
        manager = TokenBudgetManager()
        result = manager.estimate_tokens("hello world")
        expected = math.ceil(11 / 3.5)  # 4
        assert result == expected

    @pytest.mark.unit
    def test_estimate_tokens_empty_string_returns_zero(self) -> None:
        """Test that an empty string returns 0 tokens."""
        manager = TokenBudgetManager()
        assert manager.estimate_tokens("") == 0

    @pytest.mark.unit
    def test_estimate_tokens_single_char(self) -> None:
        """Test that a single character returns 1 token."""
        manager = TokenBudgetManager()
        assert manager.estimate_tokens("a") == math.ceil(1 / 3.5)  # 1


class TestAllocate:
    """Tests for TokenBudgetManager.allocate."""

    @pytest.mark.unit
    def test_identity_always_included_even_with_tiny_budget(self) -> None:
        """Test that identity memories are always included even when budget is tiny."""
        manager = TokenBudgetManager(total_budget=10)
        identity_content = "a" * 1000  # Way over budget
        identity_mem = _make_scored_memory(
            memory_type=MemoryType.IDENTITY,
            content=identity_content,
            score=0.9,
        )

        included, allocation = manager.allocate([identity_mem], budget=10)

        assert len(included) == 1
        assert included[0].memory.memory_type == MemoryType.IDENTITY
        assert allocation.identity_tokens > 10  # Exceeds budget but still included

    @pytest.mark.unit
    def test_allocation_priority_order(self) -> None:
        """Test that allocation follows identity -> pinned -> profile -> score priority."""
        manager = TokenBudgetManager(total_budget=5000)

        identity = _make_scored_memory(
            memory_type=MemoryType.IDENTITY, content="I am an agent", score=0.1
        )
        pinned = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC, content="pinned fact", score=0.2, is_pinned=True
        )
        profile = _make_scored_memory(
            memory_type=MemoryType.USER_PROFILE, content="user likes python", score=0.3
        )
        remaining_high = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC, content="high score", score=0.9
        )
        remaining_low = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC, content="low score", score=0.1
        )

        all_memories = [remaining_low, profile, remaining_high, identity, pinned]
        included, allocation = manager.allocate(all_memories)

        # All should fit in 5000 tokens budget
        assert len(included) == 5

        # Verify order: identity first, then pinned, then profile, then remaining by score desc
        assert included[0].memory.memory_type == MemoryType.IDENTITY
        assert included[1].memory.is_pinned is True
        assert included[2].memory.memory_type == MemoryType.USER_PROFILE
        # Remaining sorted by score descending
        assert included[3].final_score >= included[4].final_score

    @pytest.mark.unit
    def test_over_budget_trims_lowest_score_first(self) -> None:
        """Test that lowest-score memories are trimmed when budget is exceeded."""
        manager = TokenBudgetManager(total_budget=10)

        mem_high = _make_scored_memory(memory_type=MemoryType.SEMANTIC, content="hi", score=0.9)
        mem_low = _make_scored_memory(memory_type=MemoryType.SEMANTIC, content="lo", score=0.1)
        mem_big = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC,
            content="x" * 100,  # ceil(100/3.5) = 29 tokens
            score=0.2,
        )

        included, allocation = manager.allocate([mem_high, mem_low, mem_big], budget=10)

        # Remaining sorted by score: high(0.9), big(0.2), low(0.1) -- greedy fill
        # The big one should be trimmed because it doesn't fit after mem_high
        assert allocation.memories_trimmed >= 1
        assert len(included) < 3

    @pytest.mark.unit
    def test_warning_logged_when_identity_exceeds_budget(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that a warning is logged when identity tokens exceed the budget."""
        manager = TokenBudgetManager(total_budget=5)
        identity = _make_scored_memory(
            memory_type=MemoryType.IDENTITY,
            content="a" * 100,  # ceil(100/3.5) = 29 tokens, way over budget=5
            score=0.9,
        )

        with caplog.at_level(logging.WARNING, logger="src.memory.token_budget"):
            included, allocation = manager.allocate([identity], budget=5)

        assert len(included) == 1  # Identity still included
        assert allocation.identity_tokens > 5
        assert any("exceeds budget" in record.message for record in caplog.records)

    @pytest.mark.unit
    def test_budget_allocation_fields_correct(self) -> None:
        """Test that BudgetAllocation fields are computed correctly."""
        manager = TokenBudgetManager(total_budget=5000)

        identity = _make_scored_memory(
            memory_type=MemoryType.IDENTITY, content="identity", score=0.9
        )
        pinned = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC, content="pinned", score=0.5, is_pinned=True
        )
        profile = _make_scored_memory(
            memory_type=MemoryType.USER_PROFILE, content="profile", score=0.5
        )
        remaining = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC, content="remaining", score=0.3
        )

        included, allocation = manager.allocate([identity, pinned, profile, remaining])

        assert isinstance(allocation, BudgetAllocation)
        assert allocation.identity_tokens == manager.estimate_tokens("identity")
        assert allocation.pinned_tokens == manager.estimate_tokens("pinned")
        assert allocation.profile_tokens == manager.estimate_tokens("profile")
        assert allocation.remaining_tokens == manager.estimate_tokens("remaining")
        assert allocation.total_tokens == (
            allocation.identity_tokens
            + allocation.pinned_tokens
            + allocation.profile_tokens
            + allocation.remaining_tokens
        )
        assert allocation.memories_included == 4
        assert allocation.memories_trimmed == 0

    @pytest.mark.unit
    def test_pinned_trimmed_when_no_budget_left(self) -> None:
        """Test that pinned memories are trimmed when budget is consumed by identity."""
        manager = TokenBudgetManager(total_budget=5)

        identity = _make_scored_memory(
            memory_type=MemoryType.IDENTITY,
            content="a" * 100,  # 29 tokens, exceeds budget
            score=0.9,
        )
        pinned = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC,
            content="pinned info",
            score=0.5,
            is_pinned=True,
        )

        included, allocation = manager.allocate([identity, pinned], budget=5)

        # Identity is always included, but pinned is trimmed
        assert len(included) == 1
        assert included[0].memory.memory_type == MemoryType.IDENTITY
        assert allocation.memories_trimmed == 1

    @pytest.mark.unit
    def test_budget_override_parameter(self) -> None:
        """Test that the budget parameter overrides the default total_budget."""
        manager = TokenBudgetManager(total_budget=5000)
        mem = _make_scored_memory(
            memory_type=MemoryType.SEMANTIC,
            content="x" * 100,  # 29 tokens
            score=0.5,
        )

        # With default budget (5000) it fits
        included_large, _ = manager.allocate([mem])
        assert len(included_large) == 1

        # With tiny override budget it doesn't fit
        included_tiny, alloc_tiny = manager.allocate([mem], budget=1)
        assert len(included_tiny) == 0
        assert alloc_tiny.memories_trimmed == 1
