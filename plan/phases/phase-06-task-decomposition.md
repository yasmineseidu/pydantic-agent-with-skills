# Phase 6: Background Processing - Task Decomposition

> **29 atomic tasks** | **9 waves** | **~68 new tests** | **17 new files** | **3 existing files modified**
>
> Decomposed: 2026-02-10 | Prerequisites: Phase 4 (Auth+API), Phase 2 (Memory), Phase 3 (Redis)

---

## Critical Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Async bridge | `asyncio.run()` in `workers/utils.py` | Safe in Celery prefork model (each worker = own process) |
| Session mgmt | Tasks create own `AsyncSession` (pool_size=3) | Separate from FastAPI pool (5); tasks run outside request lifecycle |
| Serialization | UUIDs as strings in Celery args | JSON serializer (no pickle = security); convert back inside task |
| Consolidation | Split into 3 tasks + 2 helpers | Phase 1 (merge), Phase 2 (summarize), Phase 3-4 (decay) = manageable context |
| Degradation | Feature flag + try/except fallback | `enable_background_processing` gates Celery; falls back to asyncio |
| No new deps on AgentDependencies | Tasks construct own services | No coupling between Celery and FastAPI DI |

---

## Wave Execution Plan

```
WAVE 1 (2 tasks, 0 deps) ─────────────────────────────────────
  #1  pyproject.toml: add celery[redis]
  #2  settings.py: add enable_background_processing flag

WAVE 2 (2 tasks) ─────────────────────────────────────────────
  #3  ScheduledJobORM model                     ← #1
  #5  workers/__init__.py + celery_app.py       ← #1, #2

WAVE 3 (6 tasks, max parallelism) ────────────────────────────
  #4  Alembic migration 003                     ← #3
  #6  workers/tasks/__init__.py                 ← #5
  #7  workers/utils.py (async bridge)           ← #5
  #15 tests/test_workers/conftest.py            ← #5
  #22 tests for ScheduledJobORM                 ← #3
  #23 update test_table_count                   ← #3

WAVE 4 (4 tasks) ─────────────────────────────────────────────
  #8  memory_tasks.py: extract_memories         ← #6, #7
  #11 agent_tasks.py: scheduled_agent_run       ← #3, #6, #7
  #12 cleanup_tasks.py: 4 cleanup tasks         ← #6, #7
  #16 tests for utils.py                        ← #7, #15

WAVE 5 (6 tasks) ─────────────────────────────────────────────
  #9  consolidation Phase 1: merge dupes        ← #8
  #10 consolidation Phase 3-4: decay/cache      ← #8
  #14 chat.py Celery dispatch + fallback        ← #2, #8
  #26 agent_tasks.py: delivery + job tracking   ← #11
  #18 tests for agent_tasks                     ← #11, #15
  #19 tests for cleanup_tasks                   ← #12, #15

WAVE 6 (5 tasks) ─────────────────────────────────────────────
  #25 consolidation Phase 2: summarize episodic ← #9
  #13 schedules.py: static beat schedule        ← #8, #9, #10, #11, #12
  #17 tests for extract_memories                ← #8, #15
  #29 tests for decay/expire                    ← #10, #15
  #21 tests for chat.py integration             ← #14, #15

WAVE 7 (3 tasks) ─────────────────────────────────────────────
  #28 tests for consolidation (Phase 1+2)       ← #9, #25, #15
  #27 dynamic schedule loader from DB           ← #3, #13
  #20 tests for schedules.py                    ← #13, #15

WAVE 8 (1 task) ──────────────────────────────────────────────
  #26 tests for delivery + job tracking         (covered by #18 extension)

WAVE 9 (final) ───────────────────────────────────────────────
  #24 Full regression: 833+ tests pass          ← ALL
```

### Critical Path (longest chain)
```
#1 → #5 → #7 → #8 → #9 → #25 → #28 → #24   (8 hops)
```

---

## File Ownership Map

