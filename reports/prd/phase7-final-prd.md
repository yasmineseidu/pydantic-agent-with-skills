# PRD: Phase 7 - Agent Collaboration System

> Generated: 2026-02-10 | Status: PENDING APPROVAL
> Complexity Score: 8 (Ambiguity=1, Integration=2, Novelty=2, Risk=2, Scale=1)
> Tasks: 58 | Waves: 11 | Critical Path Depth: 8 | Max Parallelism: 7

---

## Overview

Phase 7 introduces a multi-agent collaboration layer on top of the existing skill agent system (Phases 2-6). It enables agents to route requests to the most qualified team member, delegate tasks to other agents, hand off conversations, communicate via pub/sub messaging, and collaborate in structured patterns (supervisor-worker, pipeline, peer review, brainstorm, consensus, delegation).

**Why**: The current system routes every request to a single agent. Real-world agent teams need intelligent routing to match requests with the best expert, task delegation for complex work decomposition, and structured collaboration patterns for multi-step reasoning tasks.

**Two subsystems**:
1. **MoE Agent Routing** -- 4-signal expert scoring (skill_match, past_performance, personality_fit, load_balance) with 4 selection strategies (TOP_1, TOP_K, ENSEMBLE, CASCADE)
2. **Collaboration Stack** -- Task delegation via Celery, inter-agent messaging via Redis pub/sub, 6 collaboration patterns via CollaborationOrchestrator

---

## Mode: EXISTING

### What currently exists

| Component | Phase | Status |
|---|---|---|
| Agent ORM with skills, personality, slug | Phase 1 | Operational |
| MessageORM with agent_id FK | Phase 1 | Operational (Phase 7 does NOT add this column) |
| Bulletproof memory system (5-signal retrieval, double-pass extraction) | Phase 2 | Operational |
| MoE model routing (ComplexityScore, ModelRouter, CostGuard) | Phase 2 | Operational |
| Redis caching (hot cache, working memory, embedding cache) | Phase 3 | Operational |
| FastAPI auth + 7 API routers | Phase 4 | Operational |
| SSE streaming + WebSocket | Phase 5 | Operational |
| Celery background processing (3 task types, schedules) | Phase 6 | Operational |
| FeatureFlags with `enable_agent_collaboration` flag | Phase 1 | Present but unused |

### How Phase 7 integrates

Phase 7 creates a new `src/collaboration/` package (10 modules), adds 3 modules to `src/moe/`, creates 7 new DB tables (migration 004), adds 1 API router with 10 endpoints, adds 1 Celery task, and modifies 7 existing files.

Integration touches the critical chat path (`src/api/routers/chat.py`), all controlled by feature flags with fallback to direct dispatch.

---

## Requirements

### Functional Requirements

**FR-1: Agent Routing**
- FR-1.1: @mention routing -- `@kyra help me` routes to agent with slug "kyra"
- FR-1.2: Skill-based routing -- Match query keywords to agent skills
- FR-1.3: 4-signal expert scoring -- skill_match (0.40), past_performance (0.25), personality_fit (0.20), load_balance (0.15)
- FR-1.4: 4 selection strategies -- TOP_1, TOP_K, ENSEMBLE, CASCADE
- FR-1.5: Response aggregation -- ENSEMBLE mode synthesizes multi-expert responses via meta-model
- FR-1.6: Routing decision logging -- All routing decisions persisted with scores, latency, selected agents

**FR-2: Agent Handoff**
- FR-2.1: Conversation transfer from one agent to another with context summary
- FR-2.2: Return-to-previous functionality (reverse last handoff)
- FR-2.3: Participant role tracking (primary, invited, handoff_source)

**FR-3: Task Delegation**
- FR-3.1: Agent-to-agent task creation with instructions, constraints, priority
- FR-3.2: Celery-based async execution with timeout
- FR-3.3: Depth-limited delegation (max 3 levels)
- FR-3.4: Cycle detection (A->B->A prevented)
- FR-3.5: Concurrent task limits (5 per agent)
- FR-3.6: Result retrieval via Redis pub/sub or polling

