# Task Tree: Phase 1 - Database Foundation
Status: COMPLETE

## Summary
- **Total tasks**: 16 atomic tasks
- **Tracks**: 5 parallel tracks where possible
- **Agents**: builder (code), tester (tests)
- **Estimated total complexity**: ~4-5 sessions

---

## Track 1: Project Config (no dependencies -- can start immediately)

### Task 1.1: Add database dependencies to pyproject.toml
- **Agent**: builder
- **Complexity**: S
- **Files owned**: `pyproject.toml`
- **Description**: Add 4 new dependencies to `[project] dependencies`:
  - `sqlalchemy[asyncio]~=2.0.36`
  - `asyncpg~=0.30.0`
  - `alembic~=1.14.0`
  - `pgvector~=0.3.6`
  Then run `uv sync` to install.
- **Acceptance criteria**:
  - [ ] Dependencies listed in pyproject.toml
  - [ ] `uv sync` succeeds
  - [ ] `python -c "import sqlalchemy; import asyncpg; import alembic; import pgvector"` works
  - [ ] Existing tests still pass: `.venv/bin/python -m pytest tests/ -v`
- **Blocked by**: nothing

### Task 1.2: Extend settings.py with database fields
- **Agent**: builder
- **Complexity**: S
- **Files owned**: `src/settings.py`
- **Description**: Add 6 Optional fields to the Settings class:
  - `database_url: Optional[str] = Field(default=None, description="PostgreSQL connection URL (postgresql+asyncpg://...)")`
  - `database_pool_size: int = Field(default=5, ge=1, le=50)`
  - `database_pool_overflow: int = Field(default=10, ge=0, le=100)`
  - `embedding_model: str = Field(default="text-embedding-3-small")`
  - `embedding_api_key: Optional[str] = Field(default=None, description="OpenAI API key for embeddings")`
  - `embedding_dimensions: int = Field(default=1536)`
  All fields MUST have defaults or be Optional so `load_settings()` works without DB.
- **Acceptance criteria**:
  - [ ] 6 new fields added to Settings class
  - [ ] `load_settings()` works without DATABASE_URL set
  - [ ] `python -m src.cli` still works (test manually or via existing tests)
  - [ ] `ruff check src/settings.py` clean
  - [ ] `mypy src/settings.py` clean
- **Blocked by**: nothing

### Task 1.3: Update .env.example with database placeholders
- **Agent**: builder
- **Complexity**: S
- **Files owned**: `.env.example`
- **Description**: Add a new section to .env.example:
  ```
  # =============================================================================
  # DATABASE (Optional - enables persistence)
  # =============================================================================
  # DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/skill_agent
  # DATABASE_POOL_SIZE=5
  # DATABASE_POOL_OVERFLOW=10

  # =============================================================================
  # EMBEDDINGS (Optional - enables semantic search)
  # =============================================================================
  # EMBEDDING_API_KEY=sk-PLACEHOLDER
  # EMBEDDING_MODEL=text-embedding-3-small
  # EMBEDDING_DIMENSIONS=1536
  ```
  All lines commented out by default (Optional features).
- **Acceptance criteria**:
  - [ ] New section added to .env.example
  - [ ] No real credentials (use PLACEHOLDER values)
  - [ ] Existing sections unchanged
- **Blocked by**: nothing

---

## Track 2: Database Infrastructure (depends on Track 1 completion)

### Task 2.1: Create database base module (Base + Mixins)
- **Agent**: builder
- **Complexity**: S
- **Files owned**: `src/db/__init__.py`, `src/db/base.py`
- **Description**: Create `src/db/` package with:
  - `__init__.py` -- empty initially (will export after engine.py exists)
  - `base.py` -- `Base(DeclarativeBase)`, `UUIDMixin` (UUID PK with server_default gen_random_uuid()), `TimestampMixin` (created_at + updated_at with timezone)
  Follow exact patterns from architecture.md. Use `server_default=text("gen_random_uuid()")` for UUIDs. Use `DateTime(timezone=True)`.
- **Acceptance criteria**:
  - [ ] `src/db/__init__.py` exists
  - [ ] `src/db/base.py` exports Base, UUIDMixin, TimestampMixin
  - [ ] `from src.db.base import Base, UUIDMixin, TimestampMixin` works
  - [ ] ruff + mypy clean
