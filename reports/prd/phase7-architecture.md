# Phase 7: Agent Collaboration - Architecture Document

> Generated: 2026-02-10 | Mode: EXISTING | Prerequisites: Phase 2, 4, 6

## 1. Architecture Overview

Phase 7 introduces two complementary subsystems that sit on top of existing infrastructure:

```
                        USER REQUEST
                             |
                    [Feature Flag Check]
                        /    |    \
                       /     |     \
                 OFF  /  SIMPLE  \  EXPERT
                     /     |      \
            Direct   AgentRouter  ExpertGate
            Dispatch    (7.1.1)    (7.1.2)
                \        |         /
                 \       |        /
                  [Selected Agent(s)]
                         |
                  +----- | -----+
                  |      |      |
                TOP_1  TOP_K  ENSEMBLE
                  |      |      |
                  v      v      v
               Single  Pick   Aggregate
               Agent   Best   Responses
                  \      |      /
                   \     |     /
                    [Final Response]
                         |
                [Routing Decision Log]
```

```
COLLABORATION STACK (independent of routing):

    Agent A (lead)
        |
    [Collaboration Orchestrator]
        |
    +---+---+---+---+---+
    |   |   |   |   |   |
    SW  PIP PR  BR  CON DEL    (6 patterns)
    |   |   |   |   |   |
    [TaskDelegator]  [AgentMessageBus]
        |                |
    [Celery Worker]  [Redis Pub/Sub]
        |                |
    [DB: agent_task] [DB: agent_message]
```

## 2. Component Architecture

### 2.1 New Package: src/collaboration/

```
src/collaboration/
    __init__.py              # Package exports
    models.py                # ALL Pydantic models + Enums (foundation, no deps)
    router.py                # AgentRouter (baseline skill-matching)
    discovery.py             # AgentDirectory (find experts by skill)
    handoff.py               # HandoffManager (agent-to-agent transfers)
    multi_agent.py           # Multi-agent conversation management
    team_memory_bus.py       # Shared memory propagation
    message_bus.py           # AgentMessageBus (Redis pub/sub + DB)
    task_delegator.py        # TaskDelegator (Celery dispatch, safety)
    report_manager.py        # ReportManager (structured reports)
    orchestrator.py          # CollaborationOrchestrator (5 patterns)
```

### 2.2 Expanded Package: src/moe/ (Phase 7 additions)

```
src/moe/
    # Phase 2 (existing, unchanged):
    __init__.py              # MODIFIED: add Phase 7 exports
    model_tier.py            # ComplexityScore, ModelTier, BudgetCheck
    complexity_scorer.py     # QueryComplexityScorer
    model_router.py          # ModelRouter
    cost_guard.py            # CostGuard

    # Phase 7 (new):
    models.py                # ExpertScore, SelectionStrategy, SelectionResult, ExpertResponse, AggregatedResponse
    expert_gate.py           # ExpertGate (4-signal scoring)
    expert_selector.py       # ExpertSelector (TOP_1, TOP_K, ENSEMBLE, CASCADE)
    response_aggregator.py   # ResponseAggregator (ENSEMBLE synthesis)
```

### 2.3 New ORM Models: src/db/models/collaboration.py

Single file containing 7 ORM models:

| ORM Model | Table | Key Relationships |
|---|---|---|
| `ConversationParticipantORM` | conversation_participant | FK conversation, FK agent |
| `AgentHandoffORM` | agent_handoff | FK conversation, FK agent (from/to) |
| `RoutingDecisionLogORM` | routing_decision_log | FK team, FK conversation, FK message |
| `AgentTaskORM` | agent_task | FK team, FK agent (creator/assignee), self-ref parent_task_id |
| `AgentMessageORM` | agent_message | FK team, FK agent (from/to) |
| `CollaborationSessionORM` | collaboration_session | FK team, FK agent (lead), FK conversation |
| `CollaborationParticipantV2ORM` | collaboration_participant_v2 | FK session, FK agent, FK agent_task |

All use `Base, UUIDMixin, TimestampMixin` from `src/db/base.py`.

