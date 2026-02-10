# Architecture Design: Phase 1 - Database Foundation
Status: COMPLETE

## Overview

Phase 1 adds a PostgreSQL persistence layer to the existing skill-based agent. The architecture follows the existing codebase patterns: Pydantic for validation, dataclass for DI, structured logging, Google docstrings. All new modules are self-contained in `src/db/` and `src/models/` -- nothing in existing `src/` imports from them except extended settings fields.

---

## Directory Structure

```
src/
    db/
        __init__.py              # Public API: get_engine, get_session_factory, Base
        engine.py                # AsyncEngine creation + session factory
        base.py                  # DeclarativeBase + UUIDMixin + TimestampMixin
        models/
            __init__.py          # Import all ORM models (for Alembic discovery)
            user.py              # UserORM, TeamORM, TeamMembershipORM
            agent.py             # AgentORM
            conversation.py      # ConversationORM, MessageORM
            memory.py            # MemoryORM, MemoryLogORM, MemoryTagORM
        repositories/
            __init__.py          # Export repositories
            base.py              # BaseRepository[T] generic CRUD
            memory_repo.py       # MemoryRepository with vector search
        migrations/
            env.py               # Async Alembic env
            script.py.mako       # Migration template
            versions/
                001_phase1_foundation.py  # Initial migration
    models/
        __init__.py              # Export Pydantic models
        agent_models.py          # AgentDNA, AgentPersonality, etc.
        memory_models.py         # MemoryCreate, MemoryRecord, etc.
        conversation_models.py   # ConversationCreate, MessageCreate
        user_models.py           # UserCreate, TeamCreate, etc.
    settings.py                  # MODIFIED: +6 Optional DB/embedding fields

alembic.ini                      # NEW: Alembic configuration
pyproject.toml                   # MODIFIED: +4 dependencies
.env.example                     # MODIFIED: +3 placeholder lines

tests/
    test_db/
        __init__.py
        conftest.py              # DB fixtures (engine, session, skip logic)
        test_engine.py           # Engine creation, session lifecycle
        test_models.py           # ORM model validation, relationships
        test_repositories.py     # CRUD operations, vector search
    test_models/
        __init__.py
        test_agent_models.py     # AgentDNA, computed fields, validation
        test_memory_models.py    # MemoryCreate, validation constraints
```

---

## Component Design

### 1. Database Engine (`src/db/engine.py`)

```python
"""Async database engine and session factory."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


async def get_engine(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    echo: bool = False,
) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine.

    Args:
        database_url: PostgreSQL connection URL (postgresql+asyncpg://...)
        pool_size: Connection pool size
        max_overflow: Maximum overflow connections
        echo: Enable SQL logging

    Returns:
        Configured AsyncEngine

    Raises:
        ValueError: If database_url is empty
    """
    if not database_url:
        raise ValueError("database_url is required")

    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )
    logger.info(f"engine_created: pool_size={pool_size}, max_overflow={max_overflow}")
    return engine


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create an async session factory.

    Args:
        engine: AsyncEngine to bind sessions to

    Returns:
        Configured async_sessionmaker
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
```

**Design decisions:**
- Factory functions (not class) -- matches `load_settings()` pattern
- Returns engine/factory, caller manages lifecycle
- `expire_on_commit=False` -- standard for async usage (avoids lazy-load issues)
- Logging follows `f"action_name: key={value}"` format

### 2. Declarative Base (`src/db/base.py`)

```python
"""SQLAlchemy declarative base and common mixins."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class UUIDMixin:
    """Mixin providing UUID primary key with server-side generation."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

**Design decisions:**
- `server_default=text("gen_random_uuid()")` -- uses PG's native UUID generation
- `DateTime(timezone=True)` -- TIMESTAMPTZ to match schema.sql
- Mixins are plain classes (not Base subclasses) for multiple inheritance

### 3. ORM Models

#### 3a. User Models (`src/db/models/user.py`)

```python
"""ORM models for user, team, and team membership."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, Enum as SAEnum, ForeignKey, Integer, String, Text,
    DateTime, JSON, ARRAY, func, text, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUIDMixin, TimestampMixin


class UserRole(str, enum.Enum):
    """RBAC roles for team membership."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserORM(UUIDMixin, TimestampMixin, Base):
    """Platform user."""
    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        CheckConstraint(r"email ~* '^[^@]+@[^@]+\.[^@]+$'", name="ck_user_email_format"),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Relationships
    owned_teams: Mapped[list["TeamORM"]] = relationship(back_populates="owner")
    memberships: Mapped[list["TeamMembershipORM"]] = relationship(back_populates="user")