- **Blocked by**: Task 1.1 (needs sqlalchemy installed)

### Task 2.2: Create database engine module
- **Agent**: builder
- **Complexity**: S
- **Files owned**: `src/db/engine.py`
- **Description**: Create `src/db/engine.py` with:
  - `get_engine(database_url, pool_size, max_overflow, echo) -> AsyncEngine`
  - `get_session_factory(engine) -> async_sessionmaker[AsyncSession]`
  Factory functions following existing `load_settings()` pattern. Raise ValueError if database_url is empty. Log with structured format.
  Update `src/db/__init__.py` to export `get_engine`, `get_session_factory`.
- **Acceptance criteria**:
  - [ ] `src/db/engine.py` has get_engine() and get_session_factory()
  - [ ] `from src.db import get_engine, get_session_factory` works
  - [ ] ValueError raised if database_url is None/empty
  - [ ] Google docstrings on both functions
  - [ ] ruff + mypy clean
- **Blocked by**: Task 2.1

---

## Track 3: ORM Models (depends on Task 2.1)

### Task 3.1: Create user ORM models (User, Team, TeamMembership)
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/db/models/__init__.py`, `src/db/models/user.py`
- **Description**: Create `src/db/models/` package:
  - `__init__.py` -- imports all ORM models (needed for Alembic discovery)
  - `user.py` -- `UserRole(str, Enum)`, `UserORM`, `TeamORM`, `TeamMembershipORM`
  Match exact column definitions from schema.sql. Include all constraints (UNIQUE, CHECK), all FKs with CASCADE where specified. Include relationships (owner -> owned_teams, user -> memberships, team -> memberships, team -> agents).
  Use `SAEnum(name="user_role", create_constraint=False, native_enum=True)` for PG native enums.
- **Acceptance criteria**:
  - [ ] UserORM matches schema.sql `user` table exactly (all columns, constraints)
  - [ ] TeamORM matches schema.sql `team` table exactly
  - [ ] TeamMembershipORM matches schema.sql `team_membership` table exactly
  - [ ] All relationships defined (bidirectional)
  - [ ] UserRole enum defined
  - [ ] ruff + mypy clean
- **Blocked by**: Task 2.1

### Task 3.2: Create agent ORM model
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/db/models/agent.py`
- **Description**: Create `src/db/models/agent.py`:
  - `AgentStatus(str, Enum)` -- draft/active/paused/archived
  - `AgentORM` -- matches schema.sql `agent` table
  All JSONB columns (personality, model_config_json, memory_config, boundaries) with JSON defaults matching schema.sql. ARRAY(Text) for skill arrays. Unique (team_id, slug) constraint. Slug format CHECK.
  Add relationship to team (back_populates="agents") and conversations.
  Update `src/db/models/__init__.py` to import AgentORM.
- **Acceptance criteria**:
  - [ ] AgentORM matches schema.sql `agent` table exactly
  - [ ] JSONB server_defaults match schema.sql defaults
  - [ ] ARRAY columns for skill names
  - [ ] AgentStatus enum defined
  - [ ] Relationships to TeamORM and ConversationORM
  - [ ] ruff + mypy clean
- **Blocked by**: Task 3.1 (needs UserORM for created_by FK, TeamORM for team_id FK)

