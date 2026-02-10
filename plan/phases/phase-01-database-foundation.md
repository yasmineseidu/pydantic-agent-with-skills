# Phase 1: Database Foundation

> **Timeline**: Week 1 | **Prerequisites**: None (first phase) | **Status**: Not Started

## Goal

Add PostgreSQL infrastructure, core ORM models, and Alembic migrations. Zero behavior changes. The existing CLI must continue to work unchanged.

## Dependencies (Install)

```toml
[project]
dependencies = [
    # ... existing ...
    "sqlalchemy[asyncio]~=2.0.36",
    "asyncpg~=0.30.0",
    "alembic~=1.14.0",
    "pgvector~=0.3.6",
]
```

> Note: Pin with `~=` (compatible release) not `>=` (any future version). Prevents breaking upgrades.

## Settings Extensions

Extend `src/settings.py` -- all new fields `Optional` so CLI works without DB:

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

Also update `.env.example` with:
```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/skill_agent
EMBEDDING_API_KEY=sk-PLACEHOLDER
EMBEDDING_MODEL=text-embedding-3-small
```

## New Directories & Files

```
src/db/
    __init__.py          # Exports get_session, engine
    engine.py            # Async engine + session factory
    base.py              # Declarative base + mixins (TimestampMixin, UUIDMixin)
    models/
        __init__.py      # Import all models for Alembic discovery
        agent.py         # Agent, AgentSkill
        memory.py        # Memory (single table, discriminated)
        conversation.py  # Conversation, Message
        user.py          # User, Team, TeamMembership
    repositories/
        __init__.py
        base.py          # BaseRepository with common CRUD operations
        memory_repo.py   # MemoryRepository with vector search
    migrations/
        env.py
        versions/

src/models/
    __init__.py
    agent_models.py      # AgentDNA, AgentPersonality, AgentModelConfig, AgentMemoryConfig,
                         # AgentBoundaries, AgentStatus, VoiceExample, RetrievalWeights
    memory_models.py     # MemoryCreate, MemoryRecord, MemorySearchRequest, MemorySearchResult
    conversation_models.py  # ConversationCreate, MessageCreate
    user_models.py       # UserCreate, TeamCreate, TeamMembership
```

## Database Tables Introduced

### Core (3 tables)

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `user` | id (UUID), email, password_hash, display_name, is_active, created_at, updated_at | bcrypt hash, email format constraint |
| `team` | id (UUID), name, slug, owner_id (FK user), settings (JSONB), shared_skill_names (TEXT[]), webhook_url, webhook_secret, conversation_retention_days, created_at, updated_at | Multi-tenant root, slug uniqueness constraint |
| `team_membership` | id (UUID), user_id (FK), team_id (FK), role (ENUM: owner/admin/member/viewer), created_at | RBAC, unique (user_id, team_id) constraint |

### Agent (1 table + 1 reserved)

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `agent` | id (UUID), team_id (FK), name, slug, tagline, avatar_emoji, personality_prompt (TEXT), model_name, model_config (JSONB), memory_config (JSONB), boundaries (JSONB), skill_names (TEXT[]), custom_skill_names (TEXT[]), disabled_skill_names (TEXT[]), status (ENUM: draft/active/paused/archived), created_by (FK user), created_at, updated_at | Named agents. Stores AgentDNA as combination of top-level columns + JSONB config. Unique (team_id, slug) constraint |
| `agent_skill` | Reserved for future DB-stored skills | Not populated in Phase 1 |

### Conversation (2 tables)

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `conversation` | id (UUID), agent_id (FK), user_id (FK), team_id (FK), title, status (ENUM: active/idle/closed), message_count, token_count, created_at, last_message_at | |
| `message` | id (UUID), conversation_id (FK), role (ENUM: user/assistant/system/tool), content (TEXT), tool_calls (JSONB), token_count, feedback_rating, feedback_comment, created_at | Stores full conversation history |

### Memory (3 tables)

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `memory` | id (UUID), team_id (FK), agent_id (FK nullable), user_id (FK nullable), memory_type (ENUM: semantic/episodic/procedural/agent_private/shared/identity/user_profile), content (TEXT), subject (TEXT), embedding (vector(1536)), importance (1-10), confidence (0-1), access_count, is_pinned, source_type (ENUM: extraction/explicit/system/feedback/consolidation/compaction), source_conversation_id (FK), source_message_ids (UUID[]), extraction_model (TEXT), version (INT), superseded_by (self-FK), contradicts (UUID[]), related_to (UUID[]), metadata (JSONB), tier (ENUM: hot/warm/cold), status (ENUM: active/superseded/archived/disputed), created_at, updated_at, last_accessed_at, expires_at | Single table, all types (ADR-6) |
| `memory_log` | id (UUID), memory_id (UUID NOT NULL, no FK), action (TEXT), old_content, new_content, old_importance, new_importance, changed_by (TEXT), reason (TEXT), created_at | Append-only audit log (ADR-8). No FK intentionally -- survives deletes |
| `memory_tag` | id (UUID), memory_id (FK), tag (TEXT) | Categorical tagging |