**FR-4: Inter-Agent Messaging**
- FR-4.1: Direct messages (agent-to-agent)
- FR-4.2: Broadcast messages (agent-to-team)
- FR-4.3: Channel-based messaging (direct, team, task, collab)
- FR-4.4: Redis pub/sub for real-time, DB for persistence
- FR-4.5: Inbox with read/unread tracking

**FR-5: Collaboration Sessions**
- FR-5.1: 6 collaboration patterns: SUPERVISOR_WORKER, PIPELINE, PEER_REVIEW, BRAINSTORM, CONSENSUS, DELEGATION
- FR-5.2: Session lifecycle: PLANNING -> ACTIVE -> SYNTHESIZING -> COMPLETED/FAILED
- FR-5.3: Cost cap enforcement ($0.50 default)
- FR-5.4: Duration timeout (600s default)
- FR-5.5: Lead agent synthesis of worker outputs

**FR-6: Structured Reports**
- FR-6.1: Template-based report requests (CODE_REVIEW, RESEARCH_SUMMARY, RISK_ASSESSMENT)
- FR-6.2: Report validation (required sections present)
- FR-6.3: Model tier selection based on complexity

**FR-7: API Endpoints (10 total)**
- FR-7.1: Handoff, multi-agent, discovery, delegation, messaging, collaboration endpoints
- FR-7.2: JWT/API key auth on all endpoints
- FR-7.3: Feature flag checks (403 when disabled)

### Non-Functional Requirements

**NFR-1: Backward Compatibility**
- ALL flags default to False -- existing behavior unchanged
- CLI startup unaffected
- Existing tests continue to pass

**NFR-2: Performance**
- Expert scoring < 100ms for team of 10 agents (without LLM calls)
- Routing decision logged without blocking response

**NFR-3: Safety**
- Max delegation depth: 3
- Max concurrent tasks per agent: 5
- Task timeout: 120s
- Collaboration timeout: 600s
- Per-task token budget: 4000
- Per-collaboration cost cap: $0.50
- Max tool calls per task: 10
- Cycle detection in delegation chains

**NFR-4: Feature Flag Progression**
```
Level 0: All off (direct dispatch, current behavior)
Level 1: enable_agent_collaboration = True (AgentRouter, @mention, skill matching)
Level 2: enable_expert_gate = True (4-signal ExpertGate scoring)
Level 3: enable_ensemble_mode = True (multi-expert ENSEMBLE + aggregation)
Level 4: enable_task_delegation = True (Celery-based delegation)
Level 5: enable_collaboration = True (full collaboration sessions)
```

### Success Criteria

- All 7 DB tables created successfully (migration 004)
- All 10 API endpoints functional with auth
- All 4 routing strategies produce correct results
- All 6 collaboration patterns execute successfully
- Delegation safety constraints enforced (depth, cycles, concurrency)
- No regression in existing ~934 tests
- ~180 new tests added, all passing
- Lint clean (`ruff check`) and type-safe (`mypy`)

---

## Architecture

### Component Overview

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

### New Packages

```
src/collaboration/           # 10 new modules
    __init__.py              models.py         router.py
    discovery.py             handoff.py        multi_agent.py
    team_memory_bus.py       message_bus.py    task_delegator.py
    report_manager.py        orchestrator.py

src/moe/ (additions)         # 3 new modules
    models.py                expert_gate.py    expert_selector.py
    response_aggregator.py
```

### Database Schema (7 new tables)

