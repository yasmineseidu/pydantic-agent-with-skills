"""Token budget manager for memory injection into system prompts."""

import logging
import math

from src.memory.types import BudgetAllocation, ScoredMemory
from src.models.memory_models import MemoryType

logger = logging.getLogger(__name__)


class TokenBudgetManager:
    """Manages token budget allocation for memory injection.

    Prioritizes memories by category (identity > pinned > profile > scored)
    and greedily fills the budget. Identity memories are NEVER trimmed.

    Args:
        total_budget: Maximum tokens available for memory injection.
    """

    def __init__(self, total_budget: int = 2000) -> None:
        self._total_budget = total_budget

    def estimate_tokens(self, text: str) -> int:
        """Estimate the token count for a text string.

        Uses a len(text) / 3.5 heuristic, rounded up.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count (always >= 1 for non-empty text).
        """
        if not text:
            return 0
        return math.ceil(len(text) / 3.5)

    def allocate(
        self,
        memories: list[ScoredMemory],
        budget: int | None = None,
    ) -> tuple[list[ScoredMemory], BudgetAllocation]:
        """Allocate token budget across memories by priority category.

        Priority order:
        1. Identity memories (NEVER trimmed, always included)
        2. Pinned memories
        3. User profile memories
        4. Remaining memories sorted by final_score descending

        Args:
            memories: Scored memories to allocate budget for.
            budget: Token budget override. Uses total_budget if None.

        Returns:
            Tuple of (included_memories, allocation) where included_memories
            are the memories that fit within the budget and allocation tracks
            the token breakdown by category.
        """
        effective_budget = budget if budget is not None else self._total_budget

        # Categorize memories
        identity: list[ScoredMemory] = []
        pinned: list[ScoredMemory] = []
        profile: list[ScoredMemory] = []
        remaining: list[ScoredMemory] = []

        for mem in memories:
            if mem.memory.memory_type == MemoryType.IDENTITY:
                identity.append(mem)
            elif mem.memory.is_pinned:
                pinned.append(mem)
            elif mem.memory.memory_type == MemoryType.USER_PROFILE:
                profile.append(mem)
            else:
                remaining.append(mem)

        # Sort remaining by score descending for greedy fill
        remaining.sort(key=lambda m: m.final_score, reverse=True)

        included: list[ScoredMemory] = []
        identity_tokens = 0
        pinned_tokens = 0
        profile_tokens = 0
        remaining_tokens = 0
        tokens_used = 0
        trimmed_count = 0

        # Step 1: Identity memories -- ALWAYS included, never trimmed
        for mem in identity:
            tokens = self.estimate_tokens(mem.memory.content)
            identity_tokens += tokens
            tokens_used += tokens
            included.append(mem)

        if identity_tokens > effective_budget:
            logger.warning(
                "allocate: identity_tokens=%d exceeds budget=%d, identity memories included anyway",
                identity_tokens,
                effective_budget,
            )

        # Step 2: Pinned memories -- high priority, fill greedily
        for mem in pinned:
            tokens = self.estimate_tokens(mem.memory.content)
            if tokens_used + tokens <= effective_budget:
                pinned_tokens += tokens
                tokens_used += tokens
                included.append(mem)
            else:
                trimmed_count += 1

        # Step 3: User profile memories
        for mem in profile:
            tokens = self.estimate_tokens(mem.memory.content)
            if tokens_used + tokens <= effective_budget:
                profile_tokens += tokens
                tokens_used += tokens
                included.append(mem)
            else:
                trimmed_count += 1

        # Step 4: Remaining memories by score descending
        for mem in remaining:
            tokens = self.estimate_tokens(mem.memory.content)
            if tokens_used + tokens <= effective_budget:
                remaining_tokens += tokens
                tokens_used += tokens
                included.append(mem)
            else:
                trimmed_count += 1

        allocation = BudgetAllocation(
            identity_tokens=identity_tokens,
            pinned_tokens=pinned_tokens,
            profile_tokens=profile_tokens,
            remaining_tokens=remaining_tokens,
            total_tokens=tokens_used,
            memories_included=len(included),
            memories_trimmed=trimmed_count,
        )

        logger.info(
            "allocate: included=%d trimmed=%d total_tokens=%d budget=%d",
            len(included),
            trimmed_count,
            tokens_used,
            effective_budget,
        )

        return included, allocation