### 2.4 New Migration: 004_phase7_collaboration.py

- Revision: "004", down_revision: "003"
- Creates 1 new ENUM type: `participant_role` ('primary', 'invited', 'handoff_source')
- Creates 7 tables (see Section 5)
- Creates ~20 indexes (mix of btree and GIN)
- Reuses `trigger_set_updated_at()` from migration 001
- Does NOT alter message table (agent_id already exists)

### 2.5 New API Router: src/api/routers/collaboration.py

Endpoints:
- `POST /v1/conversations/{id}/handoff` - Initiate agent handoff
- `POST /v1/conversations/{id}/agents` - Add/remove agents from multi-agent conversation
- `GET /v1/agents/recommend` - Agent discovery/recommendation
- `POST /v1/tasks/delegate` - Create delegated task
- `GET /v1/tasks/{id}` - Check task status
- `POST /v1/tasks/{id}/cancel` - Cancel task
- `POST /v1/collaborations` - Start collaboration session
- `GET /v1/collaborations/{id}` - Get collaboration status
- `GET /v1/agents/{slug}/inbox` - Get agent message inbox
- `POST /v1/agents/{slug}/messages` - Send message to agent

### 2.6 New Celery Task: workers/tasks/collaboration.py

- `execute_agent_task(task_id: str)` - Execute a delegated agent task
- Uses `asyncio.run()` bridge (Phase 6 pattern)
- Creates fresh DB session (pool_size=3)
- Respects max_tokens, max_tool_calls, timeout_seconds constraints
- Updates agent_task status (pending -> in_progress -> completed/failed)
- Publishes result via Redis pub/sub

## 3. Data Flow Diagrams

### 3.1 Routing Flow (Feature Flag Cascade)

```
User Message
     |
     v
[settings.feature_flags.enable_agent_collaboration?]
     |
     +-- False --> Direct dispatch to agent_slug from URL
     |
     +-- True --> [settings.feature_flags.enable_expert_gate?]
                       |
                       +-- False --> AgentRouter.route()
                       |               |
                       |               +-- @mention detected? --> Route to mentioned agent
                       |               +-- Current agent has skills? --> Keep current agent
                       |               +-- Score all agents by skill --> Pick best
                       |               +-- No match --> Default agent
                       |
                       +-- True --> ExpertGate.score_experts()
                                       |
                                       v
                                  [4-signal scoring]
                                       |
                                       v
                                  ExpertSelector.select(strategy)
                                       |
                                       +-- TOP_1 --> Single agent
                                       +-- CASCADE --> Ordered list, try until success
                                       +-- TOP_K --> [enable_ensemble_mode?]
                                       +-- ENSEMBLE --> [enable_ensemble_mode?]
                                              |
                                              +-- False --> Downgrade to TOP_1
                                              +-- True --> Parallel execution + ResponseAggregator
                                       |
                                       v
                                  [Log to routing_decision_log]
```

### 3.2 Task Delegation Flow

```
Agent A: delegate_task(to="luke", ...)
     |
     v
TaskDelegator.delegate()
     |
     +-- Validate depth < 3 (check parent chain)
     +-- Detect cycles (A->B->A)
     +-- Check agent availability (concurrent tasks < 5)
     +-- Check budget (cost_guard)
     |
     v
CREATE agent_task (status=pending)
     |
     v
Celery: execute_agent_task.delay(task_id_str)
     |
     v
[Worker picks up task]
     |
     +-- Create fresh DB session
     +-- Load agent context (identity, skills, memories)
     +-- Create Pydantic AI agent with constraints
     +-- Execute with timeout
     +-- Record tokens_used, cost_usd
     |
     v
UPDATE agent_task (status=completed, result=...)
     |
     v
Redis PUBLISH task:{task_id} "completed"
     |
     v
Agent A receives result (via get_result poll or pub/sub)
```

### 3.3 Collaboration Session Flow (Supervisor-Worker)

