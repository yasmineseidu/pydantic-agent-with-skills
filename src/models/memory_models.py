"""Pydantic models for memory system (create, record, search)."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Discriminator for the 7 memory types (ADR-6: single table)."""

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    AGENT_PRIVATE = "agent_private"
    SHARED = "shared"
    IDENTITY = "identity"
    USER_PROFILE = "user_profile"


class MemoryStatus(str, Enum):
    """Lifecycle status of a memory record."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DISPUTED = "disputed"


class MemoryTier(str, Enum):
    """Storage tier controlling retrieval latency."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class MemorySource(str, Enum):
    """How the memory was created."""

    EXTRACTION = "extraction"
    EXPLICIT = "explicit"
    SYSTEM = "system"
    FEEDBACK = "feedback"
    CONSOLIDATION = "consolidation"
    COMPACTION = "compaction"


class MemoryCreate(BaseModel):
    """Request model for creating a memory.

    Contains the minimum fields needed to insert a new memory row.
    Server-side defaults handle id, timestamps, access_count, etc.
    """

    team_id: UUID
    agent_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    memory_type: MemoryType
    content: str
    subject: Optional[str] = None
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: MemorySource = MemorySource.EXTRACTION
    source_conversation_id: Optional[UUID] = None
    source_message_ids: list[UUID] = Field(default_factory=list)
    extraction_model: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """Full memory record as returned from the database.

    Mirrors all columns in the memory table including scoring,
    provenance, versioning, and lifecycle fields.
    """

    id: UUID
    team_id: UUID
    agent_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    memory_type: MemoryType
    content: str
    subject: Optional[str] = None

    # Scoring
    importance: int
    confidence: float
    access_count: int = 0
    is_pinned: bool = False

    # Provenance
    source_type: MemorySource
    source_conversation_id: Optional[UUID] = None
    source_message_ids: list[UUID] = Field(default_factory=list)
    extraction_model: Optional[str] = None

    # Versioning and contradictions
    version: int = 1
    superseded_by: Optional[UUID] = None
    contradicts: list[UUID] = Field(default_factory=list)

    # Relationships
    related_to: list[UUID] = Field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Lifecycle
    tier: MemoryTier = MemoryTier.WARM
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    expires_at: Optional[datetime] = None


class MemorySearchRequest(BaseModel):
    """Request model for searching memories by embedding similarity.

    Args fields are used to filter and limit the vector search query.
    """

    team_id: UUID
    query: str
    agent_id: Optional[UUID] = None
    memory_types: list[MemoryType] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class MemorySearchResult(BaseModel):
    """Memory search result with cosine similarity score.

    Wraps a MemoryRecord with its similarity to the search query.
    """

    memory: MemoryRecord
    similarity: float = Field(ge=0.0, le=1.0)