| File | Task(s) | Action |
|------|---------|--------|
| `pyproject.toml` | #1 | MODIFY (add 1 dep) |
| `src/settings.py` | #2 | MODIFY (add 1 flag) |
| `src/db/models/scheduled_job.py` | #3 | CREATE |
| `src/db/models/__init__.py` | #3 | MODIFY (add import) |
| `src/db/migrations/versions/003_phase6_scheduled_job.py` | #4 | CREATE |
| `workers/__init__.py` | #5 | CREATE |
| `workers/celery_app.py` | #5 | CREATE |
| `workers/tasks/__init__.py` | #6 | CREATE |
| `workers/utils.py` | #7 | CREATE |
| `workers/tasks/memory_tasks.py` | #8 → #9 → #25 | CREATE → APPEND → APPEND |
| `workers/tasks/agent_tasks.py` | #11 → #26 | CREATE → APPEND |
| `workers/tasks/cleanup_tasks.py` | #12 | CREATE |
| `workers/schedules.py` | #13 → #27 | CREATE → APPEND |
| `src/api/routers/chat.py` | #14 | MODIFY (2 locations) |
| `tests/test_workers/__init__.py` | #15 | CREATE |
| `tests/test_workers/conftest.py` | #15 | CREATE |
| `tests/test_workers/test_utils.py` | #16 | CREATE |
| `tests/test_workers/test_memory_tasks.py` | #17 → #28 → #29 | CREATE → APPEND → APPEND |
| `tests/test_workers/test_agent_tasks.py` | #18 | CREATE |
| `tests/test_workers/test_cleanup_tasks.py` | #19 | CREATE |
| `tests/test_workers/test_schedules.py` | #20 | CREATE |
| `tests/test_workers/test_chat_integration.py` | #21 | CREATE |
| `tests/test_workers/test_scheduled_job_model.py` | #22 | CREATE |
| `tests/test_db/test_models.py` | #23 | MODIFY (assertion count) |

---

## All 29 Tasks - Full Detail

### WAVE 1: Foundation

#### Task #1: Add celery[redis] dependency to pyproject.toml
- **File**: `pyproject.toml`
- **Change**: Add `"celery[redis]~=5.4.0"` to `[project] dependencies` array (line ~26)
- **Dev dep**: Add `"celery[pytest]~=5.4.0"` to `[dependency-groups] dev` array
- **Verify**: `uv pip install -e . && python -c "import celery; print(celery.__version__)"`
- **Lines of code**: ~2
- **Context reads**: 1 file (pyproject.toml)

#### Task #2: Add enable_background_processing feature flag
- **File**: `src/settings.py` (line 30, inside `FeatureFlags` class)
- **Change**: Add one field:
  ```python
  enable_background_processing: bool = Field(
      default=False, description="Phase 6: Celery background tasks"
  )
  ```
- **Verify**: `python -c "from src.settings import FeatureFlags; f=FeatureFlags(); print(f.enable_background_processing)"`
- **Lines of code**: 3
- **Context reads**: 1 file (settings.py)

---

### WAVE 2: Models + Celery App

#### Task #3: Create ScheduledJobORM model
- **File**: `src/db/models/scheduled_job.py` (CREATE)
- **Also modify**: `src/db/models/__init__.py` (add import)
- **Pattern**: Follow `src/db/models/agent.py` for Base, UUIDMixin, TimestampMixin
- **Fields**: id (UUID PK), team_id (FK→team), agent_id (FK→agent), user_id (FK→user), name (Text), message (Text), cron_expression (Text), timezone (Text, default='UTC'), is_active (Boolean, default=True), last_run_at (DateTime nullable), next_run_at (DateTime nullable), run_count (Integer, default=0), consecutive_failures (Integer, default=0), last_error (Text nullable), delivery_config (JSONB, default='{}'), created_at, updated_at
- **Indexes**: idx_job_next_run (next_run_at WHERE is_active=TRUE), idx_job_team (team_id)
- **Verify**: `python -c "from src.db.models.scheduled_job import ScheduledJobORM; print(ScheduledJobORM.__tablename__)"`
- **Lines of code**: ~60
- **Context reads**: 1 file (agent.py for pattern)