```
Agent A: start_collaboration(pattern=SUPERVISOR_WORKER, ...)
     |
     v
CollaborationOrchestrator.start()
     |
     +-- Validate all participants exist & active
     +-- Create collaboration_session (status=planning)
     +-- Create collaboration_participant_v2 records
     |
     v
[Transition to ACTIVE]
     |
     +-- For each worker participant:
     |       TaskDelegator.delegate(instructions, from=lead, to=worker)
     |       (parallel Celery dispatch)
     |
     v
[Wait for all tasks to complete]
     |
     +-- Each worker result arrives via Redis pub/sub
     +-- Update collaboration_participant_v2 status
     +-- Track cumulative cost
     |
     v
[Check cost cap: total_cost_usd < max_total_cost_usd?]
     |
     +-- Exceeded --> Abort remaining, status=FAILED
     +-- OK --> Continue
     |
     v
[All workers complete --> Transition to SYNTHESIZING]
     |
     v
CollaborationOrchestrator.synthesize()
     |
     +-- Lead agent receives all stage_outputs
     +-- Lead generates final_output (meta-synthesis)
     |
     v
UPDATE collaboration_session (status=completed, final_output=...)
```

## 4. Integration Points

### 4.1 src/settings.py (MODIFY)

Add to `FeatureFlags` class (after line 28):
```python
enable_expert_gate: bool = Field(default=False, description="Phase 7: MoE 4-signal scoring")
enable_ensemble_mode: bool = Field(default=False, description="Phase 7: Multi-expert responses")
enable_task_delegation: bool = Field(default=False, description="Phase 7: AgentTask system")
enable_collaboration: bool = Field(default=False, description="Phase 7: Full collaboration sessions")
```

### 4.2 src/dependencies.py (MODIFY)

Add TYPE_CHECKING imports:
```python
if TYPE_CHECKING:
    # ... existing ...
    # Phase 7: Collaboration imports
    from src.collaboration.router import AgentRouter
    from src.collaboration.handoff import HandoffManager
    from src.collaboration.discovery import AgentDirectory
    from src.collaboration.task_delegator import TaskDelegator
    from src.collaboration.message_bus import AgentMessageBus
    from src.collaboration.orchestrator import CollaborationOrchestrator
    from src.moe.expert_gate import ExpertGate
    from src.moe.expert_selector import ExpertSelector
```

Add fields to `AgentDependencies`:
```python
# Collaboration system (Phase 7 - initialized externally)
agent_router: Optional["AgentRouter"] = None
expert_gate: Optional["ExpertGate"] = None
expert_selector: Optional["ExpertSelector"] = None
handoff_manager: Optional["HandoffManager"] = None
agent_directory: Optional["AgentDirectory"] = None
task_delegator: Optional["TaskDelegator"] = None
message_bus: Optional["AgentMessageBus"] = None
collaboration_orchestrator: Optional["CollaborationOrchestrator"] = None
```

### 4.3 src/api/routers/chat.py (MODIFY)

Inject routing logic at the beginning of the chat endpoint (before current Step 1: resolve agent):

```python
# Phase 7: Agent routing (if enabled)
if settings.feature_flags.enable_agent_collaboration:
    routing_decision = await _route_to_agent(
        message=request.message,
        team_id=current_user.team_id,
        user_id=current_user.id,
        current_agent_slug=agent_slug,
        agent_deps=agent_deps,
        settings=settings,
        db=db,
    )
    agent_slug = routing_decision.agent_slug
    # Log routing decision
    ...
```

### 4.4 src/api/app.py (MODIFY)

Add router import and registration:
```python
from src.api.routers import (
    # ... existing ...
    collaboration_router,
)
# In create_app():
app.include_router(collaboration_router)
```

### 4.5 src/moe/__init__.py (MODIFY)

Add Phase 7 exports:
```python
"""Mixture-of-Experts routing: model tier (Phase 2) + agent expert (Phase 7)."""

# Phase 7 exports will be added after implementation
```

### 4.6 src/db/models/__init__.py (MODIFY)

Add Phase 7 ORM model imports and __all__ entries.

### 4.7 src/api/routers/__init__.py (MODIFY)

Add collaboration_router import and __all__ entry.