### Task 3.3: Create conversation ORM models (Conversation, Message)
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/db/models/conversation.py`
- **Description**: Create `src/db/models/conversation.py`:
  - `ConversationStatus(str, Enum)` -- active/idle/closed
  - `MessageRole(str, Enum)` -- user/assistant/system/tool
  - `ConversationORM` -- matches schema.sql `conversation` table
  - `MessageORM` -- matches schema.sql `message` table
  Include message_count, total_input_tokens, total_output_tokens, summary, metadata JSONB, last_message_at. MessageORM includes tool_calls JSONB, tool_results JSONB, feedback_rating CHECK, feedback_comment.
  Update `src/db/models/__init__.py`.
- **Acceptance criteria**:
  - [ ] ConversationORM matches schema.sql exactly
  - [ ] MessageORM matches schema.sql exactly
  - [ ] Enums defined
  - [ ] Relationships (conversation <-> messages, conversation -> agent)
  - [ ] ruff + mypy clean
- **Blocked by**: Task 3.2 (needs AgentORM for agent_id FK)

### Task 3.4: Create memory ORM models (Memory, MemoryLog, MemoryTag)
- **Agent**: builder
- **Complexity**: L
- **Files owned**: `src/db/models/memory.py`
- **Description**: Create `src/db/models/memory.py`:
  - `MemoryType(str, Enum)` -- 7 types
  - `MemoryStatus(str, Enum)` -- 4 statuses
  - `MemoryTier(str, Enum)` -- 3 tiers
  - `MemorySource(str, Enum)` -- 6 sources
  - `MemoryORM` -- full memory table with Vector(1536) via pgvector
  - `MemoryLogORM` -- append-only audit (NO FK on memory_id)
  - `MemoryTagORM` -- tags with unique (memory_id, tag)
  This is the most complex model. Must handle: self-referential FK (superseded_by), UUID arrays (contradicts, related_to, source_message_ids), nullable Vector column.
  Column name `metadata` mapped as `metadata_json` in Python (avoids SA reserved word).
  Update `src/db/models/__init__.py`.
- **Acceptance criteria**:
  - [ ] MemoryORM matches schema.sql `memory` table exactly (all 30+ columns)
  - [ ] MemoryLogORM matches schema.sql (NO FK on memory_id)
  - [ ] MemoryTagORM matches schema.sql with UNIQUE constraint
  - [ ] 4 enums defined (MemoryType, MemoryStatus, MemoryTier, MemorySource)
  - [ ] Vector(1536) column for embedding
  - [ ] Self-referential FK for superseded_by
  - [ ] UUID arrays for contradicts, related_to, source_message_ids
  - [ ] ruff + mypy clean
- **Blocked by**: Task 3.1 (needs UserORM, TeamORM FKs), Task 3.3 (needs ConversationORM FK)

---

## Track 4: Pydantic Models + Repositories (depends on Track 2/3)

### Task 4.1: Create Pydantic agent models (AgentDNA and sub-models)
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/models/__init__.py`, `src/models/agent_models.py`
- **Description**: Create `src/models/` package:
  - `__init__.py` -- exports key models
  - `agent_models.py` -- all Pydantic models exactly as defined in the phase doc:
    - `AgentStatus(str, Enum)`
    - `RetrievalWeights(BaseModel)` -- 5 weights with Field(ge=0, le=1)
    - `VoiceExample(BaseModel)` -- user_message, agent_response, context
    - `AgentPersonality(BaseModel)` -- tone (Literal), verbosity, formality, language, traits, voice_examples, always_rules, never_rules, custom_instructions
    - `AgentModelConfig(BaseModel)` -- model_name, temperature Field(ge=0, le=2), max_output_tokens Field(ge=100, le=32000)
    - `AgentMemoryConfig(BaseModel)` -- token_budget, retrieval_weights, auto_extract, auto_pin_preferences, summarize_interval, remember_commands
    - `AgentBoundaries(BaseModel)` -- can_do, cannot_do, escalates_to, max_autonomy (Literal), allowed_domains, max_tool_calls_per_turn
    - `AgentDNA(BaseModel)` -- with `effective_skills` computed_field property
- **Acceptance criteria**:
  - [ ] All 8 models match the phase doc definitions exactly
  - [ ] AgentDNA.effective_skills computed correctly (shared + custom - disabled)
  - [ ] Field constraints (ge, le, Literal) on all applicable fields
  - [ ] Google docstrings on all classes
  - [ ] ruff + mypy clean
- **Blocked by**: Task 1.1 (needs pydantic installed -- already is)