Reference: `plan/sql/schema.sql` (Phase 1 section)

### Indexes

```sql
-- Vector similarity search
CREATE INDEX idx_memory_embedding ON memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Filtered vector search (most common query pattern)
CREATE INDEX idx_memory_team_type ON memory (team_id, memory_type)
    WHERE expires_at IS NULL OR expires_at > NOW();

-- Conversation lookup
CREATE INDEX idx_message_conversation ON message (conversation_id, created_at);

-- Agent per team
CREATE INDEX idx_agent_team ON agent (team_id, status);
```

### Database Extensions Required

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- gen_random_uuid() fallback
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector for embeddings
```

### ENUM Types Created

```sql
CREATE TYPE user_role AS ENUM ('owner', 'admin', 'member', 'viewer');
CREATE TYPE agent_status AS ENUM ('draft', 'active', 'paused', 'archived');
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');
CREATE TYPE memory_type_enum AS ENUM (
    'semantic', 'episodic', 'procedural', 'agent_private',
    'shared', 'identity', 'user_profile'
);
CREATE TYPE memory_status AS ENUM ('active', 'superseded', 'archived', 'disputed');
CREATE TYPE memory_tier AS ENUM ('hot', 'warm', 'cold');
CREATE TYPE memory_source AS ENUM (
    'extraction', 'explicit', 'system', 'feedback', 'consolidation', 'compaction'
);
CREATE TYPE conversation_status AS ENUM ('active', 'idle', 'closed');
```

## Implementation Details

### Database Engine Module (`src/db/engine.py`)

Async engine + session factory:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

async def get_engine(database_url: str, pool_size: int = 5, pool_overflow: int = 10):
    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=pool_overflow,
    )
    return engine

async def get_session(engine) -> AsyncSession:
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
```

### Base Models (`src/db/base.py`)

Declarative base + mixins:

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from uuid import UUID, uuid4

class Base(DeclarativeBase):
    pass

class UUIDMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### Repository Layer (`src/db/repositories/`)

```python
# src/db/repositories/base.py
class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    def __init__(self, session: AsyncSession) -> None: ...
    async def get_by_id(self, id: UUID) -> Optional[T]: ...
    async def create(self, **kwargs) -> T: ...
    async def update(self, id: UUID, **kwargs) -> T: ...
    async def delete(self, id: UUID) -> bool: ...

# src/db/repositories/memory_repo.py
class MemoryRepository(BaseRepository[MemoryORM]):
    async def search_by_embedding(
        self, embedding: list[float], team_id: UUID,
        agent_id: Optional[UUID], memory_types: list[MemoryType],
        limit: int = 20
    ) -> list[MemoryORM]: ...

    async def find_similar(
        self, embedding: list[float], threshold: float = 0.92
    ) -> list[MemoryORM]: ...
```

### Pydantic Models (`src/models/`)

The AgentDNA model is the central concept (full definition from Section 3A of main plan):