## 5. Database Schema

### 5.1 New ENUM Type

```sql
CREATE TYPE participant_role AS ENUM ('primary', 'invited', 'handoff_source');
```

### 5.2 Table: conversation_participant

```
conversation_participant
    id                  UUID PK DEFAULT gen_random_uuid()
    conversation_id     UUID NOT NULL FK conversation(id) CASCADE
    agent_id            UUID NOT NULL FK agent(id)
    role                participant_role NOT NULL DEFAULT 'primary'
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
    left_at             TIMESTAMPTZ NULL
    UNIQUE (conversation_id, agent_id)
```

### 5.3 Table: agent_handoff

```
agent_handoff
    id                  UUID PK DEFAULT gen_random_uuid()
    conversation_id     UUID NOT NULL FK conversation(id) CASCADE
    from_agent_id       UUID NOT NULL FK agent(id)
    to_agent_id         UUID NOT NULL FK agent(id)
    reason              TEXT NOT NULL
    context_summary     TEXT NULL
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 5.4 Table: routing_decision_log

```
routing_decision_log
    id                      UUID PK DEFAULT gen_random_uuid()
    team_id                 UUID NOT NULL FK team(id)
    conversation_id         UUID FK conversation(id)
    message_id              UUID FK message(id)
    strategy                TEXT NOT NULL
    scores                  JSONB NOT NULL
    selected_agents         TEXT[] NOT NULL
    confidence_threshold    FLOAT NOT NULL DEFAULT 0.6
    fallback_used           BOOLEAN NOT NULL DEFAULT FALSE
    complexity_score        FLOAT NULL
    complexity_dimensions   JSONB NULL
    selected_tier           TEXT NULL
    selected_model          TEXT NULL
    tier_override_reason    TEXT NULL
    estimated_cost          FLOAT NULL
    actual_cost             FLOAT NULL
    gate_latency_ms         FLOAT NULL
    router_latency_ms       FLOAT NULL
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 5.5 Table: agent_task

```
agent_task
    id                      UUID PK DEFAULT gen_random_uuid()
    team_id                 UUID NOT NULL FK team(id) CASCADE
    conversation_id         UUID FK conversation(id)
    created_by_agent_id     UUID NOT NULL FK agent(id)
    assigned_to_agent_id    UUID NOT NULL FK agent(id)
    parent_task_id          UUID FK agent_task(id)
    task_type               TEXT NOT NULL
    title                   TEXT NOT NULL
    instructions            TEXT NOT NULL
    context                 TEXT NULL
    expected_output         TEXT NULL
    input_artifacts         JSONB NOT NULL DEFAULT '[]'
    priority                TEXT NOT NULL DEFAULT 'normal'
    max_tokens              INT NOT NULL DEFAULT 4000
    max_tool_calls          INT NOT NULL DEFAULT 10
    timeout_seconds         INT NOT NULL DEFAULT 120
    model_tier              TEXT NULL
    delegation_depth        INT NOT NULL DEFAULT 0
    status                  TEXT NOT NULL DEFAULT 'pending'
    result                  TEXT NULL
    result_artifacts        JSONB NOT NULL DEFAULT '[]'
    error                   TEXT NULL
    tokens_used             INT NOT NULL DEFAULT 0
    cost_usd                DECIMAL(10,6) NOT NULL DEFAULT 0
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    started_at              TIMESTAMPTZ NULL
    completed_at            TIMESTAMPTZ NULL
    CHECK (delegation_depth <= 3)
    CHECK (created_by_agent_id != assigned_to_agent_id)
```

### 5.6 Table: agent_message