class TeamORM(UUIDMixin, TimestampMixin, Base):
    """Multi-tenant root entity."""
    __tablename__ = "team"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_team_slug"),
        CheckConstraint(r"slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'", name="ck_team_slug_format"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'::jsonb"))
    shared_skill_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("90")
    )

    # Relationships
    owner: Mapped["UserORM"] = relationship(back_populates="owned_teams")
    memberships: Mapped[list["TeamMembershipORM"]] = relationship(back_populates="team")
    agents: Mapped[list["AgentORM"]] = relationship(back_populates="team")


class TeamMembershipORM(UUIDMixin, Base):
    """RBAC: user-to-team membership with role."""
    __tablename__ = "team_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_team_membership"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False, native_enum=True),
        nullable=False,
        server_default="member",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["UserORM"] = relationship(back_populates="memberships")
    team: Mapped["TeamORM"] = relationship(back_populates="memberships")
```

#### 3b. Agent Model (`src/db/models/agent.py`)

```python
"""ORM model for agent (AgentDNA storage)."""

import enum
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    ARRAY, Enum as SAEnum, ForeignKey, JSON, Text,
    CheckConstraint, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUIDMixin, TimestampMixin


class AgentStatus(str, enum.Enum):
    """Agent lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AgentORM(UUIDMixin, TimestampMixin, Base):
    """Named agent with full AgentDNA configuration."""
    __tablename__ = "agent"
    __table_args__ = (
        UniqueConstraint("team_id", "slug", name="uq_agent_team_slug"),
        CheckConstraint(
            r"slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'",
            name="ck_agent_slug_format",
        ),
    )

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    tagline: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    avatar_emoji: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))

    # Personality (serialized AgentPersonality)
    personality: Mapped[dict] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Skills
    shared_skill_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    custom_skill_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    disabled_skill_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    # Model config (serialized AgentModelConfig)
    model_config_json: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        server_default=text(
            """'{"model_name":"anthropic/claude-sonnet-4.5","temperature":0.7,"max_output_tokens":4096}'::jsonb"""
        ),
    )

    # Memory config (serialized AgentMemoryConfig)
    memory_config: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        server_default=text(
            """'{"token_budget":2000,"auto_extract":true,"auto_pin_preferences":true,"summarize_interval":20,"retrieval_weights":{"semantic":0.35,"recency":0.20,"importance":0.20,"continuity":0.15,"relationship":0.10}}'::jsonb"""
        ),
    )

    # Boundaries (serialized AgentBoundaries)
    boundaries: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        server_default=text(
            """'{"max_autonomy":"execute","max_tool_calls_per_turn":10}'::jsonb"""
        ),
    )

    # Lifecycle
    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus, name="agent_status", create_constraint=False, native_enum=True),
        nullable=False,
        server_default="draft",
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )

    # Relationships
    team: Mapped["TeamORM"] = relationship(back_populates="agents")
    conversations: Mapped[list["ConversationORM"]] = relationship(back_populates="agent")
```

#### 3c. Conversation Models (`src/db/models/conversation.py`)

```python
"""ORM models for conversation and message."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, Text,
    CheckConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUIDMixin, TimestampMixin


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationORM(UUIDMixin, TimestampMixin, Base):
    """A conversation between a user and an agent."""
    __tablename__ = "conversation"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, name="conversation_status",
               create_constraint=False, native_enum=True),
        nullable=False, server_default="active",
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'::jsonb"))
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    agent: Mapped["AgentORM"] = relationship(back_populates="conversations")
    messages: Mapped[list["MessageORM"]] = relationship(back_populates="conversation")