#### Task #5: Create workers/__init__.py and celery_app.py
- **Files**: `workers/__init__.py` (empty), `workers/celery_app.py`
- **Config**: broker_url from settings.redis_url, result_backend same, JSON serializer, acks_late, worker_prefetch_multiplier=1
- **Function**: `get_celery_app()` singleton
- **Verify**: `python -c "from workers.celery_app import get_celery_app; app=get_celery_app(); print(app.main)"`
- **Lines of code**: ~45
- **Context reads**: 1 file (settings.py for redis_url)

---

### WAVE 3: Utilities + Migration

#### Task #4: Alembic migration 003 for scheduled_job table
- **File**: `src/db/migrations/versions/003_phase6_scheduled_job.py` (CREATE)
- **Pattern**: Follow `002_phase4_auth_api.py` for structure
- **SQL**: CREATE TABLE scheduled_job + indexes + trigger (from plan SQL)
- **Verify**: Migration file imports correctly, has upgrade() and downgrade()
- **Lines of code**: ~80
- **Context reads**: 1 file (002_phase4_auth_api.py for pattern)

#### Task #6: Create workers/tasks/__init__.py
- **File**: `workers/tasks/__init__.py` (CREATE, empty)
- **Content**: `"""Background task modules for Celery workers."""`
- **Lines of code**: 1

