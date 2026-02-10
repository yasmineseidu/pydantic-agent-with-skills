# Phase 6: Background Processing

> **Timeline**: Week 4 | **Prerequisites**: Phase 4 (Auth + API), Phase 2 (Memory) | **Status**: Not Started

## Goal

Add Celery workers with Redis broker for background memory extraction after conversations, periodic memory consolidation (merge duplicates, summarize old episodic memories, manage tier demotions), scheduled agent runs, and cleanup tasks. This phase makes the memory system self-maintaining and enables asynchronous agent execution.

## Dependencies (Install)

```toml
[project]
dependencies = [
    # ... existing from Phases 1-4 ...
    "celery[redis]~=5.4.0",
]
```

## Settings Extensions

```python
# No new settings fields required.
# Celery uses the existing redis_url (Phase 3) as its broker.
# Celery configuration is defined in workers/celery_app.py directly.
#
# The redis_url field from Phase 3 settings is reused:
#   redis_url: Optional[str] = Field(default=None, description="Redis connection URL")
#
# Celery-specific config lives in workers/celery_app.py:
#   broker_url = settings.redis_url
#   result_backend = settings.redis_url
```

## New Directories & Files

```
workers/
    __init__.py
    celery_app.py             # Celery config (Redis broker, JSON serializer)
    schedules.py              # Celery Beat schedule
    tasks/
        __init__.py
        memory_tasks.py       # extract_memories, consolidate_memories
        agent_tasks.py        # scheduled_agent_run
        cleanup_tasks.py      # expire_tokens, stale_sessions, old_conversations
```

## Database Tables Introduced

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `scheduled_job` | id (UUID), team_id (FK), agent_id (FK), user_id (FK), name, message (TEXT -- the prompt to run), cron_expression, timezone (default 'UTC'), is_active, last_run_at, next_run_at, run_count, consecutive_failures, last_error, delivery_config (JSONB -- {webhook_url, email, slack_channel, telegram_chat_id}), created_at, updated_at | User-configured scheduled agent runs. Example: "Summarize my emails daily at 9am". Cron expression format for flexible scheduling. Delivery config supports multiple output channels. |

Reference: `plan/sql/schema.sql` (Phase 6 section, table 14)

### Full SQL for Phase 6 Tables

```sql
-- 14. scheduled_job
-- User-configured scheduled agent runs ("Summarize my emails daily at 9am").
CREATE TABLE scheduled_job (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    user_id             UUID NOT NULL REFERENCES "user"(id),
    name                TEXT NOT NULL,       -- "Daily email summary"
    message             TEXT NOT NULL,       -- The prompt to run
    cron_expression     TEXT NOT NULL,       -- "0 9 * * *"
    timezone            TEXT NOT NULL DEFAULT 'UTC',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    -- Execution tracking
    last_run_at         TIMESTAMPTZ,
    next_run_at         TIMESTAMPTZ,
    run_count           INT NOT NULL DEFAULT 0,
    consecutive_failures INT NOT NULL DEFAULT 0,
    last_error          TEXT,
    -- Delivery
    delivery_config     JSONB NOT NULL DEFAULT '{}',
    -- {webhook_url, email, slack_channel, telegram_chat_id}
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at trigger
CREATE TRIGGER set_updated_at_scheduled_job
    BEFORE UPDATE ON scheduled_job
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Indexes
CREATE INDEX idx_job_next_run ON scheduled_job (next_run_at)
    WHERE is_active = TRUE;
-- Query: "find jobs due to run (Celery Beat polling)"

CREATE INDEX idx_job_team ON scheduled_job (team_id);
-- Query: "list scheduled jobs for team"
```

## Implementation Details

### Celery Application (`workers/celery_app.py`)

```python
# Celery config:
# - Broker: Redis (from settings.redis_url)
# - Result backend: Redis
# - Serializer: JSON (not pickle -- security)
# - Task acknowledgment: late ack (prevents lost tasks on worker crash)
# - Retry policy: max 3 retries with exponential backoff
#
# from celery import Celery
#
# celery_app = Celery("skill_agent")
# celery_app.config_from_object({
#     "broker_url": settings.redis_url,
#     "result_backend": settings.redis_url,
#     "task_serializer": "json",
#     "accept_content": ["json"],
#     "result_serializer": "json",
#     "task_acks_late": True,
#     "task_reject_on_worker_lost": True,
#     "worker_prefetch_multiplier": 1,
# })
```