| Table | Purpose | Key Constraints |
|---|---|---|
| conversation_participant | Track multi-agent conversations | UNIQUE(conversation_id, agent_id) |
| agent_handoff | Log agent-to-agent transfers | FK conversation, FK agent (from/to) |
| routing_decision_log | Audit trail for routing decisions | JSONB scores, GIN index |
| agent_task | Delegated task lifecycle | CHECK(depth<=3), CHECK(no self-delegation) |
| agent_message | Inter-agent messages | Partial index on unread |
| collaboration_session | Multi-agent session state | Cost cap, duration timeout |
| collaboration_participant_v2 | Session participants | UNIQUE(session_id, agent_id) |

Plus 1 new ENUM type (`participant_role`) and ~20 indexes.

### Integration Points (7 modified files)

| File | Change |
|---|---|
| `src/settings.py` | Add 4 feature flags to FeatureFlags |
| `src/dependencies.py` | Add 8 Optional fields + TYPE_CHECKING imports |
| `src/api/routers/chat.py` | Inject `_route_to_agent()` at Step 1 |
| `src/api/app.py` | Register collaboration_router |
| `src/api/routers/__init__.py` | Export collaboration_router |
| `src/moe/__init__.py` | Export Phase 7 classes |
| `src/db/models/__init__.py` | Export 7 new ORM models |

### Key Design Decisions

1. **ExpertScore follows ComplexityScore pattern** -- `ClassVar[dict[str,float]]` for WEIGHTS, `@computed_field @property` for overall score, `Field(ge=0.0, le=1.0)` validators
2. **Fixed weights (0.40/0.25/0.20/0.15)** -- Learned weights deferred to future phase
3. **No ALTER TABLE on message** -- `agent_id` column already exists from Phase 1
4. **metadata -> metadata_json** -- SA reserved word convention carried forward
5. **Celery for delegation** -- Reuses Phase 6 patterns (asyncio.run bridge, fresh sessions)
6. **Redis pub/sub for messaging** -- Graceful degradation when Redis unavailable
7. **Feature flag cascade** -- Each level builds on previous; never partial activation

---

## Task Tree

### Summary: 58 Tasks across 11 Waves

| Wave | Tasks | Parallelism | Focus |
|------|-------|-------------|-------|
| 1 | P7-01..P7-05 | 5 | Foundation: models, enums, types (zero deps) |
| 2 | P7-06..P7-11 | 6 | DB: ORM models, migration, conftest |
| 3 | P7-12..P7-18 | 7 | Services Layer 1: independent services |
| 4 | P7-19..P7-24 | 6 | Services Layer 2: dependent services + MoE |
| 5 | P7-25..P7-29 | 5 | Services Layer 3: orchestrator, aggregator, Celery |
| 6 | P7-30..P7-34 | 5 | Tests Wave 1: model tests + foundation service tests |
| 7 | P7-35..P7-41 | 7 | Tests Wave 2: all remaining service tests |
| 8 | P7-42..P7-47 | 6 | Integration: settings, deps, routers, chat.py |
| 9 | P7-48..P7-52 | 5 | Integration tests |
| 10 | P7-53..P7-56 | 4 | E2E smoke tests |
| 11 | P7-57..P7-58 | 2 | Final validation: full test suite + lint |

### Wave 1: Foundation (Zero Dependencies) -- 5 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-01 | Create collaboration Pydantic models + Enums | `src/collaboration/models.py` | L | -- |
| P7-02 | Create MoE Pydantic models (ExpertScore etc.) | `src/moe/models.py` | M | -- |
| P7-03 | Create collaboration package __init__.py | `src/collaboration/__init__.py` | S | -- |
| P7-04 | Create test_collaboration package __init__.py | `tests/test_collaboration/__init__.py` | S | -- |
| P7-05 | Add 4 feature flags to settings.py | `src/settings.py` | S | -- |