### Task 4.2: Create Pydantic memory + conversation + user models
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/models/memory_models.py`, `src/models/conversation_models.py`, `src/models/user_models.py`
- **Description**: Create 3 model files:
  - `memory_models.py` -- MemoryCreate, MemoryRecord, MemorySearchRequest, MemorySearchResult
  - `conversation_models.py` -- ConversationCreate, MessageCreate
  - `user_models.py` -- UserCreate, TeamCreate, TeamMembershipInfo
  All models should have Field constraints matching the DB constraints (importance 1-10, confidence 0-1, etc.). Email validation on UserCreate.
  Update `src/models/__init__.py` to export key models.
- **Acceptance criteria**:
  - [ ] All models defined with appropriate Field constraints
  - [ ] MemoryCreate validates importance (1-10) and confidence (0-1)
  - [ ] UserCreate validates email format
  - [ ] Google docstrings on all classes
  - [ ] ruff + mypy clean
- **Blocked by**: Task 4.1 (reuses enums from agent_models)

### Task 4.3: Create base repository
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/db/repositories/__init__.py`, `src/db/repositories/base.py`
- **Description**: Create `src/db/repositories/` package:
  - `__init__.py` -- exports BaseRepository, MemoryRepository
  - `base.py` -- `BaseRepository[T](Generic[T])` with:
    - `__init__(self, session: AsyncSession, model_class: Type[T])`
    - `get_by_id(id: UUID) -> Optional[T]`
    - `create(**kwargs) -> T`
    - `update(id: UUID, **kwargs) -> Optional[T]`
    - `delete(id: UUID) -> bool`
    - `list(limit: int = 100, offset: int = 0) -> list[T]`
  Use `session.get()` for get_by_id, `session.add()` + `session.flush()` for create, `setattr` loop for update.
- **Acceptance criteria**:
  - [ ] BaseRepository[T] implements all 5 CRUD methods + list
  - [ ] Type annotations on all methods
  - [ ] Google docstrings
  - [ ] ruff + mypy clean
- **Blocked by**: Task 2.2 (needs engine/session types)

### Task 4.4: Create memory repository with vector search
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `src/db/repositories/memory_repo.py`
- **Description**: Create `src/db/repositories/memory_repo.py`:
  - `MemoryRepository(BaseRepository[MemoryORM])` with:
    - `search_by_embedding(embedding, team_id, agent_id, memory_types, limit) -> list[MemoryORM]`
    - `find_similar(embedding, threshold) -> list[MemoryORM]`
    - `update_access(memory_ids: list[UUID]) -> None`
  Uses pgvector's `.cosine_distance()` for ordering. Filters by team_id, status=active, embedding IS NOT NULL. Optional agent_id and memory_type filters.
  Update `src/db/repositories/__init__.py`.
- **Acceptance criteria**:
  - [ ] MemoryRepository extends BaseRepository[MemoryORM]
  - [ ] search_by_embedding uses cosine_distance ordering
  - [ ] find_similar uses threshold-based filtering
  - [ ] update_access batch-updates access_count and last_accessed_at
  - [ ] ruff + mypy clean
- **Blocked by**: Task 4.3, Task 3.4 (needs MemoryORM + BaseRepository)

---

## Track 5: Alembic Migrations (depends on all ORM models)

### Task 5.1: Create Alembic configuration and async env
- **Agent**: builder
- **Complexity**: M
- **Files owned**: `alembic.ini`, `src/db/migrations/env.py`, `src/db/migrations/script.py.mako`, `src/db/migrations/versions/.gitkeep`
- **Description**: Set up Alembic for async migrations:
  - `alembic.ini` -- script_location = src/db/migrations, default sqlalchemy.url
  - `src/db/migrations/env.py` -- async env that imports Base + all models, uses Settings.database_url
  - `src/db/migrations/script.py.mako` -- standard migration template
  - `src/db/migrations/versions/` -- empty dir with .gitkeep
  The env.py must import all ORM models (`from src.db.models import *`) so Alembic detects them.
  Uses `async_engine_from_config` + `NullPool` for migration connections.
- **Acceptance criteria**:
  - [ ] `alembic.ini` configured correctly
  - [ ] `env.py` handles async migrations
  - [ ] `env.py` imports all ORM models
  - [ ] `env.py` reads database_url from Settings
  - [ ] `alembic --help` works (Alembic installed and config found)
  - [ ] ruff + mypy clean on env.py
- **Blocked by**: Task 2.2, Task 3.4 (all ORM models must exist)