### Memory Tasks (`workers/tasks/memory_tasks.py`)

#### Extract Memories (Post-Conversation)

This task is triggered after a conversation ends (or every N messages per `summarize_interval`). It runs the double-pass extraction pipeline from Phase 2's `MemoryExtractor`.

```python
@celery_app.task(name="memory.extract", bind=True, max_retries=3)
def extract_memories(
    self,
    conversation_id: str,
    team_id: str,
    agent_id: str,
    user_id: str,
) -> dict:
    """
    Extract memories from a conversation asynchronously.

    Delegates to MemoryExtractor.extract_from_conversation() (Phase 2).

    Returns: {
        memories_created: int,
        memories_versioned: int,
        duplicates_skipped: int,
        contradictions_found: int,
        duration_ms: int,
    }
    """
```

#### Consolidate Memories (Celery Beat, every 6 hours)

```python
@celery_app.task(name="memory.consolidate")
def consolidate_memories(team_id: str) -> dict:
    """
    Periodic memory maintenance.

    Phase 1: Merge near-duplicates
        - Find pairs with cosine > 0.92, same type + agent
        - Keep higher importance, merge content, re-embed

    Phase 2: Summarize old episodic
        - Episodic memories > 30 days, importance < 5
        - LLM summarizes cluster into single memory
        - Mark originals superseded_by summary

    Phase 3: Decay and expire
        - Boost memories with access_count > 10
        - Set expires_at for: importance < 3, last_accessed > 90 days, not pinned

    Phase 4: Cache invalidation
        - Delete hot cache keys for affected agents

    Returns: {merged: N, summarized: N, expired: N, duration_ms: N}
    """
```

Consolidation details for each phase:

**Phase 1 -- Merge near-duplicates:**
- Query all active memories for the team grouped by (memory_type, agent_id)
- For each group, compute pairwise cosine similarity
- Pairs with cosine > 0.92: keep the one with higher importance
- Merge content (LLM generates combined version), re-embed the merged memory
- Mark the duplicate as `status='superseded'`, `superseded_by=merged.id`
- Log to `memory_log`: action='consolidated'

**Phase 2 -- Summarize old episodic:**
- Find episodic memories > 30 days old with importance < 5
- Cluster by subject/topic (cosine > 0.8)
- For each cluster: LLM summarizes into a single episodic memory
- New summary memory gets `importance = max(cluster importances)`
- Originals: `status='superseded'`, `superseded_by=summary.id`, `tier='cold'`
- Log to `memory_log`: action='consolidated'

**Phase 3 -- Decay and expire:**
- Memories with `access_count > 10` in past 7 days: boost importance by +1 (cap at 10)
- Memories with `importance < 3 AND access_count < 2 AND last_accessed_at > 90 days AND NOT is_pinned`: set `expires_at = NOW() + 30 days`
- Never expire: identity memories, pinned memories, importance >= 8

**Phase 4 -- Cache invalidation:**
- For each agent affected by consolidation changes: delete Redis hot cache keys
- Pattern: `ska:hot:{agent_id}:*`
- Agents will rebuild their hot cache on next retrieval

### Agent Tasks (`workers/tasks/agent_tasks.py`)

#### Scheduled Agent Run

```python
@celery_app.task(name="agent.scheduled_run")
def scheduled_agent_run(
    agent_id: str, message: str, user_id: str
) -> dict:
    """
    Run an agent on a schedule (e.g., "Summarize my emails daily at 9am").

    Creates a conversation, runs the agent, persists results.
    Optionally delivers result via webhook/integration.

    Flow:
    1. Load AgentDNA from DB by agent_id
    2. Create a new conversation
    3. Build agent with full memory context
    4. Run agent with the scheduled message
    5. Persist conversation + messages
    6. Deliver result via delivery_config (webhook_url, email, etc.)
    7. Update scheduled_job: last_run_at, next_run_at, run_count
    8. On failure: increment consecutive_failures, set last_error

    Returns: {
        conversation_id: str,
        response_preview: str (first 200 chars),
        tokens_used: int,
        duration_ms: int,
        delivered_to: list[str],
    }
    """
```

### Cleanup Tasks (`workers/tasks/cleanup_tasks.py`)