### Wave 2: Database Layer -- 6 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-06 | Create 7 collaboration ORM models | `src/db/models/collaboration.py` | L | P7-01 |
| P7-07 | Create Alembic migration 004 | `src/db/migrations/versions/004_phase7_collaboration.py` | L | P7-06 |
| P7-08 | Update db/models/__init__.py exports | `src/db/models/__init__.py` | S | P7-06 |
| P7-09 | Create test_collaboration conftest.py | `tests/test_collaboration/conftest.py` | M | P7-01, P7-02 |
| P7-10 | Create MoE test conftest additions | `tests/test_collaboration/conftest_moe.py` | S | P7-02 |
| P7-11 | Add collaboration deps to AgentDependencies | `src/dependencies.py` | S | P7-01 |

### Wave 3: Services Layer 1 (Independent) -- 7 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-12 | Implement AgentRouter (baseline routing) | `src/collaboration/router.py` | M | P7-01, P7-06 |
| P7-13 | Implement AgentDirectory (discovery) | `src/collaboration/discovery.py` | M | P7-01, P7-06 |
| P7-14 | Implement HandoffManager | `src/collaboration/handoff.py` | M | P7-01, P7-06 |
| P7-15 | Implement MultiAgentManager | `src/collaboration/multi_agent.py` | M | P7-01, P7-06 |
| P7-16 | Implement TeamMemoryBus | `src/collaboration/team_memory_bus.py` | S | P7-01 |
| P7-17 | Implement AgentMessageBus | `src/collaboration/message_bus.py` | M | P7-01, P7-06 |
| P7-18 | Implement RoutingLogger | `src/collaboration/routing_log.py` | S | P7-01, P7-06 |

### Wave 4: Services Layer 2 + MoE -- 6 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-19 | Implement ExpertGate (4-signal scoring) | `src/moe/expert_gate.py` | L | P7-02, P7-06, P7-13 |
| P7-20 | Implement ExpertSelector (4 strategies) | `src/moe/expert_selector.py` | M | P7-02 |
| P7-21 | Implement TaskDelegator | `src/collaboration/task_delegator.py` | L | P7-01, P7-06, P7-13, P7-17 |
| P7-22 | Implement ReportManager | `src/collaboration/report_manager.py` | M | P7-01, P7-21 |
| P7-23 | Update moe/__init__.py with Phase 7 exports | `src/moe/__init__.py` | S | P7-02, P7-19, P7-20 |
| P7-24 | Update collaboration __init__.py exports | `src/collaboration/__init__.py` | S | P7-12..P7-18 |

### Wave 5: Services Layer 3 (High-Dependency) -- 5 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-25 | Implement ResponseAggregator | `src/moe/response_aggregator.py` | M | P7-02, P7-19 |
| P7-26 | Implement CollaborationOrchestrator | `src/collaboration/orchestrator.py` | L | P7-01, P7-21, P7-17, P7-13 |
| P7-27 | Implement Celery collaboration task | `workers/tasks/collaboration.py` | M | P7-21 |
| P7-28 | Implement collaboration API router | `src/api/routers/collaboration.py` | L | P7-12..P7-17, P7-21 |
| P7-29 | Update api/routers/__init__.py | `src/api/routers/__init__.py` | S | P7-28 |

### Wave 6: Tests Wave 1 (Foundation) -- 5 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-30 | Test collaboration models (~20 tests) | `tests/test_collaboration/test_models.py` | M | P7-01 |
| P7-31 | Test MoE models (~15 tests) | `tests/test_collaboration/test_moe_models.py` | M | P7-02 |
| P7-32 | Test AgentRouter (~12 tests) | `tests/test_collaboration/test_agent_router.py` | M | P7-12, P7-09 |
| P7-33 | Test HandoffManager (~10 tests) | `tests/test_collaboration/test_handoff.py` | M | P7-14, P7-09 |
| P7-34 | Test AgentDirectory (~10 tests) | `tests/test_collaboration/test_agent_discovery.py` | M | P7-13, P7-09 |

