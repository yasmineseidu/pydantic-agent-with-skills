"""Phase 2 Pydantic models for memory retrieval, scoring, and extraction."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.memory_models import (
    MemoryRecord,
    MemoryType,
)


class ScoredMemory(BaseModel):
    """A memory record wrapped with its composite retrieval score.

    Combines the raw MemoryRecord with the final weighted score and
    per-signal breakdown used during 5-signal retrieval ranking.

    Attributes:
        memory: The underlying memory record from the database.
        final_score: Composite weighted score in [0.0, 1.0].
        signal_scores: Per-signal scores keyed by signal name
            (semantic, recency, importance, continuity, relationship).
    """

    memory: MemoryRecord
    final_score: float = Field(ge=0.0, le=1.0)
    signal_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-signal scores: semantic, recency, importance, continuity, relationship",
    )


class RetrievalStats(BaseModel):
    """Performance metrics for a single retrieval operation.

    Attributes:
        signals_hit: Number of retrieval signals that contributed non-zero scores.
        cache_hit: Whether the result was served from cache.
        total_ms: Wall-clock time for the retrieval in milliseconds.
        query_tokens: Estimated token count of the query text.
    """

    signals_hit: int = Field(ge=0)
    cache_hit: bool = False
    total_ms: float = Field(ge=0.0)
    query_tokens: int = Field(ge=0)


class Contradiction(BaseModel):
    """A detected contradiction between two memory records.

    Attributes:
        memory_a: UUID of the first conflicting memory.
        memory_b: UUID of the second conflicting memory.
        reason: Human-readable explanation of the contradiction.
    """

    memory_a: UUID
    memory_b: UUID
    reason: str


class RetrievalResult(BaseModel):
    """Complete output of a memory retrieval operation.

    Contains the ranked memories, formatted prompt section,
    performance stats, and any contradictions detected among results.

    Attributes:
        memories: Scored memories ranked by final_score descending.
        formatted_prompt: Pre-formatted string ready for injection into the system prompt.
        stats: Performance metrics for this retrieval.
        contradictions: Contradictions detected among the returned memories.
    """

    memories: list[ScoredMemory] = Field(default_factory=list)
    formatted_prompt: str = ""
    stats: RetrievalStats
    contradictions: list[Contradiction] = Field(default_factory=list)


class ContradictionResult(BaseModel):
    """Result of checking a new memory against existing memories for contradictions.

    Attributes:
        contradicts: UUIDs of existing memories that conflict with the new memory.
        action: Resolution strategy chosen for the contradiction.
        reason: Explanation of why this action was selected.
    """

    contradicts: list[UUID] = Field(default_factory=list)
    action: Literal["supersede", "dispute", "coexist"]
    reason: str


class CompactionResult(BaseModel):
    """Result of compacting a conversation into long-term memories.

    Attributes:
        memories_extracted: Total number of memories extracted from the conversation.
        summary: Human-readable summary of the compaction pass.
        pass1_count: Memories extracted in the first (high-confidence) pass.
        pass2_additions: Additional memories extracted in the second (gap-filling) pass.
    """

    memories_extracted: int = Field(ge=0)
    summary: str
    pass1_count: int = Field(ge=0)
    pass2_additions: int = Field(ge=0)


class ExtractionResult(BaseModel):
    """Result of extracting memories from a conversation or text block.

    Attributes:
        memories_created: Number of new memory records created.
        memories_versioned: Number of existing memories that were versioned (updated).
        duplicates_skipped: Number of duplicate memories that were not persisted.
        contradictions_found: Number of contradictions detected during extraction.
        pass1_count: Memories extracted in the first (high-confidence) pass.
        pass2_additions: Additional memories extracted in the second (gap-filling) pass.
    """

    memories_created: int = Field(ge=0)
    memories_versioned: int = Field(ge=0)
    duplicates_skipped: int = Field(ge=0)
    contradictions_found: int = Field(ge=0)
    pass1_count: int = Field(ge=0)
    pass2_additions: int = Field(ge=0)


class ExtractedMemory(BaseModel):
    """A single memory extracted from conversation before persistence.

    Represents the raw extraction output before deduplication,
    contradiction checking, and database insertion.

    Attributes:
        type: The memory type classification.
        content: The extracted memory content text.
        subject: Optional subject or topic tag for the memory.
        importance: Importance score from 1 (trivial) to 10 (critical).
        confidence: Extraction confidence from 0.0 (uncertain) to 1.0 (certain).
    """

    type: MemoryType
    content: str
    subject: Optional[str] = None
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class MemorySnapshot(BaseModel):
    """Point-in-time snapshot of a memory's state.

    Used for debugging, auditing, and timeline reconstruction.

    Attributes:
        memory_id: UUID of the memory record.
        content: The memory content at this point in time.
        status: Lifecycle status (active, superseded, archived, disputed).
        tier: Storage tier (hot, warm, cold).
        timestamp: When this snapshot was captured.
    """

    memory_id: UUID
    content: str
    status: str
    tier: str
    timestamp: datetime


class BudgetAllocation(BaseModel):
    """Token budget breakdown for memory injection into the system prompt.

    Tracks how the total token budget is distributed across memory
    categories and how many memories were included vs. trimmed.

    Attributes:
        identity_tokens: Tokens allocated to identity memories.
        pinned_tokens: Tokens allocated to pinned memories.
        profile_tokens: Tokens allocated to user profile memories.
        remaining_tokens: Tokens available after fixed allocations.
        total_tokens: Total token budget for memory injection.
        memories_included: Number of memories that fit within budget.
        memories_trimmed: Number of memories excluded due to budget constraints.
    """

    identity_tokens: int = Field(ge=0)
    pinned_tokens: int = Field(ge=0)
    profile_tokens: int = Field(ge=0)
    remaining_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    memories_included: int = Field(ge=0)
    memories_trimmed: int = Field(ge=0)
