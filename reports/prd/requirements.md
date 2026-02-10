# Requirements: Phase 1 - Database Foundation
Status: COMPLETE

## Overview
Add PostgreSQL infrastructure, ORM models, repository layer, Pydantic models, and Alembic migrations to the existing skill-based agent codebase. Zero behavior changes to existing functionality.

## Mode: EXISTING CODEBASE
Integrating into a working CLI agent at `src/`. All new DB fields must be Optional to preserve CLI-only operation.

---

## Functional Requirements

### FR-1: PostgreSQL Engine and Session Management
- Async engine via SQLAlchemy 2.0 + asyncpg
- Connection pooling (configurable pool_size, max_overflow)
- Session factory with `expire_on_commit=False`
- Engine creation only when `database_url` is configured (lazy)

### FR-2: Declarative Base and Mixins
- `Base(DeclarativeBase)` as ORM foundation
- `UUIDMixin` -- UUID primary key with `gen_random_uuid()` default
- `TimestampMixin` -- `created_at` (server_default NOW) + `updated_at` (onupdate NOW)

### FR-3: ORM Models (9 Tables)

#### FR-3.1: User Model
- UUID PK, email (unique, format-validated), password_hash (bcrypt), display_name, is_active, timestamps
- Constraint: `email ~* '^[^@]+@[^@]+\.[^@]+$'`

#### FR-3.2: Team Model
- UUID PK, name, slug (unique, format-validated), owner_id FK(user), settings JSONB, shared_skill_names TEXT[], webhook_url, webhook_secret, conversation_retention_days, timestamps
- Constraint: `slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'`

#### FR-3.3: TeamMembership Model
- UUID PK, user_id FK(user CASCADE), team_id FK(team CASCADE), role ENUM(owner/admin/member/viewer), created_at
- Unique constraint: (user_id, team_id)

#### FR-3.4: Agent Model (AgentDNA storage)
- UUID PK, team_id FK(team CASCADE), name, slug, tagline, avatar_emoji
- personality JSONB (serialized AgentPersonality)
- shared_skill_names TEXT[], custom_skill_names TEXT[], disabled_skill_names TEXT[]
- model_config_json JSONB (serialized AgentModelConfig, with JSON defaults)
- memory_config JSONB (serialized AgentMemoryConfig, with JSON defaults)
- boundaries JSONB (serialized AgentBoundaries, with JSON defaults)
- status ENUM(draft/active/paused/archived), created_by FK(user), timestamps
- Unique constraint: (team_id, slug)
- Constraint: `slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'`

#### FR-3.5: Conversation Model
- UUID PK, team_id FK(team CASCADE), agent_id FK(agent), user_id FK(user), title, status ENUM(active/idle/closed), message_count, total_input_tokens, total_output_tokens, summary, metadata JSONB, timestamps, last_message_at

#### FR-3.6: Message Model
- UUID PK, conversation_id FK(conversation CASCADE), agent_id FK(agent, nullable), role ENUM(user/assistant/system/tool), content TEXT, tool_calls JSONB, tool_results JSONB, token_count, model TEXT, feedback_rating CHECK(positive/negative), feedback_comment, created_at

#### FR-3.7: Memory Model (single table, all 7 types)
- UUID PK, team_id FK(team CASCADE), agent_id FK(agent, nullable), user_id FK(user, nullable)
- memory_type ENUM(semantic/episodic/procedural/agent_private/shared/identity/user_profile)
- content TEXT, subject TEXT, embedding vector(1536)
- importance INT (1-10), confidence FLOAT (0-1), access_count, is_pinned
- source_type ENUM(extraction/explicit/system/feedback/consolidation/compaction)
- source_conversation_id FK(conversation), source_message_ids UUID[], extraction_model TEXT
- version INT, superseded_by FK(memory, self-ref), contradicts UUID[], related_to UUID[]
- metadata JSONB, tier ENUM(hot/warm/cold), status ENUM(active/superseded/archived/disputed)
- timestamps + last_accessed_at + expires_at

#### FR-3.8: MemoryLog Model (append-only audit)
- UUID PK, memory_id UUID (NO FK intentionally), action TEXT
- old_content, new_content, old_importance, new_importance, old_tier, new_tier, old_status, new_status
- changed_by TEXT, reason TEXT, conversation_id UUID, related_memory_ids UUID[]
- created_at

#### FR-3.9: MemoryTag Model
- UUID PK, memory_id FK(memory CASCADE), tag TEXT, created_at
- Unique constraint: (memory_id, tag)

### FR-4: ENUM Types (8 for Phase 1)
- user_role, agent_status, message_role, memory_type_enum, memory_status, memory_tier, memory_source, conversation_status

### FR-5: Indexes
- IVFFlat vector index on memory.embedding (lists=100, vector_cosine_ops)
- Filtered indexes on memory (team_id+type+status, agent, user_profile, recency, importance, subject, tier, expiration, conversation)
- Message index on (conversation_id, created_at)
- Agent index on (team_id, status)
- User email index, Team slug index, TeamMembership user/team indexes
- Conversation indexes (team, user, agent, active status)
- MemoryLog indexes (memory_id+created_at, created_at)
- MemoryTag indexes (tag, memory_id)

### FR-6: Database Functions
- `trigger_set_updated_at()` -- auto-update updated_at on UPDATE
- `trigger_update_conversation_stats()` -- auto-increment message_count + last_message_at on INSERT to message
- `update_memory_access(memory_ids UUID[])` -- batch update access_count + last_accessed_at
- `reconstruct_memory_at(p_memory_id, p_timestamp)` -- point-in-time memory reconstruction from audit log