### Wave 7: Tests Wave 2 (Remaining Services) -- 7 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-35 | Test ExpertGate (~15 tests) | `tests/test_collaboration/test_expert_gate.py` | L | P7-19, P7-09, P7-10 |
| P7-36 | Test ExpertSelector (~12 tests) | `tests/test_collaboration/test_expert_selector.py` | M | P7-20, P7-09, P7-10 |
| P7-37 | Test ResponseAggregator (~8 tests) | `tests/test_collaboration/test_response_aggregator.py` | M | P7-25, P7-09 |
| P7-38 | Test TaskDelegator (~18 tests) | `tests/test_collaboration/test_task_delegator.py` | L | P7-21, P7-09 |
| P7-39 | Test AgentMessageBus (~12 tests) | `tests/test_collaboration/test_agent_message_bus.py` | M | P7-17, P7-09 |
| P7-40 | Test ReportManager (~10 tests) | `tests/test_collaboration/test_report_manager.py` | M | P7-22, P7-09 |
| P7-41 | Test RoutingLogger (~6 tests) | `tests/test_collaboration/test_routing_log.py` | S | P7-18, P7-09 |

### Wave 8: Integration Tasks -- 6 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-42 | Integrate routing into chat.py | `src/api/routers/chat.py` | M | P7-12, P7-19, P7-20, P7-18, P7-05 |
| P7-43 | Register collaboration router in app.py | `src/api/app.py` | S | P7-28, P7-29 |
| P7-44 | Test MultiAgentManager (~10 tests) | `tests/test_collaboration/test_multi_agent.py` | M | P7-15, P7-09 |
| P7-45 | Test TeamMemoryBus (~5 tests) | `tests/test_collaboration/test_team_memory_bus.py` | S | P7-16, P7-09 |
| P7-46 | Test CollaborationOrchestrator (~20 tests) | `tests/test_collaboration/test_collaboration_orchestrator.py` | L | P7-26, P7-09 |
| P7-47 | Test Celery collaboration task (~8 tests) | `tests/test_workers/test_collaboration_tasks.py` | M | P7-27, P7-09 |

### Wave 9: Integration Tests -- 5 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-48 | Test collaboration API router (~15 tests) | `tests/test_api/test_collaboration_router.py` | L | P7-28, P7-09 |
| P7-49 | Test chat.py routing integration (~10 tests) | `tests/test_api/test_chat_routing.py` | M | P7-42, P7-09 |
| P7-50 | Test ORM models (~10 tests) | `tests/test_collaboration/test_orm_models.py` | M | P7-06, P7-09 |
| P7-51 | Test migration 004 structure (~5 tests) | `tests/test_collaboration/test_migration.py` | S | P7-07 |
| P7-52 | Test db/models exports (~3 tests) | `tests/test_collaboration/test_model_exports.py` | S | P7-08 |

### Wave 10: Cross-Service Smoke Tests -- 4 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-53 | E2E routing smoke test (~5 tests) | `tests/test_collaboration/test_routing_e2e.py` | M | P7-49 |
| P7-54 | E2E delegation smoke test (~5 tests) | `tests/test_collaboration/test_delegation_e2e.py` | M | P7-46, P7-47 |
| P7-55 | E2E collaboration smoke test (~5 tests) | `tests/test_collaboration/test_collaboration_e2e.py` | M | P7-46 |
| P7-56 | Backward compatibility smoke test (~5 tests) | `tests/test_collaboration/test_backward_compat.py` | S | P7-42, P7-43 |

### Wave 11: Final Validation -- 2 tasks

| ID | Subject | Files | Size | BlockedBy |
|---|---|---|---|---|
| P7-57 | Run full test suite (tester) | -- | M | P7-53, P7-54, P7-55, P7-56 |
| P7-58 | Run lint + type checks (tester) | -- | S | P7-57 |

---

## Implementation Order

### Critical Path (Longest Chain, Depth 8)

```
P7-01 -> P7-06 -> P7-21 -> P7-26 -> P7-46 -> P7-55 -> P7-57 -> P7-58
  (models)  (ORM)  (delegator) (orch)  (test)   (e2e)   (suite)  (lint)
```

