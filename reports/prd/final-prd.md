# PRD: Phase 1 - Database Foundation

## Overview

Add PostgreSQL infrastructure to the existing skill-based agent codebase. This phase creates the persistence layer (ORM models, repositories, migrations) that all subsequent phases build on. Zero behavior changes -- the existing CLI must continue to work unchanged without a database configured.

## Mode: EXISTING CODEBASE

The project has a working CLI agent at `src/` with 11 modules, 5 skill directories, and a test suite. Phase 1 adds new modules (`src/db/`, `src/models/`) without modifying existing behavior. Only 3 existing files are touched: `src/settings.py` (+6 Optional fields), `pyproject.toml` (+4 deps), `.env.example` (+3 placeholder lines).

---

## Requirements Summary

### What We're Building
- **9 database tables**: user, team, team_membership, agent, conversation, message, memory, memory_log, memory_tag
- **8 PostgreSQL ENUM types**: user_role, agent_status, message_role, memory_type_enum, memory_status, memory_tier, memory_source, conversation_status
- **ORM layer**: SQLAlchemy 2.0 async models with Mapped[] syntax
- **Repository layer**: BaseRepository[T] generic CRUD + MemoryRepository with pgvector search
- **Pydantic models**: AgentDNA (8 models), memory models, conversation models, user models
- **Alembic migrations**: Async env + initial migration with tables, indexes, functions, triggers
- **Settings**: 6 Optional DB/embedding fields

### Critical Constraint
```
python -m src.cli              # MUST still work (no DB required)
.venv/bin/python -m pytest tests/ -v  # ALL existing tests MUST pass
ruff check src/ tests/         # MUST be clean
mypy src/                      # MUST be clean
```

---

## Architecture

### New Directory Structure
```
src/
    db/
        __init__.py          # Exports: get_engine, get_session_factory, Base
        engine.py            # AsyncEngine + session factory
        base.py              # DeclarativeBase + UUIDMixin + TimestampMixin
        models/
            __init__.py      # Imports all ORM models for Alembic
            user.py          # UserORM, TeamORM, TeamMembershipORM, UserRole
            agent.py         # AgentORM, AgentStatus
            conversation.py  # ConversationORM, MessageORM, enums
            memory.py        # MemoryORM, MemoryLogORM, MemoryTagORM, 4 enums
        repositories/
            __init__.py
            base.py          # BaseRepository[T]
            memory_repo.py   # MemoryRepository (vector search)
        migrations/
            env.py           # Async Alembic env
            script.py.mako
            versions/
                001_phase1_foundation.py
    models/
        __init__.py
        agent_models.py      # AgentDNA + 7 sub-models
        memory_models.py     # MemoryCreate, MemoryRecord, etc.
        conversation_models.py
        user_models.py
    settings.py              # MODIFIED (+6 Optional fields)

alembic.ini                  # NEW
pyproject.toml               # MODIFIED (+4 deps)
.env.example                 # MODIFIED (+3 placeholders)
```

### Key Design Decisions
1. **ORM suffix convention**: `UserORM`, `MemoryORM` to avoid collision with Pydantic model names
2. **Factory functions** (not classes) for engine/session -- matches existing `load_settings()` pattern
3. **server_default=text("gen_random_uuid()")** for UUIDs -- uses PG-native generation
4. **memory_log has NO FK on memory_id** -- intentional, survives deletes (ADR-8)
5. **Column name `metadata` mapped as `metadata_json`** in Python -- avoids SQLAlchemy reserved word
6. **All Settings fields Optional** -- preserves CLI-only operation

---

## Task Tree (16 Tasks)

### Track 1: Project Config (no dependencies)

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 1.1 | Add database dependencies to pyproject.toml | builder | S | pyproject.toml | -- |
| 1.2 | Extend settings.py with database fields | builder | S | src/settings.py | -- |
| 1.3 | Update .env.example with database placeholders | builder | S | .env.example | -- |

### Track 2: Database Infrastructure

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 2.1 | Create database base module (Base + Mixins) | builder | S | src/db/__init__.py, src/db/base.py | 1.1 |
| 2.2 | Create database engine module | builder | S | src/db/engine.py | 2.1 |

### Track 3: ORM Models

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 3.1 | Create user ORM models | builder | M | src/db/models/__init__.py, src/db/models/user.py | 2.1 |
| 3.2 | Create agent ORM model | builder | M | src/db/models/agent.py | 3.1 |
| 3.3 | Create conversation ORM models | builder | M | src/db/models/conversation.py | 3.2 |
| 3.4 | Create memory ORM models | builder | L | src/db/models/memory.py | 3.1, 3.3 |