```python
class AgentDNA(BaseModel):
    """Complete identity document for a named agent."""

    # === IDENTITY ===
    id: UUID
    team_id: UUID
    name: str                        # "Kyra" -- display name
    slug: str                        # "kyra" -- URL-safe unique identifier
    tagline: str                     # "Your friendly AI companion" -- one-liner
    avatar_emoji: str = ""           # Optional visual identifier

    # === PERSONALITY ENGINE ===
    personality: AgentPersonality

    # === SKILLS ===
    shared_skill_names: list[str]    # Skills available to ALL agents in team
    custom_skill_names: list[str]    # Skills ONLY this agent has
    disabled_skill_names: list[str]  # Explicitly disabled (overrides shared)

    # === MODEL CONFIGURATION ===
    model: AgentModelConfig

    # === MEMORY CONFIGURATION ===
    memory: AgentMemoryConfig

    # === BEHAVIORAL BOUNDARIES ===
    boundaries: AgentBoundaries

    # === LIFECYCLE ===
    status: AgentStatus              # active, paused, archived, draft
    created_at: datetime
    updated_at: datetime
    created_by: UUID                 # User who created this agent

    @computed_field
    @property
    def effective_skills(self) -> list[str]:
        """All skills this agent can use (shared + custom - disabled)."""
        return [
            s for s in (self.shared_skill_names + self.custom_skill_names)
            if s not in self.disabled_skill_names
        ]


class AgentPersonality(BaseModel):
    """How the agent thinks, speaks, and behaves."""

    # Core personality prompt -- the "soul" of the agent
    system_prompt_template: str      # Template with {memory_context}, {skills}, etc.

    # Communication style
    tone: Literal[
        "professional", "friendly", "casual", "academic",
        "playful", "empathetic", "direct", "custom"
    ] = "friendly"
    verbosity: Literal["concise", "balanced", "detailed", "verbose"] = "balanced"
    formality: Literal["formal", "semi-formal", "informal", "adaptive"] = "adaptive"
    language: str = "en"             # ISO 639-1

    # Personality traits (weighted 0-1)
    traits: dict[str, float] = {}
    # Example: {"curious": 0.9, "humorous": 0.6, "empathetic": 0.8, "analytical": 0.7}

    # Voice examples -- sample responses that capture the agent's tone
    voice_examples: list[VoiceExample] = []

    # Behavioral rules (always/never)
    always_rules: list[str] = []     # "Always greet the user by name"
    never_rules: list[str] = []      # "Never give medical advice"

    # Custom instructions (free-form)
    custom_instructions: str = ""    # Extra instructions appended to system prompt


class VoiceExample(BaseModel):
    """A sample interaction that demonstrates the agent's voice."""
    user_message: str                # "What's the weather like?"
    agent_response: str              # "Hey! Let me check that for you..."
    context: str = ""                # "Casual greeting"


class AgentModelConfig(BaseModel):
    """LLM configuration per agent."""
    model_name: str = "anthropic/claude-sonnet-4.5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)
    provider_overrides: dict[str, Any] = {}  # Provider-specific params


class AgentMemoryConfig(BaseModel):
    """Memory system configuration per agent."""
    token_budget: int = Field(default=2000, ge=100, le=8000)
    retrieval_weights: RetrievalWeights = Field(default_factory=RetrievalWeights)
    auto_extract: bool = True        # Auto-extract memories after conversation
    auto_pin_preferences: bool = True  # Auto-pin user preferences
    summarize_interval: int = 20     # Messages between auto-summaries
    remember_commands: list[str] = [  # Phrases that trigger explicit memory save
        "remember this",
        "don't forget",
        "keep in mind",
        "note that",
    ]


class AgentBoundaries(BaseModel):
    """What the agent can and cannot do."""
    can_do: list[str] = []           # Explicit capabilities
    cannot_do: list[str] = []        # Explicit restrictions
    escalates_to: Optional[str] = None  # Agent slug to escalate to
    max_autonomy: Literal[
        "execute",   # Do things without asking
        "suggest",   # Suggest actions, wait for approval
        "ask",       # Always ask before acting
    ] = "execute"
    allowed_domains: list[str] = []  # HTTP tool domain allowlist (empty = all)
    max_tool_calls_per_turn: int = Field(default=10, ge=1, le=50)


class AgentStatus(str, Enum):
    DRAFT = "draft"         # Being configured, not yet usable
    ACTIVE = "active"       # Accepting conversations
    PAUSED = "paused"       # Temporarily unavailable
    ARCHIVED = "archived"   # Soft-deleted, data preserved


class RetrievalWeights(BaseModel):
    """Weights for 5-signal memory retrieval scoring."""
    semantic: float = Field(default=0.35, ge=0.0, le=1.0)
    recency: float = Field(default=0.20, ge=0.0, le=1.0)
    importance: float = Field(default=0.20, ge=0.0, le=1.0)
    continuity: float = Field(default=0.15, ge=0.0, le=1.0)
    relationship: float = Field(default=0.10, ge=0.0, le=1.0)
```

The ORM `agent` table stores AgentDNA as a combination of:
- Top-level columns: id, team_id, name, slug, tagline, status, created_at, updated_at
- config JSONB: personality, model, memory, boundaries (serialized AgentDNA subsections)
- skill_names TEXT[]: shared_skill_names + custom_skill_names + disabled_skill_names

### Memory Schema (Extended, from Section 3B)