### Task 5.2: Create initial migration (9 tables + indexes + functions + triggers)
- **Agent**: builder
- **Complexity**: L
- **Files owned**: `src/db/migrations/versions/001_phase1_foundation.py`
- **Description**: Create the initial Alembic migration manually (not autogenerate -- we need custom SQL for extensions, functions, triggers, IVFFlat index).

  Upgrade creates (in order):
  1. Extensions: uuid-ossp, pgcrypto, vector
  2. 8 ENUM types
  3. 9 tables (user -> team -> team_membership -> agent -> conversation -> message -> memory -> memory_log -> memory_tag)
  4. All indexes from schema.sql (Phase 1 section)
  5. Functions: trigger_set_updated_at, trigger_update_conversation_stats, update_memory_access, reconstruct_memory_at
  6. Triggers: set_updated_at on user/team/agent/conversation/memory, update_conversation_on_message

  Downgrade drops (in reverse order):
  1. Triggers
  2. Functions
  3. Indexes (auto-dropped with tables mostly, but explicit for named ones)
  4. Tables (reverse dependency order)
  5. ENUM types
  6. Do NOT drop extensions

  Use `op.execute()` for raw SQL where SQLAlchemy ops don't support it (functions, triggers, pgvector index).
- **Acceptance criteria**:
  - [ ] Migration creates all 9 tables
  - [ ] Migration creates all 8 ENUM types
  - [ ] Migration creates all Phase 1 indexes (including IVFFlat)
  - [ ] Migration creates all functions and triggers
  - [ ] Downgrade cleanly reverses everything
  - [ ] `alembic upgrade head` succeeds (against a test PG with pgvector)
  - [ ] `alembic downgrade base` succeeds
- **Blocked by**: Task 5.1

---

## Track 6: Tests (can start in parallel with implementation for Pydantic models)

### Task 6.1: Create Pydantic model tests
- **Agent**: tester
- **Complexity**: M
- **Files owned**: `tests/test_models/__init__.py`, `tests/test_models/test_agent_models.py`, `tests/test_models/test_memory_models.py`
- **Description**: Unit tests for all Pydantic models (NO database needed):

  `test_agent_models.py`:
  - AgentDNA creation with all fields
  - AgentDNA.effective_skills computed correctly (shared + custom - disabled)
  - AgentPersonality defaults (tone=friendly, verbosity=balanced, etc.)
  - AgentModelConfig constraints (temperature 0-2, max_output_tokens 100-32000)
  - AgentMemoryConfig defaults (token_budget=2000, etc.)
  - AgentBoundaries defaults (max_autonomy=execute)
  - RetrievalWeights defaults sum check
  - VoiceExample creation
  - AgentStatus enum values

  `test_memory_models.py`:
  - MemoryCreate with valid importance (1-10)
  - MemoryCreate rejects invalid importance (0, 11)
  - MemoryCreate with valid confidence (0.0-1.0)
  - MemoryCreate rejects invalid confidence (-0.1, 1.1)
  - MemoryRecord full field coverage
  - MemorySearchRequest defaults
- **Acceptance criteria**:
  - [ ] 15+ test cases covering all Pydantic models
  - [ ] All tests pass: `.venv/bin/python -m pytest tests/test_models/ -v`
  - [ ] Tests validate constraints (rejection of invalid values)
  - [ ] Tests validate computed fields (effective_skills)
  - [ ] Tests validate defaults
  - [ ] ruff clean on test files
- **Blocked by**: Task 4.1, Task 4.2

### Task 6.2: Create database test infrastructure and ORM tests
- **Agent**: tester
- **Complexity**: M
- **Files owned**: `tests/test_db/__init__.py`, `tests/test_db/conftest.py`, `tests/test_db/test_engine.py`, `tests/test_db/test_models.py`
- **Description**: Create test infrastructure and ORM tests:

  `conftest.py`:
  - Fixtures for test engine (skips if DATABASE_URL not set)
  - Fixtures for test session (rollback after each test)
  - Mark all tests with `@pytest.mark.integration`

  `test_engine.py`:
  - Test get_engine creates valid engine
  - Test get_engine raises ValueError without URL
  - Test get_session_factory creates sessions

  `test_models.py`:
  - Test UserORM instantiation and column defaults
  - Test TeamORM instantiation and column defaults
  - Test AgentORM JSONB defaults
  - Test MemoryORM column types and nullable fields
  - Test MemoryLogORM has no FK on memory_id
  - Test enum values match expected strings

  For tests requiring a live database, use `pytest.mark.skipif` to skip when DATABASE_URL is not configured.