### FR-7: Triggers
- `set_updated_at_user`, `set_updated_at_team`, `set_updated_at_agent`, `set_updated_at_conversation`, `set_updated_at_memory` -- on BEFORE UPDATE
- `update_conversation_on_message` -- on AFTER INSERT on message

### FR-8: Repository Layer
- `BaseRepository[T]` -- generic CRUD (get_by_id, create, update, delete)
- `MemoryRepository(BaseRepository[MemoryORM])` -- search_by_embedding, find_similar

### FR-9: Pydantic Models (API/Domain Layer)
- `AgentDNA`, `AgentPersonality`, `VoiceExample`, `AgentModelConfig`, `AgentMemoryConfig`, `AgentBoundaries`, `AgentStatus`, `RetrievalWeights`
- `MemoryCreate`, `MemoryRecord`, `MemorySearchRequest`, `MemorySearchResult`
- `ConversationCreate`, `MessageCreate`
- `UserCreate`, `TeamCreate`, `TeamMembership`

### FR-10: Alembic Migration Infrastructure
- Async Alembic env.py targeting the async engine
- Initial migration creating all 9 tables, 8 enums, indexes, functions, triggers
- `alembic upgrade head` creates everything
- `alembic downgrade base` drops everything cleanly

### FR-11: Settings Extensions
- `database_url: Optional[str]` (default None)
- `database_pool_size: int` (default 5, ge=1, le=50)
- `database_pool_overflow: int` (default 10, ge=0, le=100)
- `embedding_model: str` (default "text-embedding-3-small")
- `embedding_api_key: Optional[str]` (default None)
- `embedding_dimensions: int` (default 1536)

### FR-12: Dependencies Updates
- `pyproject.toml`: add sqlalchemy[asyncio]~=2.0.36, asyncpg~=0.30.0, alembic~=1.14.0, pgvector~=0.3.6
- `.env.example`: add DATABASE_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL placeholders

---

## Non-Functional Requirements

### NFR-1: Backward Compatibility (CRITICAL)
- `python -m src.cli` MUST work unchanged with no database configured
- All existing tests MUST pass without modification
- All new Settings fields MUST be Optional or have defaults
- No import-time side effects from new modules

### NFR-2: Performance
- Connection pooling: configurable pool_size (default 5) and overflow (default 10)
- IVFFlat index with lists=100 for vector search performance
- Partial indexes on memory table to reduce scan overhead

### NFR-3: Security
- Password hashing: bcrypt, min 12 rounds (stored as password_hash)
- Email format validation via CHECK constraint
- Slug format validation via CHECK constraint
- webhook_secret stored as-is (will be encrypted in later phases)
- No secret values logged

### NFR-4: Type Safety
- All ORM models fully typed using SQLAlchemy 2.0 Mapped[] syntax
- All Pydantic models fully typed with Field constraints
- mypy must pass on all new code

### NFR-5: Testing
- Unit tests for all Pydantic models (validation, defaults, computed fields)
- Unit tests for ORM model relationships (using in-memory SQLite or test fixtures)
- Integration tests for repository CRUD (requires test PostgreSQL with pgvector)
- Integration tests for vector search
- All tests must pass: `.venv/bin/python -m pytest tests/ -v`

### NFR-6: Code Quality
- ruff format and ruff check must pass on all new files
- Google-style docstrings on all public functions/classes
- Structured logging format: `f"action_name: key={value}"`

---

## Edge Cases

### EC-1: No Database Configured
- Engine module returns None or raises clear error if database_url is None
- Repository constructors fail gracefully with clear message
- CLI operates normally with skill_loader only

### EC-2: Database Connection Failure
- Engine creation fails with clear error message (not leaking connection string)
- Session factory raises descriptive error

### EC-3: Missing pgvector Extension
- Migration should CREATE EXTENSION IF NOT EXISTS
- Clear error if vector extension not available

### EC-4: Memory Model Validation
- importance must be 1-10 (both Pydantic and DB constraint)
- confidence must be 0.0-1.0 (both Pydantic and DB constraint)
- memory_type must be one of 7 valid values
- superseded_by self-referential FK allowed

### EC-5: Empty Embedding
- Memory can be created without embedding (nullable)
- Vector search skips memories with NULL embedding

### EC-6: Memory Log Integrity
- memory_log.memory_id has NO FK (intentional -- survives deletes)
- All log entries are append-only, never modified

---

## Success Criteria

1. `alembic upgrade head` creates all 9 tables, 8 enums, indexes, functions, triggers
2. `alembic downgrade base` drops everything cleanly
3. Repository CRUD works for all entities (user, team, agent, conversation, message, memory)
4. Vector search returns results sorted by cosine similarity
5. `python -m src.cli` works unchanged (no DB required)
6. All existing tests pass without modification
7. All new tests pass
8. `ruff check src/ tests/` -- clean
9. `mypy src/` -- clean

---

## Integration Points (Existing Code Touched)

| File | Change | Risk |
|------|--------|------|
| `src/settings.py` | Add 6 Optional DB/embedding fields | LOW -- all Optional with defaults |
| `pyproject.toml` | Add 4 dependencies | LOW -- additive only |
| `.env.example` | Add 3 placeholder lines | LOW -- additive only |
| `src/dependencies.py` | No changes in Phase 1 | NONE -- touched in later phases |

All new code goes into `src/db/`, `src/models/`, and `tests/test_db/`, `tests/test_models/`.