```sql
CREATE TABLE memory (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES team(id),
    agent_id UUID REFERENCES agent(id),          -- NULL = shared/user-profile
    user_id UUID REFERENCES "user"(id),          -- NULL = team-wide

    -- Content
    memory_type TEXT NOT NULL,                    -- ENUM values above
    content TEXT NOT NULL,                        -- The actual memory text
    subject TEXT,                                 -- Structured: "user.preference.language"
    embedding vector(1536),                       -- pgvector

    -- Scoring
    importance INT NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    confidence FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    access_count INT DEFAULT 0,
    is_pinned BOOLEAN DEFAULT FALSE,

    -- Provenance
    source_type TEXT NOT NULL DEFAULT 'extraction',
    source_conversation_id UUID REFERENCES conversation(id),
    source_message_ids UUID[],                    -- Exact messages this memory came from
    extraction_model TEXT,                         -- Which LLM extracted this

    -- Versioning & Contradictions
    version INT DEFAULT 1,
    superseded_by UUID REFERENCES memory(id),     -- Points to newer version
    contradicts UUID[],                            -- IDs of memories this contradicts

    -- Relationships
    related_to UUID[],                             -- Soft links to related memories

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Lifecycle
    tier TEXT DEFAULT 'warm' CHECK (tier IN ('hot', 'warm', 'cold')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'archived', 'disputed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                        -- NULL = never expires

    CONSTRAINT valid_memory_type CHECK (memory_type IN (
        'semantic', 'episodic', 'procedural', 'agent_private',
        'shared', 'identity', 'user_profile'
    ))
);

-- Append-only audit log (NEVER modified, NEVER deleted)
CREATE TABLE memory_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL,                       -- No FK (survives deletes)
    action TEXT NOT NULL,                           -- 'created', 'updated', 'superseded', 'promoted', 'demoted'
    old_content TEXT,
    new_content TEXT,
    old_importance INT,
    new_importance INT,
    changed_by TEXT NOT NULL,                       -- 'system', 'user', 'consolidation', 'feedback'
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Critical Constraint

After Phase 1 completes:
```bash
python -m src.cli                    # CLI still works
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
```

## Tests

```
tests/
    test_db/
        conftest.py          # Test DB fixtures (async, uses test database)
        test_engine.py       # Connection, session creation
        test_models.py       # ORM model validation, relationships
        test_repositories.py # CRUD operations, vector search
    test_models/
        test_agent_models.py   # AgentDNA, AgentPersonality, etc.
        test_memory_models.py  # MemoryCreate, MemoryRecord, etc.
```

### Key Test Scenarios

- Alembic `upgrade head` creates all 9 tables correctly
- Alembic `downgrade base` drops all tables cleanly
- ORM model relationships resolve (e.g., team -> agents, conversation -> messages)
- Repository CRUD works for all entities (user, team, agent, conversation, message, memory)
- Vector search returns results sorted by cosine similarity
- Memory model validates importance range (1-10), confidence (0-1)
- AgentDNA `effective_skills` computed property works (shared + custom - disabled)
- RetrievalWeights default values sum appropriately
- CLI works unchanged with no database configured (`python -m src.cli`)
- All existing tests pass without modification

## Acceptance Criteria

- [ ] `alembic upgrade head` creates all 9 tables
- [ ] `alembic downgrade base` drops cleanly
- [ ] Repository CRUD works for all entities
- [ ] Vector search returns results sorted by cosine similarity
- [ ] CLI works unchanged (`python -m src.cli`)
- [ ] All existing tests pass

## Rollback Strategy

- `alembic downgrade base` removes all tables
- Delete `src/db/` and `src/models/` directories
- Revert `src/settings.py` changes (remove Optional DB/embedding fields)
- Revert `.env.example` changes
- Revert `pyproject.toml` dependency additions

### Database Migration Safety

```bash
# Before any migration in production:
1. Backup database: pg_dump -Fc skill_agent > backup_$(date +%Y%m%d).dump
2. Test migration on staging first
3. Run migration: alembic upgrade head
4. Verify: alembic current
5. If broken: alembic downgrade -1  (revert last migration)
6. If catastrophic: pg_restore -d skill_agent backup_YYYYMMDD.dump
```

## Links to Main Plan

- Architecture: `plan/multi-agent-platform.md` Section 2
- ADRs: Section 3 (ADR-1: PostgreSQL + pgvector, ADR-6: Single memory table, ADR-8: Append-only memory)
- Agent Identity System: Section 3A (AgentDNA, AgentPersonality, etc.)
- Memory Schema: Section 3B (memory table, memory_log)
- Phase 1 details: Section 4, "Phase 1: Database Foundation"
- Database schema: `plan/sql/schema.sql` (Phase 1 section, lines 118-410+)
- Files modified: Section 5 (`pyproject.toml`, `src/settings.py`, `.env.example`)
- Rollback: Section 23
- Phase dependency graph: Section 21 (Phase 1 is the root -- required by all phases)