- **Acceptance criteria**:
  - [ ] conftest.py provides engine and session fixtures
  - [ ] Tests skip gracefully without DATABASE_URL
  - [ ] test_engine.py covers engine creation and error cases
  - [ ] test_models.py covers ORM model instantiation
  - [ ] All tests pass: `.venv/bin/python -m pytest tests/test_db/ -v`
  - [ ] ruff clean
- **Blocked by**: Task 3.4, Task 2.2

### Task 6.3: Create repository tests
- **Agent**: tester
- **Complexity**: M
- **Files owned**: `tests/test_db/test_repositories.py`
- **Description**: Integration tests for repository layer:
  - BaseRepository CRUD: create, get_by_id, update, delete, list
  - MemoryRepository.search_by_embedding (requires test data with embeddings)
  - MemoryRepository.find_similar
  - MemoryRepository.update_access
  All tests require a running PostgreSQL with pgvector. Mark with `@pytest.mark.integration` and skip without DATABASE_URL.
- **Acceptance criteria**:
  - [ ] CRUD tests for BaseRepository
  - [ ] Vector search tests for MemoryRepository
  - [ ] Tests skip without DATABASE_URL
  - [ ] All tests pass with a configured test database
  - [ ] ruff clean
- **Blocked by**: Task 4.4, Task 6.2

---

## Track 7: Verification (depends on everything)

### Task 7.1: Integration verification and backward compatibility check
- **Agent**: tester
- **Complexity**: S
- **Files owned**: none (read-only verification)
- **Description**: Final verification that Phase 1 is complete and backward compatible:
  1. `python -m src.cli` starts without errors (no DB configured)
  2. `.venv/bin/python -m pytest tests/ -v` -- ALL tests pass (existing + new)
  3. `ruff check src/ tests/` -- clean
  4. `ruff format --check src/ tests/` -- clean
  5. `mypy src/` -- clean
  6. No import errors from new modules
  7. No circular dependencies introduced
  If a live PG+pgvector is available:
  8. `alembic upgrade head` creates all 9 tables
  9. `alembic downgrade base` drops cleanly
  10. Repository CRUD works
- **Acceptance criteria**:
  - [ ] All 7 non-DB checks pass
  - [ ] All existing tests still pass (zero regressions)
  - [ ] CLI works unchanged
- **Blocked by**: All previous tasks

---

## Dependency Graph

```
Track 1 (Config):
  1.1 pyproject.toml
  1.2 settings.py
  1.3 .env.example
  (all 3 can run in parallel, no deps)

Track 2 (DB Infra):
  2.1 base.py ──────── blocked by: 1.1
  2.2 engine.py ─────── blocked by: 2.1

Track 3 (ORM Models):
  3.1 user.py ────────── blocked by: 2.1
  3.2 agent.py ────────── blocked by: 3.1
  3.3 conversation.py ─── blocked by: 3.2
  3.4 memory.py ────────── blocked by: 3.1, 3.3

Track 4 (Pydantic + Repos):
  4.1 agent_models.py ─── blocked by: nothing (pure Pydantic)
  4.2 memory/conv/user ── blocked by: 4.1
  4.3 base repo ────────── blocked by: 2.2
  4.4 memory repo ──────── blocked by: 4.3, 3.4

Track 5 (Alembic):
  5.1 alembic config ──── blocked by: 2.2, 3.4
  5.2 initial migration ── blocked by: 5.1

Track 6 (Tests):
  6.1 pydantic tests ──── blocked by: 4.1, 4.2
  6.2 ORM + engine tests ─ blocked by: 3.4, 2.2
  6.3 repo tests ────────── blocked by: 4.4, 6.2

Track 7 (Verification):
  7.1 integration check ── blocked by: ALL
```

## Critical Path

The longest dependency chain:
```
1.1 -> 2.1 -> 3.1 -> 3.2 -> 3.3 -> 3.4 -> 5.1 -> 5.2 -> 7.1
```

This is 8 tasks deep. However, many tasks can run in parallel:
- 1.1, 1.2, 1.3 in parallel
- 4.1 can start immediately (no deps)
- 3.1 and 2.2 can run in parallel (both need 2.1)
- 4.3 can run after 2.2 (parallel with Track 3)
- 6.1 can run after 4.1+4.2 (parallel with Track 3)

**Realistic parallel execution**: 5-6 sessions total.