```
agent_message
    id                  UUID PK DEFAULT gen_random_uuid()
    team_id             UUID NOT NULL FK team(id) CASCADE
    from_agent_id       UUID NOT NULL FK agent(id)
    to_agent_id         UUID FK agent(id) NULL (broadcast)
    channel             TEXT NOT NULL DEFAULT 'direct'
    message_type        TEXT NOT NULL
    content             TEXT NOT NULL
    metadata_json       JSONB NOT NULL DEFAULT '{}'
    read_at             TIMESTAMPTZ NULL
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Note: `metadata` column mapped as `metadata_json` in Python (SA reserved word convention from Phase 1).

### 5.7 Table: collaboration_session

```
collaboration_session
    id                      UUID PK DEFAULT gen_random_uuid()
    team_id                 UUID NOT NULL FK team(id) CASCADE
    conversation_id         UUID FK conversation(id)
    lead_agent_id           UUID NOT NULL FK agent(id)
    pattern                 TEXT NOT NULL
    goal                    TEXT NOT NULL
    context                 TEXT NULL
    max_duration_seconds    INT NOT NULL DEFAULT 600
    max_total_cost_usd      DECIMAL(10,6) NOT NULL DEFAULT 0.50
    max_rounds              INT NOT NULL DEFAULT 5
    status                  TEXT NOT NULL DEFAULT 'planning'
    current_stage           INT NULL
    stages_completed        INT NOT NULL DEFAULT 0
    total_cost_usd          DECIMAL(10,6) NOT NULL DEFAULT 0
    final_output            TEXT NULL
    stage_outputs           JSONB NOT NULL DEFAULT '[]'
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    completed_at            TIMESTAMPTZ NULL
```

### 5.8 Table: collaboration_participant_v2

```
collaboration_participant_v2
    id              UUID PK DEFAULT gen_random_uuid()
    session_id      UUID NOT NULL FK collaboration_session(id) CASCADE
    agent_id        UUID NOT NULL FK agent(id)
    role            TEXT NOT NULL DEFAULT 'worker'
    stage           INT NULL
    task_id         UUID FK agent_task(id)
    status          TEXT NOT NULL DEFAULT 'waiting'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    UNIQUE (session_id, agent_id)
```

### 5.9 Indexes (20 total)

```
-- conversation_participant
idx_participant_conversation ON conversation_participant (conversation_id) WHERE left_at IS NULL
idx_participant_agent ON conversation_participant (agent_id) WHERE left_at IS NULL

-- agent_handoff
idx_handoff_conversation ON agent_handoff (conversation_id, created_at)

-- routing_decision_log
idx_routing_log_team ON routing_decision_log (team_id, created_at)
idx_routing_log_conversation ON routing_decision_log (conversation_id)
idx_routing_log_strategy ON routing_decision_log (strategy)
idx_routing_log_scores_gin ON routing_decision_log USING GIN (scores)

-- agent_task
idx_agent_task_team ON agent_task (team_id, status, created_at DESC)
idx_agent_task_assignee ON agent_task (assigned_to_agent_id, status)
idx_agent_task_creator ON agent_task (created_by_agent_id, created_at DESC)
idx_agent_task_parent ON agent_task (parent_task_id) WHERE parent_task_id IS NOT NULL
idx_agent_task_conversation ON agent_task (conversation_id) WHERE conversation_id IS NOT NULL

-- agent_message
idx_agent_message_recipient ON agent_message (to_agent_id, read_at) WHERE read_at IS NULL
idx_agent_message_channel ON agent_message (channel, created_at DESC)
idx_agent_message_team ON agent_message (team_id, created_at DESC)

-- collaboration_session
idx_collab_session_team ON collaboration_session (team_id, status, created_at DESC)
idx_collab_session_lead ON collaboration_session (lead_agent_id, status)

-- collaboration_participant_v2
idx_collab_participant_session ON collaboration_participant_v2 (session_id, role)
idx_collab_participant_agent ON collaboration_participant_v2 (agent_id, status)
```

## 6. Dependency Graph (Service Level)

```
Level 0 (No deps):
    collaboration/models.py     -- All Pydantic models + Enums
    moe/models.py               -- ExpertScore, SelectionStrategy, etc.