class MessageORM(UUIDMixin, Base):
    """Individual message within a conversation."""
    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint(
            "feedback_rating IN ('positive', 'negative') OR feedback_rating IS NULL",
            name="ck_message_feedback_rating",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("agent.id"), nullable=True
    )
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="message_role", create_constraint=False, native_enum=True),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_rating: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(back_populates="messages")
```

#### 3d. Memory Models (`src/db/models/memory.py`)

```python
"""ORM models for memory, memory_log, and memory_tag."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, DateTime, Enum as SAEnum,
    Float, ForeignKey, Integer, JSON, Text, UniqueConstraint,
    func, text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from src.db.base import Base, UUIDMixin, TimestampMixin


class MemoryType(str, enum.Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    AGENT_PRIVATE = "agent_private"
    SHARED = "shared"
    IDENTITY = "identity"
    USER_PROFILE = "user_profile"


class MemoryStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DISPUTED = "disputed"


class MemoryTier(str, enum.Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class MemorySource(str, enum.Enum):
    EXTRACTION = "extraction"
    EXPLICIT = "explicit"
    SYSTEM = "system"
    FEEDBACK = "feedback"
    CONSOLIDATION = "consolidation"
    COMPACTION = "compaction"


class MemoryORM(UUIDMixin, TimestampMixin, Base):
    """Single-table memory storage for all 7 memory types."""
    __tablename__ = "memory"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 10", name="ck_memory_importance"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_memory_confidence"),
    )

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("agent.id"), nullable=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )

    # Content
    memory_type: Mapped[MemoryType] = mapped_column(
        SAEnum(MemoryType, name="memory_type_enum", create_constraint=False, native_enum=True),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)

    # Scoring
    importance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # Provenance
    source_type: Mapped[MemorySource] = mapped_column(
        SAEnum(MemorySource, name="memory_source", create_constraint=False, native_enum=True),
        nullable=False, server_default="extraction",
    )
    source_conversation_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("conversation.id"), nullable=True
    )
    source_message_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PGUUID), nullable=True
    )
    extraction_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Versioning
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    superseded_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("memory.id"), nullable=True
    )
    contradicts: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PGUUID), nullable=True)

    # Relationships (soft links)
    related_to: Mapped[Optional[list[UUID]]] = mapped_column(ARRAY(PGUUID), nullable=True)

    # Metadata
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Lifecycle
    tier: Mapped[MemoryTier] = mapped_column(
        SAEnum(MemoryTier, name="memory_tier", create_constraint=False, native_enum=True),
        nullable=False, server_default="warm",
    )
    status: Mapped[MemoryStatus] = mapped_column(
        SAEnum(MemoryStatus, name="memory_status", create_constraint=False, native_enum=True),
        nullable=False, server_default="active",
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    tags: Mapped[list["MemoryTagORM"]] = relationship(back_populates="memory")


class MemoryLogORM(UUIDMixin, Base):
    """Append-only audit trail for memory lifecycle events."""
    __tablename__ = "memory_log"

    # NO FK on memory_id intentionally (survives deletes)
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
    related_memory_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PGUUID), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryTagORM(UUIDMixin, Base):
    """Categorical tagging for memories."""
    __tablename__ = "memory_tag"
    __table_args__ = (
        UniqueConstraint("memory_id", "tag", name="uq_memory_tag"),
    )

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    memory: Mapped["MemoryORM"] = relationship(back_populates="tags")
```

### 4. Pydantic Models (`src/models/`)

#### 4a. Agent Models (`src/models/agent_models.py`)

Full Pydantic models for AgentDNA and sub-models. These are the domain/API layer -- independent of ORM.

Key models:
- `AgentDNA` -- complete agent identity with `effective_skills` computed property
- `AgentPersonality` -- tone, verbosity, formality, traits, voice examples, rules
- `VoiceExample` -- sample interaction
- `AgentModelConfig` -- LLM config with Field constraints
- `AgentMemoryConfig` -- memory retrieval config
- `AgentBoundaries` -- capability boundaries
- `AgentStatus` -- Enum (draft/active/paused/archived)
- `RetrievalWeights` -- 5-signal weights

All models exactly match the definitions in the phase document.

#### 4b. Memory Models (`src/models/memory_models.py`)

- `MemoryCreate` -- input for creating a memory (content, type, importance, etc.)
- `MemoryRecord` -- full memory representation (all fields)
- `MemorySearchRequest` -- search parameters (query/embedding, filters, limit)
- `MemorySearchResult` -- search result with similarity score

#### 4c. Conversation Models (`src/models/conversation_models.py`)

- `ConversationCreate` -- input for creating a conversation
- `MessageCreate` -- input for creating a message

#### 4d. User Models (`src/models/user_models.py`)

- `UserCreate` -- input for creating a user (email, password, display_name)
- `TeamCreate` -- input for creating a team (name, slug)
- `TeamMembershipInfo` -- membership display model

### 5. Repository Layer (`src/db/repositories/`)

#### BaseRepository[T]
Generic CRUD with async session:
- `get_by_id(id: UUID) -> Optional[T]`
- `create(**kwargs) -> T`
- `update(id: UUID, **kwargs) -> Optional[T]`
- `delete(id: UUID) -> bool`
- `list(limit: int, offset: int) -> list[T]`

#### MemoryRepository(BaseRepository[MemoryORM])
Specialized vector operations:
- `search_by_embedding(embedding, team_id, agent_id, memory_types, limit) -> list[MemoryORM]`
- `find_similar(embedding, threshold) -> list[MemoryORM]`
- `update_access(memory_ids: list[UUID]) -> None`

### 6. Settings Extensions (`src/settings.py`)

Add after existing fields (line ~70):

```python
# Database (Optional - enables persistence)
database_url: Optional[str] = Field(
    default=None,
    description="PostgreSQL connection URL (postgresql+asyncpg://...)"
)
database_pool_size: int = Field(default=5, ge=1, le=50)
database_pool_overflow: int = Field(default=10, ge=0, le=100)

# Embeddings (Optional - enables semantic search)
embedding_model: str = Field(default="text-embedding-3-small")
embedding_api_key: Optional[str] = Field(
    default=None,
    description="OpenAI API key for embeddings (defaults to llm_api_key)"
)
embedding_dimensions: int = Field(default=1536)
```

**Critical**: All fields are Optional or have defaults. `load_settings()` continues to work without database configuration.

### 7. Alembic Migration

#### `alembic.ini`
- `script_location = src/db/migrations`
- Default URL overridden by env.py using Settings

#### `src/db/migrations/env.py`
- Async env using `async_engine_from_config`
- Imports Base and all models for metadata target
- Uses `load_settings().database_url` to override URL

#### Initial Migration (`001_phase1_foundation.py`)

Upgrade order:
1. Create extensions (uuid-ossp, pgcrypto, vector)
2. Create 8 ENUM types
3. Create 9 tables in dependency order (user -> team -> team_membership -> agent -> conversation -> message -> memory -> memory_log -> memory_tag)
4. Create indexes
5. Create functions (trigger_set_updated_at, trigger_update_conversation_stats, update_memory_access, reconstruct_memory_at)
6. Create triggers

Downgrade order (reverse):
1. Drop triggers
2. Drop functions
3. Drop indexes
4. Drop tables in reverse dependency order
5. Drop ENUM types
6. Do NOT drop extensions (shared resource)

---

## Integration Map

```
EXISTING CODE                    NEW CODE (Phase 1)
==============                   ==================

src/settings.py  ──(+6 fields)──> database_url, pool_size, etc.
                                   (all Optional, backward compatible)

pyproject.toml   ──(+4 deps)────> sqlalchemy, asyncpg, alembic, pgvector

.env.example     ──(+3 lines)──> DATABASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL

                                  src/db/
                                    engine.py      (standalone)
                                    base.py        (standalone)
                                    models/        (imports base.py)
                                    repositories/  (imports models + base)
                                    migrations/    (imports models + settings)

                                  src/models/      (standalone Pydantic models)

Nothing in existing src/ imports from src/db/ or src/models/ in Phase 1.
These modules become connected in Phase 2+ when dependencies.py adds DB session.
```

---

## Naming Conventions (Matching Existing Codebase)

| Pattern | Convention | Example |
|---------|-----------|---------|
| ORM model | `{Name}ORM` | `UserORM`, `MemoryORM` |
| Pydantic model | `{Name}` or `{Name}Create` | `AgentDNA`, `MemoryCreate` |
| Enum | `{Name}` (PascalCase) | `UserRole`, `MemoryType` |
| Repository | `{Name}Repository` | `MemoryRepository` |
| File (ORM) | `src/db/models/{entity}.py` | `user.py`, `memory.py` |
| File (Pydantic) | `src/models/{entity}_models.py` | `agent_models.py` |
| Test file | `tests/test_{category}/test_{entity}.py` | `test_agent_models.py` |

ORM suffix avoids collision with Pydantic model names (e.g., `AgentDNA` vs `AgentORM`).