### Track 4: Pydantic Models + Repositories

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 4.1 | Create Pydantic agent models (AgentDNA) | builder | M | src/models/__init__.py, src/models/agent_models.py | -- |
| 4.2 | Create Pydantic memory/conversation/user models | builder | M | src/models/memory_models.py, conversation_models.py, user_models.py | 4.1 |
| 4.3 | Create base repository | builder | M | src/db/repositories/__init__.py, src/db/repositories/base.py | 2.2 |
| 4.4 | Create memory repository with vector search | builder | M | src/db/repositories/memory_repo.py | 4.3, 3.4 |

### Track 5: Alembic Migrations

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 5.1 | Create Alembic config and async env | builder | M | alembic.ini, src/db/migrations/env.py, script.py.mako | 2.2, 3.4 |
| 5.2 | Create initial migration (9 tables) | builder | L | src/db/migrations/versions/001_... | 5.1 |

### Track 6: Tests

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 6.1 | Create Pydantic model tests | tester | M | tests/test_models/ | 4.1, 4.2 |
| 6.2 | Create DB test infrastructure + ORM tests | tester | M | tests/test_db/ | 3.4, 2.2 |
| 6.3 | Create repository tests | tester | M | tests/test_db/test_repositories.py | 4.4, 6.2 |

### Track 7: Verification

| # | Task | Agent | Size | Files | Blocked By |
|---|------|-------|------|-------|------------|
| 7.1 | Integration verification + backward compat | tester | S | (read-only) | ALL |

---

## Implementation Order

### Wave 1 (Parallel -- no dependencies)
```
1.1  Add dependencies to pyproject.toml
1.2  Extend settings.py
1.3  Update .env.example
4.1  Create Pydantic agent models (AgentDNA)
```

### Wave 2 (After Wave 1)
```
2.1  Create base.py (Base + Mixins)          -- needs 1.1
4.2  Create remaining Pydantic models         -- needs 4.1
```

### Wave 3 (After Wave 2)
```
2.2  Create engine.py                         -- needs 2.1
3.1  Create user ORM models                   -- needs 2.1
6.1  Create Pydantic model tests              -- needs 4.1 + 4.2
```

### Wave 4 (After Wave 3)
```
3.2  Create agent ORM model                   -- needs 3.1
4.3  Create base repository                   -- needs 2.2
```

### Wave 5 (After Wave 4)
```
3.3  Create conversation ORM models           -- needs 3.2
```

### Wave 6 (After Wave 5)
```
3.4  Create memory ORM models                 -- needs 3.1 + 3.3
```

### Wave 7 (After Wave 6)
```
4.4  Create memory repository                 -- needs 4.3 + 3.4
5.1  Create Alembic config                    -- needs 2.2 + 3.4
6.2  Create DB test infrastructure            -- needs 3.4 + 2.2
```

### Wave 8 (After Wave 7)
```
5.2  Create initial migration                 -- needs 5.1
6.3  Create repository tests                  -- needs 4.4 + 6.2
```

### Wave 9 (Final)
```
7.1  Integration verification                 -- needs ALL
```

---

## Risk Areas

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| pgvector not available in test PG | DB integration tests fail | Medium | Skip tests without pgvector; document setup requirement |
| SQLAlchemy 2.0 Mapped[] type issues with mypy | Type errors block completion | Low | Use sqlalchemy-stubs or type:ignore on known gaps |
| Alembic async env configuration complexity | Migration doesn't run | Low | Phase doc provides exact env.py pattern |
| ORM JSONB server_defaults with complex JSON | Syntax errors in migration | Medium | Use text() wrapper for all server_default SQL |
| Circular imports between ORM models | ImportError at module load | Medium | Use string-based relationship targets ("UserORM") + TYPE_CHECKING |
| Memory model complexity (30+ columns) | Bugs in column definitions | Medium | Test each column independently; compare against schema.sql |

---

## Files Created/Modified Summary

| Category | Count | Details |
|----------|-------|---------|
| New Python modules | 17 | src/db/ (8), src/models/ (5), tests/ (4) |
| New config files | 3 | alembic.ini, script.py.mako, .gitkeep |
| Modified files | 3 | settings.py, pyproject.toml, .env.example |
| Total new/modified | 23 | |