```python
@celery_app.task(name="cleanup.expire_stale")
def expire_stale_data() -> dict:
    """
    Daily cleanup job (runs at midnight UTC).

    1. Expire refresh tokens: DELETE WHERE expires_at < NOW()
    2. Close stale sessions: UPDATE conversation SET status='idle'
       WHERE status='active' AND last_message_at < NOW() - INTERVAL '30 min'
    3. Trigger memory extraction for newly-idle conversations
    4. Archive old conversations: soft-delete conversations older than
       team.conversation_retention_days (default 90)
    5. Clean expired memories: UPDATE memory SET tier='cold', status='archived'
       WHERE expires_at < NOW() AND status='active'

    Returns: {
        tokens_expired: int,
        sessions_closed: int,
        conversations_archived: int,
        memories_archived: int,
        duration_ms: int,
    }
    """
```

### Beat Schedule (`workers/schedules.py`)

```python
from celery.schedules import crontab

beat_schedule = {
    "memory-consolidation": {
        "task": "memory.consolidate",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        # Note: this dispatches one task per team. The task itself
        # queries for all active teams and processes each.
    },
    "cleanup-expired": {
        "task": "cleanup.expire_stale",
        "schedule": crontab(minute=0, hour=0),  # Daily midnight UTC
    },
}
# + Dynamic schedules from scheduled_job table
# The Celery Beat process checks the scheduled_job table for
# user-configured jobs and dispatches them at their cron times.
```

### Dynamic Schedule Loading

The `scheduled_job` table enables user-configured schedules that are not hardcoded in `beat_schedule`. These are loaded dynamically:

```python
# On Celery Beat tick (every 60 seconds):
# 1. Query: SELECT * FROM scheduled_job WHERE is_active = TRUE AND next_run_at <= NOW()
# 2. For each due job: dispatch agent.scheduled_run task
# 3. Update next_run_at based on cron_expression
```

### Task Retry Policy

All tasks follow a consistent retry policy:

| Operation | Max Retries | Retry Delay | On Final Failure |
|-----------|-------------|-------------|------------------|
| memory.extract | 3 | Exponential (30s, 120s, 480s) | Log error, mark conversation extraction_failed |
| memory.consolidate | 2 | Exponential (60s, 300s) | Log error, skip to next team |
| agent.scheduled_run | 3 | Exponential (60s, 300s, 900s) | Increment consecutive_failures, set last_error |
| cleanup.expire_stale | 1 | None | Log error, alert (this should never fail) |

```python
# Retry configuration example:
@celery_app.task(
    name="memory.extract",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=600,     # Max 10 minutes between retries
    retry_jitter=True,         # Add randomness to prevent thundering herd
)
def extract_memories(self, ...):
    try:
        # ... extraction logic ...
    except TransientError as e:
        raise self.retry(exc=e)
```

### Running Celery Workers

```bash
# Start worker (processes tasks)
celery -A workers.celery_app worker -l info

# Start beat (dispatches scheduled tasks)
celery -A workers.celery_app beat -l info

# Both in one process (development only)
celery -A workers.celery_app worker -B -l info

# Monitor with Flower (optional)
celery -A workers.celery_app flower
```

### Integration with Chat Endpoint

The Phase 4 chat endpoint is updated to dispatch memory extraction asynchronously instead of inline:

```python
# In api/routers/chat.py, after agent response:
from workers.tasks.memory_tasks import extract_memories

# Trigger async extraction (non-blocking)
extract_memories.delay(
    conversation_id=str(conversation.id),
    team_id=str(current_user.team_id),
    agent_id=str(agent.id),
    user_id=str(current_user.id),
)
```

This means the chat response is not delayed by memory extraction. The user gets a fast response, and memories are extracted in the background.

### Graceful Degradation

If Celery/Redis is unavailable:
- Memory extraction falls back to inline (synchronous) -- slower but functional
- Scheduled jobs do not run (logged as warning)
- Cleanup tasks do not run (stale data accumulates until Celery is restored)
- The API and CLI continue to function normally

## Tests

```
tests/test_workers/
    conftest.py                # Celery test fixtures (eager mode)
    test_memory_tasks.py       # Extract and consolidate task logic
    test_agent_tasks.py        # Scheduled agent runs
    test_cleanup_tasks.py      # Cleanup and expiration logic
```

### Key Test Scenarios