Level 1 (Depends on models):
    collaboration/discovery.py  -- AgentDirectory (needs AgentProfile model)
    collaboration/message_bus.py -- AgentMessageBus (needs AgentMessage model)
    collaboration/router.py     -- AgentRouter (needs RoutingDecision model)
    collaboration/handoff.py    -- HandoffManager (needs HandoffResult model)
    collaboration/multi_agent.py -- MultiAgent (needs models)
    collaboration/team_memory_bus.py -- TeamMemoryBus (needs models)
    moe/expert_gate.py          -- ExpertGate (needs ExpertScore)
    moe/expert_selector.py      -- ExpertSelector (needs SelectionResult)

Level 2 (Depends on Level 1 services):
    moe/response_aggregator.py  -- needs ExpertResponse from Level 1
    collaboration/task_delegator.py -- needs MessageBus, Discovery
    collaboration/report_manager.py -- needs TaskDelegator

Level 3 (Depends on Level 2):
    collaboration/orchestrator.py -- needs TaskDelegator, MessageBus, Discovery

Level 4 (Integration):
    api/routers/collaboration.py -- needs all collaboration services
    workers/tasks/collaboration.py -- needs TaskDelegator
    src/api/routers/chat.py modification -- needs Router, ExpertGate, ExpertSelector
```

## 7. Test Architecture

```
tests/test_collaboration/
    conftest.py                          -- Shared fixtures (MUST be created first)
    test_models.py                       -- Pydantic model validation
    test_agent_router.py                 -- AgentRouter unit tests
    test_handoff.py                      -- HandoffManager unit tests
    test_multi_agent.py                  -- Multi-agent conversation tests
    test_team_memory_bus.py              -- Team memory propagation tests
    test_agent_discovery.py              -- AgentDirectory tests
    test_task_delegator.py               -- TaskDelegator tests (mocked Celery)
    test_agent_message_bus.py            -- AgentMessageBus tests (mocked Redis)
    test_report_manager.py               -- ReportManager tests
    test_collaboration_orchestrator.py   -- CollaborationOrchestrator tests
    test_expert_gate.py                  -- ExpertGate 4-signal scoring tests
    test_expert_selector.py              -- ExpertSelector strategy tests
    test_response_aggregator.py          -- ResponseAggregator tests
    test_routing_log.py                  -- Routing decision logging tests

tests/test_workers/
    test_collaboration_tasks.py          -- Celery task for agent execution

tests/test_api/
    test_collaboration_router.py         -- API endpoint tests
```

### 7.1 Test Fixture Strategy (conftest.py)

```python
# Key fixtures needed:
@pytest.fixture
def mock_agent_orm()          # AgentORM instance with skills, personality
@pytest.fixture
def mock_team_agents()        # List of 3-5 AgentORM instances with varied skills
@pytest.fixture
def mock_routing_decision()   # RoutingDecision model instance
@pytest.fixture
def mock_expert_scores()      # List of ExpertScore instances
@pytest.fixture
def mock_db_session()         # AsyncMock session with collaboration table support
@pytest.fixture
def mock_redis_client()       # AsyncMock Redis with pub/sub support
@pytest.fixture
def mock_embedding_service()  # AsyncMock for skill matching embeddings
@pytest.fixture
def collaboration_settings()  # Settings with all Phase 7 flags enabled
```

## 8. Safety and Constraint Enforcement

### 8.1 Delegation Safety (in TaskDelegator)
- `MAX_DELEGATION_DEPTH = 3`: Check via parent_task_id chain traversal
- Cycle detection: Walk parent chain, fail if creator appears as assignee in chain
- Concurrent limit: `MAX_CONCURRENT_TASKS = 5` per agent (query agent_task WHERE status IN ('pending', 'in_progress'))
- Budget check: `CostGuard.check_budget()` before dispatch

### 8.2 Collaboration Safety (in CollaborationOrchestrator)
- Duration timeout: `max_duration_seconds = 600` (asyncio.wait_for or Celery soft_time_limit)
- Cost cap: `max_total_cost_usd = 0.50` (accumulated from task costs)
- Round limit: `max_rounds = 5` (for PEER_REVIEW pattern)

### 8.3 Feature Flag Safety
- All collaboration features default to False
- Progressive activation: collaboration -> expert_gate -> ensemble -> delegation -> full_collaboration
- Each flag check wraps the entire feature path (no partial activation)