### Build Strategy

**Wave-based parallel execution** with maximum 7 concurrent agents:

```
Wave 1  [5 agents]  ===========================
Wave 2  [6 agents]    ===========================
Wave 3  [7 agents]       ===========================
Wave 4  [6 agents]          ===========================
Wave 5  [5 agents]             ===========================
Wave 6  [5 agents]                ===========================
Wave 7  [7 agents]                   ===========================
Wave 8  [6 agents]                      ===========================
Wave 9  [5 agents]                         ===========================
Wave 10 [4 agents]                            ====================
Wave 11 [2 agents]                               ==========
```

### Dependency Highlights

- **P7-01** (collaboration models) is the most critical leaf -- 15+ tasks depend on it directly or transitively
- **P7-06** (ORM models) blocks all DB-dependent services (Waves 3-5)
- **P7-09** (conftest) blocks all test tasks (Waves 6-10)
- **P7-21** (TaskDelegator) is the highest-fan-out service -- used by orchestrator, report manager, Celery task
- **P7-42** (chat.py integration) is the highest-risk task -- modifies the critical chat path

---

## Risk Areas

### High Risk

**1. Chat Router Integration (P7-42)**
- `src/api/routers/chat.py` is the most complex file in the codebase (~200+ lines, 8-step flow)
- Phase 7 injects routing logic at Step 1 (resolve agent)
- Error in routing breaks ALL chat functionality
- **Mitigation**: Feature flag wrapping with fallback to direct dispatch; separate task from service implementation; no regression tests run before merge

**2. Dependencies Dataclass Growth**
- `src/dependencies.py` already has 18 Optional fields; Phase 7 adds 8 more (26 total)
- Risk: initialization complexity, more None checks
- **Mitigation**: Group Phase 7 fields under comment block; consider nested dataclass in Phase 8

### Medium Risk

**3. Celery Agent Execution (P7-27)**
- Running a full agent inside a Celery worker requires fresh DB session, LLM client init, token tracking independent of FastAPI
- **Mitigation**: Follow Phase 6 patterns exactly (asyncio.run bridge, pool_size=3, fresh sessions)

**4. Migration 004 Size**
- 7 new tables, 1 enum, ~20 indexes in a single migration
- **Mitigation**: Logical sections within file; test downgrade path; matches Phase 1 migration pattern

### Low Risk

**5. Feature Flag Count** -- 5 total flags with well-defined progression

**6. CollaborationOrchestrator Complexity** -- 6 patterns is many, but each pattern is 20-30 lines of delegation logic

---

## File Inventory

### New Files (~30)