- Memory extraction task runs successfully after conversation ends
- Memory extraction creates correct memories with provenance (source_conversation_id, source_message_ids)
- Memory extraction handles empty conversations gracefully (no crash, returns zeros)
- Memory extraction retries on transient failure (max 3 retries)
- Memory extraction deduplicates against existing memories (cosine > 0.95)
- Consolidation Phase 1: merges near-duplicate memories (cosine > 0.92)
- Consolidation Phase 1: keeps memory with higher importance when merging
- Consolidation Phase 2: summarizes old episodic memories (> 30 days, importance < 5)
- Consolidation Phase 2: marks originals as superseded_by summary
- Consolidation Phase 3: boosts frequently-accessed memories (access_count > 10)
- Consolidation Phase 3: sets expires_at for low-importance, stale memories
- Consolidation Phase 3: never expires identity, pinned, or high-importance memories
- Consolidation Phase 4: invalidates hot cache for affected agents
- Consolidation returns accurate stats: {merged, summarized, expired, duration_ms}
- Scheduled agent run creates conversation and persists messages
- Scheduled agent run delivers result via delivery_config webhook
- Scheduled agent run updates scheduled_job: last_run_at, next_run_at, run_count
- Scheduled agent run increments consecutive_failures on failure
- Scheduled agent run sets last_error with error message on failure
- Cleanup task expires old refresh tokens
- Cleanup task closes stale sessions (idle > 30 min)
- Cleanup task triggers memory extraction for newly-idle conversations
- Cleanup task archives conversations older than retention period
- Cleanup task archives expired memories (tier='cold', status='archived')
- All tasks retry on transient failures (max retries respected)
- All tasks log results with durations
- Celery Beat schedule dispatches consolidation every 6 hours
- Celery Beat schedule dispatches cleanup daily at midnight UTC
- Dynamic schedules from scheduled_job table are dispatched at correct cron times
- Tasks run in eager mode for testing (no real Redis/Celery required)
- All existing tests pass
- CLI still works

## Acceptance Criteria

- [ ] Memory extraction runs asynchronously after conversation ends (dispatched from chat endpoint)
- [ ] Consolidation merges near-duplicate memories (cosine > 0.92)
- [ ] Consolidation summarizes old episodic memories (> 30 days, importance < 5)
- [ ] Consolidation manages memory decay (expires_at for stale, low-importance memories)
- [ ] Scheduled agent runs execute at configured cron times
- [ ] Scheduled agent runs deliver results via configured delivery method
- [ ] Expired tokens/sessions cleaned up daily
- [ ] All tasks retry on transient failures (max 3 retries)
- [ ] Task results logged with durations and stats
- [ ] Celery Beat runs on schedule (consolidation every 6h, cleanup daily)
- [ ] Dynamic schedules from scheduled_job table work
- [ ] All existing tests pass
- [ ] CLI still works

## Rollback Strategy

**Rollback Method**: Delete `workers/` directory. Stop Celery processes. No existing code is fundamentally changed -- the chat endpoint can fall back to inline (synchronous) memory extraction.

**Database rollback**: Run `alembic downgrade` to remove the `scheduled_job` table. The Phase 1-4 tables remain intact.

**Detailed steps**:
1. Stop Celery worker process: `celery -A workers.celery_app control shutdown`
2. Stop Celery Beat process
3. Revert the chat endpoint in `api/routers/chat.py` to remove async extraction dispatch (or leave it -- the `.delay()` call will simply fail silently if Celery is down)
4. `alembic downgrade` to the Phase 4 migration revision (drops scheduled_job table)
5. Delete `workers/` directory
6. Remove `"celery[redis]~=5.4.0"` from `pyproject.toml`
7. All Redis keys used by Celery are TTL-based and will auto-expire
8. Verify: `uvicorn api.app:create_app --factory` starts and chat works
9. Verify: `python -m src.cli` still works
10. Verify: `.venv/bin/python -m pytest tests/ -v` passes

## Links to Main Plan

- Section 4, Phase 6 (Background Processing) -- primary spec
- Section 6.1-6.6 (Worker structure, consolidation, scheduled runs, beat schedule, tests)
- Section 3B (Bulletproof Memory Architecture) -- memory extraction pipeline, tier management, consolidation rules
- Section 15 (Conversation Lifecycle) -- conversation idle/close triggers extraction
- Section 17 (Data Lifecycle & Retention) -- retention policies enforced by cleanup tasks
- Section 23 (Rollback Strategy) -- Phase 6 rollback method
- ADR-2 (Celery + Redis over ARQ/Dramatiq/TaskIQ) -- task queue choice rationale, escape hatch to TaskIQ