#### Task #7: Create async bridge utility
- **File**: `workers/utils.py` (CREATE)
- **Functions**: `run_async(coro)`, `get_task_engine()`, `get_task_session_factory()`, `get_task_settings()`
- **Pattern**: Module-level engine/session_factory cache (singleton per worker process)
- **Key detail**: pool_size=3 (smaller than FastAPI's 5), expire_on_commit=False
- **Verify**: All 4 functions importable, `run_async` executes simple coroutine
- **Lines of code**: ~55
- **Context reads**: 1 file (src/db/engine.py for pattern)

#### Task #15: Create test conftest with Celery eager fixtures
- **Files**: `tests/test_workers/__init__.py` (empty), `tests/test_workers/conftest.py`
- **Fixtures**: `celery_eager` (sets CELERY_ALWAYS_EAGER=True), `mock_session_factory` (returns AsyncMock session), `mock_settings` (returns mock Settings with all required fields), `mock_hot_cache` (mock HotMemoryCache)
- **Pattern**: Follow `tests/test_cache/conftest.py` for mock patterns
- **Lines of code**: ~50
- **Context reads**: 1 file (test_cache/conftest.py for pattern)

#### Task #22: Create tests for ScheduledJobORM
- **File**: `tests/test_workers/test_scheduled_job_model.py` (CREATE)
- **Tests**: Model instantiation, field defaults, required fields, relationship FKs, JSON serialization of delivery_config
- **Estimated tests**: ~8
- **Lines of code**: ~80

#### Task #23: Update test_table_count assertion
- **File**: `tests/test_db/test_models.py`
- **Change**: Update the table count assertion (previously updated from 9→13 in Phase 4)
- **New count**: 13 → 14 (adding scheduled_job)
- **Lines of code**: 1 line change

---

### WAVE 4: Core Task Implementations

#### Task #8: Create extract_memories Celery task
- **File**: `workers/tasks/memory_tasks.py` (CREATE)
- **Implements**: `extract_memories` @shared_task wrapping `MemoryExtractor.extract_from_conversation()`
- **Key**: UUIDs as strings in args, converted to UUID() inside. Fresh session + services per invocation.
- **Retry**: max_retries=3, exponential backoff (30s base), acks_late=True
- **Returns**: `{"memories_created": N, "memories_versioned": N, "duplicates_skipped": N, "contradictions_found": N}`
- **Lines of code**: ~90
- **Context reads**: 1 file (workers/utils.py)

#### Task #11: Create scheduled_agent_run core task
- **File**: `workers/tasks/agent_tasks.py` (CREATE)
- **Implements**: `scheduled_agent_run` @shared_task that loads ScheduledJobORM, runs agent, persists conversation
- **MVP scope**: Load job → verify active → create conversation → call LLM via httpx → persist messages
- **Retry**: max_retries=2, soft_time_limit=300
- **Key fields** (prescribed in task, no need to read models):
  - ScheduledJobORM: id, agent_id, user_id, team_id, name, message, is_active, delivery_config
  - ConversationORM: team_id, agent_id, user_id, title, status, message_count
  - MessageORM: conversation_id, role, content, token_count
- **Lines of code**: ~100
- **Context reads**: 1 file (workers/utils.py)

#### Task #12: Create cleanup tasks
- **File**: `workers/tasks/cleanup_tasks.py` (CREATE)
- **Implements**: 4 @shared_task functions:
  1. `expire_tokens()` - DELETE refresh_token WHERE expires_at < NOW()
  2. `close_stale_sessions(idle_minutes=30)` - UPDATE conversation status='idle'
  3. `archive_old_conversations(days=90)` - UPDATE conversation status='closed'
  4. `archive_expired_memories()` - UPDATE memory tier='cold', status='archived'
- **Each**: ~20 lines, simple SQL via SQLAlchemy update/delete
- **Lines of code**: ~100 total
- **Context reads**: 1 file (workers/utils.py)

#### Task #16: Create tests for utils.py
- **File**: `tests/test_workers/test_utils.py` (CREATE)
- **Tests**: run_async basic, run_async error propagation, get_task_engine caching, get_task_session_factory caching, get_task_settings returns Settings, engine raises without DATABASE_URL
- **Estimated tests**: ~8
- **Lines of code**: ~70

---

### WAVE 5: Consolidation + Integration

#### Task #9: Consolidation Phase 1 - merge near-duplicates
- **File**: `workers/tasks/memory_tasks.py` (APPEND)
- **Implements**: `consolidate_memories` task shell + `_merge_near_duplicates()` helper
- **Algorithm**: Query active memories → group by (type, agent_id) → pairwise cosine → merge if > 0.92
- **LLM call**: httpx POST to merge content (same pattern as MemoryExtractor)
- **Includes**: `_cosine_similarity()` inline helper, `_call_llm()` helper
- **Lines of code**: ~120
- **Context reads**: 1 file (memory_tasks.py from #8 to understand structure)

#### Task #10: Consolidation Phase 3-4 - decay/expire + cache invalidation
- **File**: `workers/tasks/memory_tasks.py` (APPEND)
- **Implements**: `decay_and_expire_memories` @shared_task
- **Phase 3**: Archive expired (expires_at < NOW()), demote stale warm (30 days), respect protection rules
- **Phase 4**: HotMemoryCache.invalidate(agent_id) for affected agents
- **Protection rules**: NEVER demote identity type, pinned, importance >= 8
- **Lines of code**: ~90
- **Context reads**: 1 file (memory_tasks.py to understand imports)

#### Task #14: Modify chat.py Step 8 for Celery dispatch
- **File**: `src/api/routers/chat.py` (MODIFY 2 locations)
- **Location 1**: Lines 468-502 (in `chat()` function)
- **Location 2**: Lines 828-851 (in `_stream_agent_response()`)
- **Pattern**: `if settings.feature_flags.enable_background_processing: try Celery, except: fallback to asyncio`
- **Key**: Import inside try block, UUIDs as strings, `_extract_memories()` stays unchanged
- **Lines of code**: ~30 changed (15 per location)
- **Context reads**: 1 file (chat.py Step 8 sections only)

#### Task #26: Add delivery + job tracking to agent_tasks
- **File**: `workers/tasks/agent_tasks.py` (APPEND)
- **Implements**: `_deliver_result()` helper (webhook POST) + job metadata updates
- **On success**: last_run_at=now, run_count+=1, consecutive_failures=0
- **On failure**: consecutive_failures+=1, last_error=str(e)[:500]
- **Auto-disable**: is_active=False after 5 consecutive failures
- **Lines of code**: ~60
- **Context reads**: 1 file (agent_tasks.py from #11)

#### Task #18: Tests for agent_tasks.py
- **File**: `tests/test_workers/test_agent_tasks.py` (CREATE)
- **Tests**: job loading, active verification, conversation creation, LLM call, message persistence, success tracking, failure tracking, auto-disable after 5 failures, webhook delivery
- **Estimated tests**: ~9
- **Lines of code**: ~100

#### Task #19: Tests for cleanup_tasks.py
- **File**: `tests/test_workers/test_cleanup_tasks.py` (CREATE)
- **Tests**: expire_tokens deletes expired, close_stale_sessions updates status, archive_old_conversations archives, archive_expired_memories sets tier/status, each returns count dict
- **Estimated tests**: ~9
- **Lines of code**: ~90

---

### WAVE 6: Schedules + More Tests

#### Task #25: Consolidation Phase 2 - summarize old episodic
- **File**: `workers/tasks/memory_tasks.py` (APPEND)
- **Implements**: `_summarize_old_episodic()` helper + wire into `_async_consolidate()`
- **Algorithm**: Query episodic > 7 days + access_count < 3 → greedy cluster by cosine > 0.8 → LLM summarize clusters > 2
- **New memory**: source_type='consolidation', importance=max(cluster), originals superseded
- **Lines of code**: ~80
- **Context reads**: 1 file (memory_tasks.py from #9 to understand consolidate shell)

#### Task #13: Static Celery Beat schedule
- **File**: `workers/schedules.py` (CREATE)
- **Implements**: BEAT_SCHEDULE dict (6 entries) + `configure_beat_schedule(app)`
- **Entries**: expire_tokens (hourly), stale_sessions (15min), archive_conversations (daily 3AM), archive_memories (daily 4AM), consolidate (daily 2AM), decay (daily 5AM)
- **Lines of code**: ~40

#### Task #17: Tests for extract_memories only
- **File**: `tests/test_workers/test_memory_tasks.py` (CREATE)
- **Tests**: calls extractor, returns counts, converts UUIDs, commits session, propagates errors, creates fresh services, handles empty messages
- **Estimated tests**: 7
- **Lines of code**: ~80

#### Task #29: Tests for decay_and_expire (Phase 3-4)
- **File**: `tests/test_workers/test_memory_tasks.py` (APPEND)
- **Tests**: archives expired, demotes stale warm, never demotes identity/pinned/high-importance, invalidates cache, handles Redis down, returns counts
- **Estimated tests**: 8
- **Lines of code**: ~80

#### Task #21: Tests for chat.py Celery integration
- **File**: `tests/test_workers/test_chat_integration.py` (CREATE)
- **Tests**: dispatches via Celery when flag enabled, falls back to asyncio when flag disabled, falls back to asyncio when Celery unavailable, passes correct string UUIDs, _extract_memories helper unchanged
- **Estimated tests**: ~6
- **Lines of code**: ~70

---

### WAVE 7: Consolidation Tests + Dynamic Schedules

#### Task #28: Tests for consolidation (Phase 1+2)
- **File**: `tests/test_workers/test_memory_tasks.py` (APPEND)
- **Tests**: merge finds near-duplicates, keeps higher importance, marks superseded, LLM merges content, re-embeds, summarize finds old episodic, clusters by similarity, skips small clusters, creates consolidation source, returns counts
- **Estimated tests**: 10
- **Lines of code**: ~100

#### Task #27: Dynamic schedule loader from DB
- **File**: `workers/schedules.py` (APPEND)
- **Implements**: `load_dynamic_schedules()`, `_parse_cron_to_schedule()`, update `configure_beat_schedule()` to merge dynamic
- **Handles**: Invalid cron expressions (skip + warn), DB unavailable (use static only)
- **Lines of code**: ~60
- **Context reads**: 1 file (schedules.py from #13)

#### Task #20: Tests for schedules.py
- **File**: `tests/test_workers/test_schedules.py` (CREATE)
- **Tests**: BEAT_SCHEDULE has 6 entries, configure_beat_schedule applies to app, dynamic loader queries active jobs, cron parsing valid/invalid, merged schedule has both static+dynamic, handles DB failure gracefully
- **Estimated tests**: ~7
- **Lines of code**: ~70

---

### WAVE 9: Final Verification

#### Task #24: Full regression test suite
- **Verify**: `.venv/bin/python -m pytest tests/ -v` → 833+ existing tests pass + ~68 new = 901+ total
- **Verify**: `python -m src.cli` still starts
- **Verify**: `ruff check src/ workers/ tests/`
- **Verify**: `ruff format --check src/ workers/ tests/`
- **Blocked by**: ALL other tasks

---

## Integration Points Summary

| Existing Module | Phase 6 Touchpoint | Task |
|-----------------|-------------------|------|
| `src/settings.py` FeatureFlags | Add `enable_background_processing` | #2 |
| `src/api/routers/chat.py` Step 8 | Celery dispatch with asyncio fallback | #14 |
| `src/memory/storage.py` MemoryExtractor | Called by `extract_memories` task | #8 |
| `src/memory/embedding.py` EmbeddingService | Re-embedding in consolidation | #9, #25 |
| `src/memory/tier_manager.py` TierManager | Demotion rules in decay | #10 |
| `src/memory/memory_log.py` MemoryAuditLog | Audit trail for all changes | #9, #10, #25 |
| `src/cache/hot_cache.py` HotMemoryCache | Cache invalidation in Phase 4 | #10 |
| `src/cache/client.py` RedisManager | Broker URL reuse, availability check | #5, #10 |
| `src/db/models/memory.py` MemoryORM | Queried/updated by consolidation + cleanup | #9, #10, #12, #25 |
| `src/db/models/conversation.py` ConversationORM | Stale session + archive cleanup | #12 |
| `src/db/models/auth.py` RefreshTokenORM | Token expiration cleanup | #12 |
| `src/db/models/agent.py` AgentORM | Agent loading in scheduled runs | #11 |
| `src/db/repositories/memory_repo.py` | Similarity search in consolidation | #9, #25 |
| `pyproject.toml` | Add celery[redis] dep | #1 |

---

## Estimated Test Counts

| Test File | Task | Tests | Lines |
|-----------|------|-------|-------|
| `test_utils.py` | #16 | 8 | ~70 |
| `test_memory_tasks.py` (extract) | #17 | 7 | ~80 |
| `test_memory_tasks.py` (consolidation) | #28 | 10 | ~100 |
| `test_memory_tasks.py` (decay) | #29 | 8 | ~80 |
| `test_agent_tasks.py` | #18 | 9 | ~100 |
| `test_cleanup_tasks.py` | #19 | 9 | ~90 |
| `test_schedules.py` | #20 | 7 | ~70 |
| `test_chat_integration.py` | #21 | 6 | ~70 |
| `test_scheduled_job_model.py` | #22 | 8 | ~80 |
| **Total** | | **~72** | **~740** |

**Target**: 833 existing + 72 new = **905+ total tests**

---

## Context Window Safety Analysis

Each task was evaluated for builder agent context consumption:

| Task | Reads | Writes | Total Est. | Status |
|------|-------|--------|-----------|--------|
| #1 | pyproject.toml (68 lines) | 2 lines | ~100 tokens | SAFE |
| #2 | settings.py (145 lines) | 3 lines | ~200 tokens | SAFE |
| #3 | agent.py pattern (60 lines) | 60 lines | ~400 tokens | SAFE |
| #4 | migration pattern (80 lines) | 80 lines | ~500 tokens | SAFE |
| #5 | settings.py (50 lines) | 45 lines | ~300 tokens | SAFE |
| #6 | None | 1 line | ~20 tokens | SAFE |
| #7 | engine.py pattern (40 lines) | 55 lines | ~300 tokens | SAFE |
| #8 | utils.py (55 lines) | 90 lines | ~500 tokens | SAFE |
| #9 | memory_tasks.py (90 lines) | 120 lines | ~700 tokens | SAFE |
| #10 | memory_tasks.py (100 lines) | 90 lines | ~600 tokens | SAFE |
| #11 | utils.py (55 lines) | 100 lines | ~500 tokens | SAFE |
| #12 | utils.py (55 lines) | 100 lines | ~500 tokens | SAFE |
| #13 | None | 40 lines | ~200 tokens | SAFE |
| #14 | chat.py Step 8 (40 lines x2) | 30 lines | ~400 tokens | SAFE |
| #15 | conftest pattern (50 lines) | 50 lines | ~300 tokens | SAFE |
| #16-#29 | ~80 lines each | ~80 lines each | ~500 tokens | SAFE |

**Max context per task**: ~700 tokens (Task #9). Well within safe limits.

---

## Patterns to Follow (from LEARNINGS.md)

Builders MUST follow these established codebase patterns:

```python
# Absolute imports
from src.module import Class

# Structured logging
logger.info("action_name: key=%s, value=%s", key, value)

# Error returns from tools (never raise)
return f"Error: {description}"

# Google-style docstrings
def func(arg: str) -> str:
    """Brief description.

    Args:
        arg: Description.

    Returns:
        Description.
    """

# ORM naming convention
class ScheduledJobORM(Base, UUIDMixin, TimestampMixin):

# SA metadata workaround
metadata_json = mapped_column("metadata", JSONB, ...)

# Feature flags
if settings.feature_flags.enable_background_processing:

# Graceful degradation
if not redis_manager.available:
    return None  # NEVER raise
```

---

## Rollback Strategy

1. Stop Celery: `celery -A workers.celery_app control shutdown`
2. Revert chat.py (or leave - `.delay()` fails silently)
3. `alembic downgrade` to Phase 4 revision
4. Delete `workers/` directory
5. Remove `celery[redis]` from pyproject.toml
6. Redis keys auto-expire (TTL-based)
7. Verify: API starts, CLI works, 833 tests pass

---

## Success Criteria

### Per-Task (each builder must verify)
- [ ] Code follows established patterns (imports, logging, docstrings)
- [ ] No raw SQL (use SQLAlchemy ORM/core)
- [ ] UUIDs serialized as strings for Celery, converted inside tasks
- [ ] Feature-flagged where applicable
- [ ] Structured logging on all operations
- [ ] Google-style docstrings on all public functions

### Per-Wave (coordinator verifies)
- [ ] All tasks in wave complete without errors
- [ ] Existing 833 tests still pass after wave
- [ ] New tests pass in isolation
- [ ] No circular imports introduced
- [ ] ruff check passes on new/modified files

### Final Acceptance (Wave 9)
- [ ] `.venv/bin/python -m pytest tests/ -v` → 900+ tests pass
- [ ] `python -m src.cli` starts without error
- [ ] `ruff check src/ workers/ tests/` clean
- [ ] `ruff format --check src/ workers/ tests/` clean
- [ ] Memory extraction dispatches via Celery when flag enabled
- [ ] Memory extraction falls back to asyncio when Celery unavailable
- [ ] Consolidation merges near-duplicates (cosine > 0.92)
- [ ] Consolidation summarizes old episodic (> 7 days, access < 3)
- [ ] Decay respects protection rules (identity, pinned, importance >= 8)
- [ ] Cache invalidation after consolidation changes
- [ ] Cleanup tasks handle token/session/conversation/memory lifecycle
- [ ] Scheduled agent runs execute with retry and tracking
- [ ] Beat schedule has 6 static + dynamic entries from DB
- [ ] All tasks retry on transient failures (max retries respected)
- [ ] All tasks return JSON-serializable result dicts

---

## Final Checklist

- [x] Every new file has a corresponding test task
- [x] Every modification to existing files has its own task
- [x] No single task requires reading > 3 files or writing > 150 lines
- [x] Consolidation broken into 3 tasks (Phase 1, Phase 2, Phase 3-4)
- [x] Celery async bridge is its own task (#7)
- [x] Dynamic schedule loading is its own task (#27)
- [x] Feature flag integration is its own task (#2)
- [x] DB migration is its own task (#4)
- [x] pyproject.toml change is its own task (#1)
- [x] Full regression test task exists (#24)
- [x] All 29 tasks have acceptance criteria
- [x] All tasks have dependency chains
- [x] Memory task tests split 3 ways (extract, consolidation, decay)
- [x] Agent task split into core (#11) + delivery/tracking (#26)
- [x] Schedule split into static (#13) + dynamic (#27)
- [x] No task exceeds ~700 tokens context budget
- [x] File ownership map prevents conflicts between parallel tasks