| File | Purpose |
|---|---|
| `src/collaboration/__init__.py` | Package init + exports |
| `src/collaboration/models.py` | All Pydantic models + Enums |
| `src/collaboration/router.py` | AgentRouter (baseline routing) |
| `src/collaboration/discovery.py` | AgentDirectory |
| `src/collaboration/handoff.py` | HandoffManager |
| `src/collaboration/multi_agent.py` | Multi-agent conversations |
| `src/collaboration/team_memory_bus.py` | Shared memory propagation |
| `src/collaboration/message_bus.py` | AgentMessageBus (Redis + DB) |
| `src/collaboration/task_delegator.py` | TaskDelegator (Celery dispatch) |
| `src/collaboration/report_manager.py` | ReportManager |
| `src/collaboration/orchestrator.py` | CollaborationOrchestrator (6 patterns) |
| `src/collaboration/routing_log.py` | RoutingLogger |
| `src/moe/models.py` | ExpertScore, SelectionStrategy, etc. |
| `src/moe/expert_gate.py` | ExpertGate (4-signal scoring) |
| `src/moe/expert_selector.py` | ExpertSelector (4 strategies) |
| `src/moe/response_aggregator.py` | ResponseAggregator (ENSEMBLE) |
| `src/db/models/collaboration.py` | 7 ORM models |
| `src/db/migrations/versions/004_phase7_collaboration.py` | Migration |
| `src/api/routers/collaboration.py` | 10 API endpoints |
| `workers/tasks/collaboration.py` | Celery agent execution |
| `tests/test_collaboration/__init__.py` | Test package |
| `tests/test_collaboration/conftest.py` | Shared fixtures |
| `tests/test_collaboration/conftest_moe.py` | MoE fixtures |
| `tests/test_collaboration/test_models.py` | Model tests |
| `tests/test_collaboration/test_moe_models.py` | MoE model tests |
| `tests/test_collaboration/test_agent_router.py` | Router tests |
| `tests/test_collaboration/test_handoff.py` | Handoff tests |
| `tests/test_collaboration/test_agent_discovery.py` | Discovery tests |
| `tests/test_collaboration/test_expert_gate.py` | Expert gate tests |
| `tests/test_collaboration/test_expert_selector.py` | Selector tests |
| `tests/test_collaboration/test_response_aggregator.py` | Aggregator tests |
| `tests/test_collaboration/test_task_delegator.py` | Delegator tests |
| `tests/test_collaboration/test_agent_message_bus.py` | Message bus tests |
| `tests/test_collaboration/test_report_manager.py` | Report tests |
| `tests/test_collaboration/test_routing_log.py` | Routing log tests |
| `tests/test_collaboration/test_collaboration_orchestrator.py` | Orchestrator tests |
| `tests/test_collaboration/test_multi_agent.py` | Multi-agent tests |
| `tests/test_collaboration/test_team_memory_bus.py` | Memory bus tests |
| `tests/test_collaboration/test_orm_models.py` | ORM model tests |
| `tests/test_collaboration/test_migration.py` | Migration tests |
| `tests/test_collaboration/test_model_exports.py` | Export tests |
| `tests/test_collaboration/test_routing_e2e.py` | E2E routing |
| `tests/test_collaboration/test_delegation_e2e.py` | E2E delegation |
| `tests/test_collaboration/test_collaboration_e2e.py` | E2E collaboration |
| `tests/test_collaboration/test_backward_compat.py` | Backward compat |
| `tests/test_api/test_collaboration_router.py` | API router tests |
| `tests/test_api/test_chat_routing.py` | Chat routing tests |
| `tests/test_workers/test_collaboration_tasks.py` | Celery tests |

### Modified Files (7)

| File | Modification |
|---|---|
| `src/settings.py` | Add 4 feature flags |
| `src/dependencies.py` | Add 8 Optional fields + TYPE_CHECKING imports |
| `src/api/routers/chat.py` | Inject routing at Step 1 |
| `src/api/app.py` | Register collaboration_router |
| `src/api/routers/__init__.py` | Export collaboration_router |
| `src/moe/__init__.py` | Export Phase 7 classes |
| `src/db/models/__init__.py` | Export 7 ORM models |

### Totals

- **~48 new files** + **7 modified files** = **~55 files**
- **~5,000-6,000 new LOC** (implementation + tests)
- **~180 new tests** (bringing total from ~934 to ~1,114)

---

## Supporting Documents

Full details available in:
- `/Users/yasmynat/coding/pydantic-skill-agents/pydantic-agent-with-skills/reports/prd/phase7-research.md` -- Technical research report
- `/Users/yasmynat/coding/pydantic-skill-agents/pydantic-agent-with-skills/reports/prd/phase7-architecture.md` -- Architecture document with data flows, DB schema, dependency graph
- `/Users/yasmynat/coding/pydantic-skill-agents/pydantic-agent-with-skills/reports/prd/phase7-task-tree.md` -- Full 58-task decomposition with acceptance criteria per task

---

## Approval

Ready to approve this plan? Say **"go"** and I will create all 58 tasks in the task system with proper dependency chains. Or tell me what to change.
