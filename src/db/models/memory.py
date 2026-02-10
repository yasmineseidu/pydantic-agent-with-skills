"""Memory, MemoryLog, and MemoryTag ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.agent import AgentORM
    from src.db.models.conversation import ConversationORM
    from src.db.models.user import TeamORM, UserORM


class MemoryTypeEnum(str, enum.Enum):
    """Discriminator for the 7 memory types (ADR-6: single table).

    Maps to the ``memory_type_enum`` PostgreSQL enum type.
    """

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    AGENT_PRIVATE = "agent_private"
    SHARED = "shared"
    IDENTITY = "identity"
    USER_PROFILE = "user_profile"


class MemoryStatusEnum(str, enum.Enum):
    """Lifecycle status of a memory record.

    Maps to the ``memory_status`` PostgreSQL enum type.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DISPUTED = "disputed"


class MemoryTierEnum(str, enum.Enum):
    """Storage tier controlling retrieval latency.

    Maps to the ``memory_tier`` PostgreSQL enum type.
    """

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class MemorySourceEnum(str, enum.Enum):
    """How the memory was created.

    Maps to the ``memory_source`` PostgreSQL enum type.
    """

    EXTRACTION = "extraction"
    EXPLICIT = "explicit"
    SYSTEM = "system"
    FEEDBACK = "feedback"
    CONSOLIDATION = "consolidation"
    COMPACTION = "compaction"


class MemoryORM(Base, UUIDMixin, TimestampMixin):
    """Core memory table for all 7 memory types (ADR-6: type discriminator).

    Append-only semantics: memories are never hard-deleted.
    Superseded memories move to tier='cold', status='superseded'.
    Maps to the ``memory`` table.
    """

    __tablename__ = "memory"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 10", name="ck_memory_importance"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_memory_confidence"),
    )

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agent.id"), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("user.id"), nullable=True)

    # Content
    memory_type: Mapped[str] = mapped_column(
        Enum(MemoryTypeEnum, name="memory_type_enum", native_enum=True, create_constraint=False),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    # Scoring
    importance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Provenance
    source_type: Mapped[str] = mapped_column(
        Enum(MemorySourceEnum, name="memory_source", native_enum=True, create_constraint=False),
        nullable=False,
        server_default=text("'extraction'"),
    )
    source_conversation_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("conversation.id"), nullable=True
    )
    source_message_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    extraction_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Versioning and contradictions
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    superseded_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("memory.id"), nullable=True)
    contradicts: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)

    # Relationships (soft links)
    related_to: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)

    # Metadata
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Lifecycle
    tier: Mapped[str] = mapped_column(
        Enum(MemoryTierEnum, name="memory_tier", native_enum=True, create_constraint=False),
        nullable=False,
        server_default=text("'warm'"),
    )
    status: Mapped[str] = mapped_column(
        Enum(MemoryStatusEnum, name="memory_status", native_enum=True, create_constraint=False),
        nullable=False,
        server_default=text("'active'"),
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    team: Mapped["TeamORM"] = relationship("TeamORM")
    agent: Mapped[Optional["AgentORM"]] = relationship("AgentORM")
    user: Mapped[Optional["UserORM"]] = relationship("UserORM")
    source_conversation: Mapped[Optional["ConversationORM"]] = relationship("ConversationORM")
    superseding_memory: Mapped[Optional["MemoryORM"]] = relationship(
        "MemoryORM", remote_side="MemoryORM.id", foreign_keys=[superseded_by]
    )
    tags: Mapped[List["MemoryTagORM"]] = relationship(
        "MemoryTagORM", back_populates="memory", cascade="all, delete-orphan"
    )


class MemoryLogORM(Base, UUIDMixin):
    """Append-only audit trail for memory lifecycle events.

    Never modified, never deleted. Every memory lifecycle event is recorded.
    No FK on memory_id intentionally (ADR-8: survives memory deletes).
    Maps to the ``memory_log`` table.
    """

    __tablename__ = "memory_log"

    memory_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)

    # Change tracking
    old_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_importance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_importance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Attribution
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provenance
    conversation_id: Mapped[Optional[UUID]] = mapped_column(nullable=True)
    related_memory_ids: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryTagORM(Base, UUIDMixin):
    """Categorical tag for a memory (searchable label).

    Maps to the ``memory_tag`` table.
    """

    __tablename__ = "memory_tag"
    __table_args__ = (UniqueConstraint("memory_id", "tag", name="uq_memory_tag"),)

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    memory: Mapped["MemoryORM"] = relationship("MemoryORM", back_populates="tags")
