# Phase 7: Agent Collaboration - Task Decomposition

> Generated: 2026-02-10 | Total Tasks: 58 | Waves: 11 | Critical Path Depth: 11

## Task Naming Convention

`P7-{nn}` where nn is 01-58. Dependencies reference task IDs.

## Wave Summary

| Wave | Tasks | Parallelism | Description |
|------|-------|-------------|-------------|
| 1 | P7-01..P7-05 | 5 | Foundation: models, enums, types (zero deps) |
| 2 | P7-06..P7-11 | 6 | DB: ORM models, migration, conftest |
| 3 | P7-12..P7-18 | 7 | Services Layer 1: independent services |
| 4 | P7-19..P7-24 | 6 | Services Layer 2: dependent services + MoE |
| 5 | P7-25..P7-29 | 5 | Services Layer 3: orchestrator, aggregator, Celery |
| 6 | P7-30..P7-34 | 5 | Tests Wave 1: model tests + foundation service tests |
| 7 | P7-35..P7-41 | 7 | Tests Wave 2: all remaining service tests |
| 8 | P7-42..P7-47 | 6 | Integration: settings, deps, routers, chat.py |
| 9 | P7-48..P7-52 | 5 | Tests Wave 3: integration tests |
| 10 | P7-53..P7-56 | 4 | Smoke tests + cross-service tests |
| 11 | P7-57..P7-58 | 2 | Final validation: full test suite + lint |

---

## WAVE 1: Foundation (Zero Dependencies)

### P7-01: Create collaboration Pydantic models
- **Files**: `src/collaboration/models.py`
- **Size**: L
- **Agent**: builder
- **Description**: Create ALL Pydantic models and Enums for the collaboration system. This is the foundation file that everything else imports from.
- **Contains**:
  - Enums: `ParticipantRole`, `AgentTaskType`, `AgentTaskStatus`, `TaskPriority`, `AgentMessageType`, `CollaborationPattern`, `CollaborationStatus`, `ReportType`
  - Models: `RoutingDecision`, `HandoffResult`, `AgentRecommendation`, `AgentProfile`, `AgentAvailability`, `AgentTaskCreate`, `AgentTask`, `AgentMessage`, `ReportRequest`, `ReportTemplate`, `Report`, `CollaborationParticipantInfo`, `StageOutput`, `CollaborationSession`, `ParticipantConfig`
  - Constants: `REPORT_TEMPLATES` dict, `MAX_DELEGATION_DEPTH=3`, `MAX_CONCURRENT_TASKS=5`
- **Acceptance Criteria**:
  - All models have Google docstrings with Args/Returns
  - All fields have type annotations with Field() validators where appropriate
  - All Enums use `str, Enum` base for JSON serialization
  - `ruff check src/collaboration/models.py` passes
  - `mypy src/collaboration/models.py` passes

### P7-02: Create MoE Pydantic models
- **Files**: `src/moe/models.py`
- **Size**: M
- **Agent**: builder
- **Description**: Create Pydantic models for the MoE expert routing layer. Follow `model_tier.py` patterns exactly.
- **Contains**:
  - Enums: `SelectionStrategy` (TOP_1, TOP_K, ENSEMBLE, CASCADE)
  - Models: `ExpertScore` (with WEIGHTS ClassVar and @computed_field weighted_total), `SelectionResult`, `ExpertResponse`, `AggregatedResponse`
  - ExpertScore WEIGHTS: skill_match=0.40, past_performance=0.25, personality_fit=0.20, load_balance=0.15
- **Acceptance Criteria**:
  - `ExpertScore.WEIGHTS` uses `ClassVar[dict[str, float]]` matching `ComplexityScore.WEIGHTS` pattern
  - `ExpertScore.overall` uses `@computed_field @property` matching `weighted_total` pattern
  - All 4 signal fields have `Field(ge=0.0, le=1.0)` constraints
  - `ruff check src/moe/models.py` passes
  - `mypy src/moe/models.py` passes

### P7-03: Create collaboration package __init__.py
- **Files**: `src/collaboration/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Create the package init file with a docstring and placeholder imports. Actual imports will be added as modules are created.
- **Acceptance Criteria**:
  - File exists with module docstring: `"""Agent collaboration, routing, and multi-agent orchestration."""`
  - Empty `__all__` list (will be populated in Wave 8)

### P7-04: Create test_collaboration package __init__.py
- **Files**: `tests/test_collaboration/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Create the test package init file.
- **Acceptance Criteria**:
  - File exists with docstring `"""Tests for agent collaboration system."""`

### P7-05: Add feature flags to settings.py
- **Files**: `src/settings.py`
- **Size**: S
- **Agent**: builder
- **Description**: Add 4 new feature flags to the `FeatureFlags` class. All default to False. Must maintain backward compatibility (existing CLI works unchanged).
- **Changes**:
  - Add `enable_expert_gate: bool = Field(default=False, description="Phase 7: MoE 4-signal scoring")`
  - Add `enable_ensemble_mode: bool = Field(default=False, description="Phase 7: Multi-expert responses")`
  - Add `enable_task_delegation: bool = Field(default=False, description="Phase 7: AgentTask system")`
  - Add `enable_collaboration: bool = Field(default=False, description="Phase 7: Full collaboration sessions")`
- **Acceptance Criteria**:
  - `FeatureFlags` has all 4 new fields, all default False
  - `load_settings()` still works (test manually or via existing test suite)
  - `ruff check src/settings.py` passes
  - Existing tests that use Settings/FeatureFlags still pass

---

## WAVE 2: Database Layer

### P7-06: Create collaboration ORM models
- **Blocks**: P7-07
- **BlockedBy**: P7-01
- **Files**: `src/db/models/collaboration.py`
- **Size**: L
- **Agent**: builder
- **Description**: Create all 7 ORM models for Phase 7 collaboration tables. Follow `src/db/models/agent.py` patterns.
- **Contains**:
  - `ConversationParticipantORM` (conversation_participant)
  - `AgentHandoffORM` (agent_handoff)
  - `RoutingDecisionLogORM` (routing_decision_log)
  - `AgentTaskORM` (agent_task) -- with CheckConstraints for depth and self-delegation
  - `AgentMessageORM` (agent_message) -- metadata column mapped as metadata_json
  - `CollaborationSessionORM` (collaboration_session)
  - `CollaborationParticipantV2ORM` (collaboration_participant_v2)
- **Acceptance Criteria**:
  - All models inherit `Base, UUIDMixin, TimestampMixin` from `src/db/base.py`
  - All ForeignKeys use `ondelete="CASCADE"` where appropriate
  - JSONB columns use `postgresql.JSONB()` type
  - `metadata` column mapped as `metadata_json` (SA reserved word)
  - UniqueConstraints on (conversation_id, agent_id) and (session_id, agent_id)
  - CheckConstraints: `delegation_depth <= 3` and `created_by_agent_id != assigned_to_agent_id`
  - `ruff check src/db/models/collaboration.py` passes
  - `mypy src/db/models/collaboration.py` passes

### P7-07: Create Alembic migration 004
- **BlockedBy**: P7-06
- **Files**: `src/db/migrations/versions/004_phase7_collaboration.py`
- **Size**: L
- **Agent**: builder
- **Description**: Create migration 004 with all 7 tables, 1 enum type, ~20 indexes, and triggers. Follow migration 003 pattern exactly.
- **IMPORTANT**: Do NOT add agent_id to message table (already exists from earlier phase).
- **Contains**:
  - `upgrade()`: Create participant_role enum, 7 tables, ~20 indexes, 7 triggers (reuse trigger_set_updated_at)
  - `downgrade()`: Drop all 7 tables, drop participant_role enum
  - revision="004", down_revision="003"
- **Acceptance Criteria**:
  - `alembic check` reports no issues (if DB available)
  - downgrade drops all tables in correct order (respecting FKs)
  - All partial indexes use correct WHERE clauses
  - All GIN indexes on JSONB columns
  - Triggers use existing `trigger_set_updated_at()` function

### P7-08: Update db/models/__init__.py with Phase 7 exports
- **BlockedBy**: P7-06
- **Files**: `src/db/models/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Add imports and __all__ entries for all 7 new ORM models.
- **Acceptance Criteria**:
  - All 7 ORM models importable via `from src.db.models import ConversationParticipantORM` etc.
  - Existing imports unchanged
  - `ruff check src/db/models/__init__.py` passes

### P7-09: Create test_collaboration/conftest.py
- **BlockedBy**: P7-01, P7-02
- **Files**: `tests/test_collaboration/conftest.py`
- **Size**: M
- **Agent**: builder
- **Description**: Create shared test fixtures for all collaboration tests. Follow `tests/test_workers/conftest.py` patterns.
- **Contains**:
  - `mock_agent_orm()` - AgentORM with skills, personality, team_id
  - `mock_team_agents()` - List of 3-5 agents with varied skills (code_review, data_analysis, general)
  - `mock_routing_decision()` - RoutingDecision model instance
  - `mock_expert_scores()` - List of ExpertScore instances with varied scores
  - `mock_db_session()` - AsyncMock with execute, commit, rollback, add, flush, refresh
  - `mock_redis_client()` - AsyncMock with publish, subscribe, get, set
  - `mock_embedding_service()` - AsyncMock returning test embeddings
  - `collaboration_settings()` - Settings with all Phase 7 flags enabled
  - `mock_celery_task()` - MagicMock for Celery task dispatch
- **Acceptance Criteria**:
  - All fixtures use `@pytest.fixture` decorator
  - AsyncMock for all async operations
  - At least 3 agents with different skill sets for routing tests
  - Settings fixture has all 5 collaboration flags = True

### P7-10: Create MoE test conftest additions
- **BlockedBy**: P7-02
- **Files**: `tests/test_collaboration/conftest_moe.py` (imported by conftest.py)
- **Size**: S
- **Agent**: builder
- **Description**: Create MoE-specific test fixtures for expert gate/selector testing. Can be a separate file imported by conftest or added to conftest.py.
- **Contains**:
  - `sample_expert_scores()` - 5 ExpertScore instances with known values
  - `high_confidence_scores()` - All above 0.6 threshold
  - `low_confidence_scores()` - All below 0.6 threshold
  - `mixed_confidence_scores()` - Some above, some below threshold
- **Acceptance Criteria**:
  - Scores are mathematically correct (overall = weighted sum of 4 signals)
  - At least one fixture has a clear "winner" for TOP_1 testing

### P7-11: Add collaboration dependencies to AgentDependencies
- **BlockedBy**: P7-01
- **Files**: `src/dependencies.py`
- **Size**: S
- **Agent**: builder
- **Description**: Add TYPE_CHECKING imports and Optional fields for Phase 7 collaboration services.
- **Changes**:
  - Add TYPE_CHECKING block for Phase 7 imports (8 imports)
  - Add 8 Optional fields to AgentDependencies dataclass
  - Add comment block: `# Collaboration system (Phase 7 - initialized externally)`
- **Acceptance Criteria**:
  - All new imports under `if TYPE_CHECKING:` block
  - All new fields are `Optional["TypeName"] = None`
  - Existing `initialize()` method unchanged
  - `ruff check src/dependencies.py` passes
  - `mypy src/dependencies.py` passes
  - Existing tests still pass

---

## WAVE 3: Services Layer 1 (Independent Services)

### P7-12: Implement AgentRouter (baseline routing)
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/router.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement the baseline AgentRouter for skill-based routing. Used when `enable_agent_collaboration=True` but `enable_expert_gate=False`.
- **Contains**:
  - `AgentRouter` class with `__init__(self, db_session)`
  - `route(message, team_id, user_id, current_agent_slug)` -> RoutingDecision
  - @mention parsing via regex: `r"@(\w+)"`
  - Skill matching via keyword overlap (simple TF-IDF or keyword matching)
  - Default agent fallback when no match
  - `_parse_mentions(message)` -> list[str]
  - `_score_agent_skills(query, agent_skills)` -> float
- **Acceptance Criteria**:
  - @mention `@kyra` routes to agent with slug "kyra"
  - Skill matching returns highest-scoring agent
  - Falls back to default agent when no match above threshold
  - Returns RoutingDecision with agent_slug, confidence, reason
  - All methods have Google docstrings

### P7-13: Implement AgentDirectory (discovery)
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/discovery.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement agent discovery and capability registry.
- **Contains**:
  - `AgentDirectory` class with `__init__(self, db_session)`
  - `find_experts(required_skills, team_id, exclude_agent_ids)` -> list[AgentProfile]
  - `check_availability(agent_id)` -> AgentAvailability
  - `recommend(query, team_id, limit=3)` -> list[AgentRecommendation]
  - Skill coverage calculation: % of required skills that agent has
  - Load balancing: query active tasks count
- **Acceptance Criteria**:
  - Returns agents sorted by skill coverage, then availability
  - Excludes specified agent IDs
  - Availability check counts active tasks and conversations
  - `recommend()` returns top-3 by default

### P7-14: Implement HandoffManager
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/handoff.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement agent-to-agent conversation transfer.
- **Contains**:
  - `HandoffManager` class with `__init__(self, db_session)`
  - `initiate_handoff(from_agent_id, to_agent_slug, conversation_id, reason, context_summary)` -> HandoffResult
  - `return_to_previous(conversation_id)` -> HandoffResult
  - Creates `agent_handoff` record
  - Updates `conversation_participant` roles (from_agent becomes 'handoff_source', to_agent becomes 'primary')
  - Generates context summary for receiving agent
- **Acceptance Criteria**:
  - Creates handoff record with all fields
  - Updates participant roles correctly
  - `return_to_previous()` looks up last handoff and reverses
  - Returns HandoffResult with success flag, new_agent_slug, context

### P7-15: Implement multi-agent conversation management
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/multi_agent.py`
- **Size**: M
- **Agent**: builder
- **Description**: Manage multi-agent conversations where multiple agents participate.
- **Contains**:
  - `MultiAgentManager` class with `__init__(self, db_session)`
  - `add_agent(conversation_id, agent_id, role='invited')` -> ConversationParticipantORM
  - `remove_agent(conversation_id, agent_id)` -> None (sets left_at)
  - `get_participants(conversation_id, active_only=True)` -> list[ConversationParticipantORM]
  - `get_agent_conversations(agent_id, active_only=True)` -> list[UUID]
- **Acceptance Criteria**:
  - Adding agent creates conversation_participant record
  - Removing agent sets left_at timestamp (soft delete)
  - Active participants have left_at IS NULL
  - UniqueConstraint prevents duplicate (conversation_id, agent_id)

### P7-16: Implement TeamMemoryBus
- **BlockedBy**: P7-01
- **Files**: `src/collaboration/team_memory_bus.py`
- **Size**: S
- **Agent**: builder
- **Description**: Implement shared memory propagation across team agents.
- **Contains**:
  - `TeamMemoryBus` class with `__init__(self, hot_cache=None)`
  - `propagate_shared_memory(team_id, memory)` -> None
  - Invalidates hot cache for all agents in team
  - Shared memories have `agent_id=NULL` (team-wide)
- **Acceptance Criteria**:
  - `propagate_shared_memory()` invalidates hot cache if available
  - Gracefully handles missing hot_cache (no-op)
  - Structured logging: `f"team_memory_propagated: team_id={team_id}"`

### P7-17: Implement AgentMessageBus
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/message_bus.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement inter-agent messaging with Redis pub/sub and DB persistence.
- **Contains**:
  - `AgentMessageBus` class with `__init__(self, db_session, redis_client=None)`
  - `send(from_agent_id, to_agent_id, message_type, content, metadata, channel)` -> AgentMessage
  - `broadcast(from_agent_id, team_id, message_type, content)` -> list[AgentMessage]
  - `get_inbox(agent_id, unread_only=True, limit=10)` -> list[AgentMessage]
  - `mark_read(message_id)` -> None
  - Redis pub/sub publish on send (graceful degradation if Redis unavailable)
  - DB persistence for all messages
  - Channel validation: "direct", "team", "task:{uuid}", "collab:{uuid}"
- **Acceptance Criteria**:
  - Messages persisted to DB regardless of Redis availability
  - Redis publish on send (if available)
  - Inbox returns unread messages sorted by created_at DESC
  - Channel format validated
  - Broadcast sends to all active agents in team

### P7-18: Implement routing decision logging
- **BlockedBy**: P7-01, P7-06
- **Files**: `src/collaboration/routing_log.py`
- **Size**: S
- **Agent**: builder
- **Description**: Implement logging of routing decisions to the routing_decision_log table.
- **Contains**:
  - `RoutingLogger` class with `__init__(self, db_session)`
  - `log_decision(team_id, conversation_id, message_id, strategy, scores, selected_agents, ...)` -> RoutingDecisionLogORM
  - Records full ExpertScore JSONB, timing metrics, tier selection
  - `get_analytics(team_id, days=30)` -> dict with routing statistics
- **Acceptance Criteria**:
  - Creates routing_decision_log record with all fields
  - Scores stored as JSONB array of ExpertScore dicts
  - Latency tracked in milliseconds
  - Analytics returns top agents, average confidence, strategy distribution

---

## WAVE 4: Services Layer 2 + MoE

### P7-19: Implement ExpertGate (4-signal scoring)
- **BlockedBy**: P7-02, P7-06, P7-13
- **Files**: `src/moe/expert_gate.py`
- **Size**: L
- **Agent**: builder
- **Description**: Implement the MoE Expert Gate with 4-signal scoring for agent selection. Follow `complexity_scorer.py` patterns.
- **Contains**:
  - `ExpertGate` class with `__init__(self, db_session, embedding_service=None)`
  - `score_experts(query, team_id, context)` -> list[ExpertScore]
  - `_score_skill_match(query, agent)` -> float (TF-IDF + embedding similarity if available)
  - `_score_past_performance(query, agent_id, team_id)` -> float (avg feedback rating on similar queries)
  - `_score_personality_fit(query, agent)` -> float (tone/style heuristic)
  - `_score_load_balance(agent_id)` -> float (inverse of active load)
  - New agent default score: 0.7 (neutral)
  - Performance query: last 30 days, similarity > 0.8
- **Acceptance Criteria**:
  - Returns ExpertScore for each active agent in team
  - Scores sorted by overall (descending)
  - Skill match uses keyword overlap (embeddings optional)
  - Past performance defaults to 0.7 for new agents
  - Load balance penalizes high active_conversations_count
  - All methods have Google docstrings
  - < 100ms for team of 10 agents (without LLM calls)

### P7-20: Implement ExpertSelector (4 strategies)
- **BlockedBy**: P7-02
- **Files**: `src/moe/expert_selector.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement strategy-based agent selection from expert scores.
- **Contains**:
  - `ExpertSelector` class
  - `select(scores, strategy, k=3, confidence_threshold=0.6)` -> SelectionResult
  - TOP_1: Return highest scoring agent
  - TOP_K: Return top K agents (requires enable_ensemble_mode)
  - ENSEMBLE: Return all above threshold (requires enable_ensemble_mode)
  - CASCADE: Return ordered list for sequential try
  - Fallback: If best < threshold, use default agent + set fallback_used=True
- **Acceptance Criteria**:
  - All 4 strategies implemented correctly
  - Confidence threshold check on all strategies
  - Fallback to default agent when no expert meets threshold
  - SelectionResult includes selected_agents, strategy, confidence, fallback_used
  - TOP_K and ENSEMBLE disabled when enable_ensemble_mode=False (downgrade to TOP_1)

### P7-21: Implement TaskDelegator
- **BlockedBy**: P7-01, P7-06, P7-13, P7-17
- **Files**: `src/collaboration/task_delegator.py`
- **Size**: L
- **Agent**: builder
- **Description**: Implement the core task delegation system with safety constraints.
- **Contains**:
  - `TaskDelegator` class with `__init__(self, db_session, message_bus, celery_dispatch=True)`
  - `delegate(from_agent_id, to_agent_slug, task, parent_task_id=None)` -> AgentTask
  - `get_result(task_id, timeout_seconds=120)` -> AgentTask
  - `cancel(task_id, reason)` -> None
  - `_validate_depth(parent_task_id)` -> int (current depth)
  - `_detect_cycle(from_agent_id, parent_task_id)` -> bool
  - `_check_availability(agent_id)` -> bool
  - Custom exceptions: `DelegationDepthExceeded`, `CycleDetected`, `AgentUnavailable`, `BudgetExhausted`
  - Celery dispatch: `execute_agent_task.delay(str(task_id))`
  - Redis pub/sub wait for result (with polling fallback)
- **Acceptance Criteria**:
  - Creates agent_task record with status=pending
  - Depth validation walks parent chain (max 3)
  - Cycle detection: A->B->A fails immediately
  - Concurrent limit: 5 per agent
  - Dispatches via Celery (or mock in tests)
  - get_result waits with timeout
  - cancel updates status to CANCELLED
  - All 4 custom exceptions defined and raised

### P7-22: Implement ReportManager
- **BlockedBy**: P7-01, P7-21
- **Files**: `src/collaboration/report_manager.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement structured report requests between agents.
- **Contains**:
  - `ReportManager` class with `__init__(self, task_delegator)`
  - `request_report(from_agent_id, to_agent_slug, request)` -> AgentTask
  - `get_report(task_id)` -> Report
  - Converts ReportRequest to AgentTask with template-injected instructions
  - `REPORT_TEMPLATES` dict with CODE_REVIEW, RESEARCH_SUMMARY, RISK_ASSESSMENT templates
  - Report validation: checks required sections present
  - Model tier selection: "balanced" for simple reports, "powerful" for comprehensive
- **Acceptance Criteria**:
  - Converts ReportRequest to AgentTask correctly
  - Template sections injected into task instructions
  - get_report parses result into structured Report
  - Missing required sections raise validation error
  - All 3+ report types have templates defined

### P7-23: Update moe/__init__.py with Phase 7 exports
- **BlockedBy**: P7-02, P7-19, P7-20
- **Files**: `src/moe/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Update the MoE package init to export Phase 7 models and classes.
- **Acceptance Criteria**:
  - Updated docstring: "Mixture-of-Experts routing: model tier (Phase 2) + agent expert (Phase 7)."
  - Exports: ExpertGate, ExpertSelector, ExpertScore, SelectionStrategy, SelectionResult
  - Existing Phase 2 functionality unaffected

### P7-24: Implement collaboration __init__.py exports
- **BlockedBy**: P7-12, P7-13, P7-14, P7-15, P7-16, P7-17, P7-18
- **Files**: `src/collaboration/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Update collaboration package init with all module exports.
- **Acceptance Criteria**:
  - All collaboration classes importable via `from src.collaboration import AgentRouter` etc.
  - `__all__` list includes all public classes
  - `ruff check src/collaboration/__init__.py` passes

---

## WAVE 5: Services Layer 3 (High-Dependency Services)

### P7-25: Implement ResponseAggregator
- **BlockedBy**: P7-02, P7-19
- **Files**: `src/moe/response_aggregator.py`
- **Size**: M
- **Agent**: builder
- **Description**: Implement ENSEMBLE mode response synthesis from multiple experts.
- **Contains**:
  - `ResponseAggregator` class with `__init__(self, api_key, base_url, model=None)`
  - `aggregate(responses, query)` -> AggregatedResponse
  - Score each response on relevance (0-1)
  - Dedup overlapping content (simple text similarity or semantic > 0.9)
  - Merge complementary insights
  - Attribute sources: "According to {agent_name} ({role})..."
  - Uses Tier 1 model for synthesis (meta-model call)
  - Graceful degradation: if LLM unavailable, concatenate with attribution headers
- **Acceptance Criteria**:
  - Aggregates 2+ expert responses into single coherent response
  - Each expert's contribution attributed
  - Duplicate content deduplicated
  - Fallback to simple concatenation if LLM fails
  - Returns AggregatedResponse with synthesized text and per-expert attribution

### P7-26: Implement CollaborationOrchestrator
- **BlockedBy**: P7-01, P7-21, P7-17, P7-13
- **Files**: `src/collaboration/orchestrator.py`
- **Size**: L
- **Agent**: builder
- **Description**: Implement the multi-agent collaboration orchestrator supporting 5+ patterns.
- **Contains**:
  - `CollaborationOrchestrator` class with `__init__(self, db_session, task_delegator, message_bus, directory)`
  - `start(lead_agent_id, pattern, goal, context, participants)` -> CollaborationSession
  - `advance(session_id)` -> CollaborationSession
  - `synthesize(session_id)` -> str
  - `cancel(session_id, reason)` -> None
  - Pattern implementations:
    - SUPERVISOR_WORKER: parallel tasks, lead synthesizes
    - PIPELINE: sequential stages, output feeds next
    - PEER_REVIEW: worker->reviewer loop (max_rounds)
    - BRAINSTORM: parallel perspectives, lead synthesizes
    - CONSENSUS: independent assess, converge
    - DELEGATION: simple one-off (lightweight)
  - Cost tracking: accumulate from task costs, check cap
  - Duration tracking: check against max_duration_seconds
- **Acceptance Criteria**:
  - All 6 patterns implemented (including DELEGATION)
  - Session lifecycle: PLANNING -> ACTIVE -> SYNTHESIZING -> COMPLETED
  - Cost cap enforcement ($0.50 default)
  - Duration timeout enforcement (600s default)
  - advance() correctly transitions for each pattern
  - Creates collaboration_session and collaboration_participant_v2 records

### P7-27: Implement Celery task for agent execution
- **BlockedBy**: P7-21
- **Files**: `workers/tasks/collaboration.py`
- **Size**: M
- **Agent**: builder
- **Description**: Create Celery task that executes delegated agent tasks. Follow `workers/tasks/memory.py` patterns.
- **Contains**:
  - `execute_agent_task(task_id: str)` Celery task
  - Fresh DB session creation (pool_size=3)
  - Load agent context (identity, skills, memories)
  - Execute with timeout (soft_time_limit)
  - Token/cost tracking
  - Status updates: pending -> in_progress -> completed/failed
  - Redis publish on completion: `task:{task_id}` channel
  - Error handling with retry (max 2)
- **Acceptance Criteria**:
  - Task registered with Celery autodiscover
  - UUID string conversion to UUID inside task
  - Fresh session (not shared with FastAPI)
  - asyncio.run() bridge for async code
  - Status updates at each stage
  - Redis notification on completion
  - Error handling with retry and dead-letter

### P7-28: Implement collaboration API router
- **BlockedBy**: P7-12, P7-13, P7-14, P7-15, P7-21, P7-17
- **Files**: `src/api/routers/collaboration.py`
- **Size**: L
- **Agent**: builder
- **Description**: Create FastAPI router for all collaboration endpoints. Follow chat.py patterns.
- **Contains**:
  - `router = APIRouter(prefix="/v1", tags=["collaboration"])`
  - `POST /v1/conversations/{id}/handoff` - Initiate handoff
  - `POST /v1/conversations/{id}/agents` - Add/remove agents
  - `GET /v1/agents/recommend` - Agent discovery
  - `POST /v1/tasks/delegate` - Delegate task
  - `GET /v1/tasks/{id}` - Task status
  - `POST /v1/tasks/{id}/cancel` - Cancel task
  - `POST /v1/collaborations` - Start session
  - `GET /v1/collaborations/{id}` - Session status
  - `GET /v1/agents/{slug}/inbox` - Message inbox
  - `POST /v1/agents/{slug}/messages` - Send message
  - Request/Response Pydantic models (inline or in models.py)
  - Auth: `Depends(get_current_user)`, DB: `Depends(get_db)`
  - Feature flag checks on each endpoint
- **Acceptance Criteria**:
  - All 10 endpoints implemented
  - Auth required on all endpoints
  - Feature flag checks (return 403 if feature disabled)
  - Proper HTTP status codes (201 for creates, 200 for gets)
  - Request validation via Pydantic models
  - Google docstrings on all endpoints

### P7-29: Update api/routers/__init__.py with collaboration router
- **BlockedBy**: P7-28
- **Files**: `src/api/routers/__init__.py`
- **Size**: S
- **Agent**: builder
- **Description**: Add collaboration_router to the routers package.
- **Acceptance Criteria**:
  - `collaboration_router` importable from `src.api.routers`
  - Added to `__all__` list
  - `ruff check src/api/routers/__init__.py` passes

---

## WAVE 6: Tests Wave 1 (Foundation Tests)

### P7-30: Test collaboration models
- **BlockedBy**: P7-01
- **Files**: `tests/test_collaboration/test_models.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test all Pydantic models and Enums in collaboration/models.py.
- **Tests**: ~20 tests
  - Enum serialization (str values)
  - Model creation with valid data
  - Model validation (reject invalid data)
  - RoutingDecision defaults
  - AgentTask constraint fields (max_tokens, delegation_depth)
  - REPORT_TEMPLATES dict contents
- **Acceptance Criteria**:
  - All models tested for valid construction
  - All Enums tested for value membership
  - Invalid data raises ValidationError
  - All tests pass

### P7-31: Test MoE models
- **BlockedBy**: P7-02
- **Files**: `tests/test_collaboration/test_moe_models.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test MoE Pydantic models including ExpertScore weighted calculation.
- **Tests**: ~15 tests
  - ExpertScore creation with valid signals
  - ExpertScore.overall computed_field is correct weighted sum
  - ExpertScore WEIGHTS sum to 1.0
  - SelectionStrategy enum values
  - SelectionResult construction
  - ExpertResponse and AggregatedResponse models
  - Field validators (ge=0.0, le=1.0)
- **Acceptance Criteria**:
  - ExpertScore(skill_match=0.9, past_performance=0.8, personality_fit=0.8, load_balance=0.7).overall == 0.83 (within float tolerance)
  - Sum of WEIGHTS == 1.0
  - Field validation rejects values < 0 or > 1

### P7-32: Test AgentRouter
- **BlockedBy**: P7-12, P7-09
- **Files**: `tests/test_collaboration/test_agent_router.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test baseline routing: @mention parsing, skill matching, default fallback.
- **Tests**: ~12 tests
  - @mention parsing: `"@kyra help me"` -> agent_slug="kyra"
  - Multiple @mentions: uses first
  - No @mention: falls through to skill matching
  - Skill matching: agent with best skills wins
  - Default agent used when no match
  - Single-agent backward compatibility
  - Empty message handling
- **Acceptance Criteria**:
  - All routing strategies tested
  - Backward compatibility verified (no @mention, no collaboration)
  - RoutingDecision includes correct reason field

### P7-33: Test HandoffManager
- **BlockedBy**: P7-14, P7-09
- **Files**: `tests/test_collaboration/test_handoff.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test agent-to-agent handoff flow.
- **Tests**: ~10 tests
  - Successful handoff creates handoff record
  - Participant roles updated (source -> handoff_source, target -> primary)
  - Context summary included in handoff
  - return_to_previous finds last handoff and reverses
  - Handoff to nonexistent agent fails
  - Multiple handoffs create chain
- **Acceptance Criteria**:
  - DB calls verified (session.add, session.commit)
  - Participant role updates verified
  - return_to_previous tested

### P7-34: Test AgentDirectory
- **BlockedBy**: P7-13, P7-09
- **Files**: `tests/test_collaboration/test_agent_discovery.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test agent discovery and recommendation.
- **Tests**: ~10 tests
  - find_experts returns agents with matching skills
  - find_experts excludes specified agent IDs
  - Agents sorted by skill coverage
  - check_availability returns correct counts
  - recommend returns top-3 by default
  - Empty team returns empty list
- **Acceptance Criteria**:
  - Skill coverage calculation correct
  - Exclusion list works
  - Availability reflects active task count

---

## WAVE 7: Tests Wave 2 (All Remaining Service Tests)

### P7-35: Test ExpertGate
- **BlockedBy**: P7-19, P7-09, P7-10
- **Files**: `tests/test_collaboration/test_expert_gate.py`
- **Size**: L
- **Agent**: builder
- **Description**: Test 4-signal scoring system.
- **Tests**: ~15 tests
  - score_experts returns scores for all active agents
  - Skill match signal correct (keyword matching)
  - Past performance defaults to 0.7 for new agents
  - Load balance penalizes high-load agents
  - Overall score is correct weighted sum
  - Scores sorted by overall descending
  - Empty team returns empty list
  - Performance query uses last 30 days
- **Acceptance Criteria**:
  - Each signal tested independently
  - Weighted sum verified mathematically
  - New agent default (0.7) verified
  - Sorted order verified

### P7-36: Test ExpertSelector
- **BlockedBy**: P7-20, P7-09, P7-10
- **Files**: `tests/test_collaboration/test_expert_selector.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test all 4 selection strategies.
- **Tests**: ~12 tests
  - TOP_1 selects highest scoring agent
  - TOP_1 falls back when best < threshold
  - TOP_K returns K agents
  - ENSEMBLE returns all above threshold
  - ENSEMBLE falls back when none above threshold
  - CASCADE returns ordered list
  - Confidence threshold enforced
  - fallback_used flag set correctly
  - Empty scores list handled
- **Acceptance Criteria**:
  - All 4 strategies tested with known inputs
  - Fallback behavior verified
  - SelectionResult fields verified

### P7-37: Test ResponseAggregator
- **BlockedBy**: P7-25, P7-09
- **Files**: `tests/test_collaboration/test_response_aggregator.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test ENSEMBLE response synthesis.
- **Tests**: ~8 tests
  - Aggregates 2+ responses into single text
  - Attributes sources ("According to Luke...")
  - Handles single response (pass-through)
  - Handles LLM failure (concatenation fallback)
  - Dedup detection (similar content merged)
- **Acceptance Criteria**:
  - Attribution present in output
  - Fallback works when LLM mocked to fail
  - AggregatedResponse has all fields

### P7-38: Test TaskDelegator
- **BlockedBy**: P7-21, P7-09
- **Files**: `tests/test_collaboration/test_task_delegator.py`
- **Size**: L
- **Agent**: builder
- **Description**: Test task delegation lifecycle with safety constraints.
- **Tests**: ~18 tests
  - delegate creates task record (status=pending)
  - Depth validation: depth=3 succeeds, depth=4 raises DelegationDepthExceeded
  - Cycle detection: A->B->A raises CycleDetected
  - Concurrent limit: 6th task raises error
  - Task timeout: marks TIMED_OUT after timeout
  - get_result waits and returns completed task
  - cancel marks CANCELLED
  - Dead-letter after 2 retries
  - Celery dispatch called with string UUID
  - Budget check integration
- **Acceptance Criteria**:
  - All 4 custom exceptions tested
  - Depth chain traversal verified
  - Cycle detection verified
  - Celery mock verified (delay called with str)
  - Status transitions verified

### P7-39: Test AgentMessageBus
- **BlockedBy**: P7-17, P7-09
- **Files**: `tests/test_collaboration/test_agent_message_bus.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test inter-agent messaging.
- **Tests**: ~12 tests
  - send creates message record
  - send publishes to Redis (if available)
  - send works without Redis (graceful degradation)
  - broadcast sends to all active agents
  - get_inbox returns unread only
  - get_inbox sorted by created_at DESC
  - mark_read updates read_at timestamp
  - Channel validation (valid and invalid)
  - All message types tested
- **Acceptance Criteria**:
  - DB persistence verified
  - Redis publish verified (mocked)
  - Graceful degradation without Redis
  - Channel format validation

### P7-40: Test ReportManager
- **BlockedBy**: P7-22, P7-09
- **Files**: `tests/test_collaboration/test_report_manager.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test structured report system.
- **Tests**: ~10 tests
  - request_report converts to AgentTask
  - Template sections injected into instructions
  - get_report parses result into Report
  - Missing required sections fail validation
  - All report types have templates
  - Model tier selection based on complexity
- **Acceptance Criteria**:
  - Task creation verified with correct template
  - Report parsing verified
  - Validation of required sections tested

### P7-41: Test RoutingLogger
- **BlockedBy**: P7-18, P7-09
- **Files**: `tests/test_collaboration/test_routing_log.py`
- **Size**: S
- **Agent**: builder
- **Description**: Test routing decision logging.
- **Tests**: ~6 tests
  - log_decision creates record with all fields
  - Scores stored as JSONB
  - Latency fields recorded
  - get_analytics returns statistics
- **Acceptance Criteria**:
  - All fields persisted correctly
  - JSONB serialization verified
  - Analytics query returns expected shape

---

## WAVE 8: Integration Tasks

### P7-42: Integrate routing into chat.py
- **BlockedBy**: P7-12, P7-19, P7-20, P7-18, P7-05
- **Files**: `src/api/routers/chat.py`
- **Size**: M
- **Agent**: builder
- **Description**: Inject agent routing logic into the chat endpoint. This is the highest-risk integration point.
- **Changes**:
  - Add helper function `_route_to_agent()` that checks feature flags and routes
  - Feature flag cascade: direct dispatch -> AgentRouter -> ExpertGate
  - Log routing decisions via RoutingLogger
  - Pass routing result to existing agent resolution logic
  - Maintain backward compatibility: when all flags off, behavior unchanged
- **Acceptance Criteria**:
  - With all flags off: exact same behavior as before
  - With enable_agent_collaboration=True: uses AgentRouter
  - With enable_expert_gate=True: uses ExpertGate
  - Routing decision logged
  - No regression in existing chat tests
  - `ruff check src/api/routers/chat.py` passes

### P7-43: Register collaboration router in app.py
- **BlockedBy**: P7-28, P7-29
- **Files**: `src/api/app.py`
- **Size**: S
- **Agent**: builder
- **Description**: Add collaboration_router to the FastAPI app.
- **Changes**:
  - Import collaboration_router from src.api.routers
  - Add `app.include_router(collaboration_router)` in create_app()
- **Acceptance Criteria**:
  - Router registered and endpoints accessible
  - Existing routers unaffected
  - `ruff check src/api/app.py` passes

### P7-44: Test multi-agent conversations
- **BlockedBy**: P7-15, P7-09
- **Files**: `tests/test_collaboration/test_multi_agent.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test multi-agent conversation management.
- **Tests**: ~10 tests
  - Add agent to conversation
  - Remove agent (soft delete)
  - Get active participants
  - Duplicate add fails (unique constraint)
  - Removed agents not in active list
  - Get agent's active conversations
- **Acceptance Criteria**:
  - All CRUD operations tested
  - Soft delete verified
  - Unique constraint tested

### P7-45: Test TeamMemoryBus
- **BlockedBy**: P7-16, P7-09
- **Files**: `tests/test_collaboration/test_team_memory_bus.py`
- **Size**: S
- **Agent**: builder
- **Description**: Test shared memory propagation.
- **Tests**: ~5 tests
  - Propagation invalidates hot cache
  - Graceful when hot_cache is None
  - Structured logging verified
- **Acceptance Criteria**:
  - Hot cache invalidation verified (mock)
  - No-op when cache unavailable

### P7-46: Test CollaborationOrchestrator
- **BlockedBy**: P7-26, P7-09
- **Files**: `tests/test_collaboration/test_collaboration_orchestrator.py`
- **Size**: L
- **Agent**: builder
- **Description**: Test all 6 collaboration patterns.
- **Tests**: ~20 tests
  - SUPERVISOR_WORKER: parallel tasks, synthesis
  - PIPELINE: sequential stages
  - PEER_REVIEW: worker->reviewer loop
  - BRAINSTORM: parallel perspectives
  - CONSENSUS: independent assess, converge
  - DELEGATION: simple one-off
  - Cost cap enforcement
  - Duration timeout enforcement
  - advance() for each pattern
  - synthesize() combines outputs
  - cancel() terminates session
  - Invalid participant fails validation
- **Acceptance Criteria**:
  - All 6 patterns have at least 2 tests each
  - Cost cap tested (over limit -> FAILED)
  - Duration timeout tested
  - Session lifecycle verified for each pattern

### P7-47: Test Celery collaboration task
- **BlockedBy**: P7-27, P7-09
- **Files**: `tests/test_workers/test_collaboration_tasks.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test Celery task for agent execution.
- **Tests**: ~8 tests
  - Task picks up pending task and executes
  - Status transitions: pending -> in_progress -> completed
  - Timeout marks task as TIMED_OUT
  - Error handling: failed task -> status=FAILED
  - Retry logic (max 2)
  - Redis notification on completion
  - Token/cost tracking updated
- **Acceptance Criteria**:
  - All status transitions tested
  - Timeout enforced
  - Retry logic verified
  - Redis publish verified (mock)

---

## WAVE 9: Integration Tests

### P7-48: Test collaboration API router
- **BlockedBy**: P7-28, P7-09
- **Files**: `tests/test_api/test_collaboration_router.py`
- **Size**: L
- **Agent**: builder
- **Description**: Test all collaboration API endpoints.
- **Tests**: ~15 tests
  - POST handoff: creates handoff, returns result
  - POST add/remove agents: modifies participants
  - GET recommend: returns top agents
  - POST delegate: creates task
  - GET task status: returns task
  - POST cancel task: marks cancelled
  - POST start collaboration: creates session
  - GET collaboration status: returns session
  - GET inbox: returns messages
  - POST send message: creates message
  - Auth required on all endpoints
  - Feature flag disabled -> 403
- **Acceptance Criteria**:
  - All 10 endpoints tested
  - Auth enforcement verified
  - Feature flag checks verified
  - Correct HTTP status codes

### P7-49: Test chat.py routing integration
- **BlockedBy**: P7-42, P7-09
- **Files**: `tests/test_api/test_chat_routing.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test the routing integration in chat.py.
- **Tests**: ~10 tests
  - Flags off: direct dispatch (no routing)
  - enable_agent_collaboration: uses AgentRouter
  - enable_expert_gate: uses ExpertGate
  - @mention routing in chat
  - Routing decision logged
  - Routing failure falls back to default
  - Existing chat tests still pass
- **Acceptance Criteria**:
  - Feature flag cascade verified
  - No regression in existing chat behavior
  - Routing log created on each routed chat

### P7-50: Test ORM models
- **BlockedBy**: P7-06, P7-09
- **Files**: `tests/test_collaboration/test_orm_models.py`
- **Size**: M
- **Agent**: builder
- **Description**: Test ORM model creation and constraints.
- **Tests**: ~10 tests
  - Each ORM model can be instantiated
  - UniqueConstraints tested
  - CheckConstraints tested (delegation_depth, no self-delegation)
  - ForeignKey relationships exist
  - JSONB fields accept dict data
  - TimestampMixin fields have defaults
- **Acceptance Criteria**:
  - All 7 ORM models tested
  - Constraint violations raise IntegrityError (mocked or actual)

### P7-51: Test migration 004 structure
- **BlockedBy**: P7-07
- **Files**: `tests/test_collaboration/test_migration.py`
- **Size**: S
- **Agent**: builder
- **Description**: Test that migration 004 has correct structure (revision, down_revision, operations).
- **Tests**: ~5 tests
  - revision == "004"
  - down_revision == "003"
  - upgrade() creates 7 tables
  - downgrade() drops 7 tables
  - Enum type created/dropped
- **Acceptance Criteria**:
  - Migration metadata correct
  - Operation count verified

### P7-52: Test db/models/__init__.py exports
- **BlockedBy**: P7-08
- **Files**: `tests/test_collaboration/test_model_exports.py`
- **Size**: S
- **Agent**: builder
- **Description**: Verify all Phase 7 ORM models are importable from src.db.models.
- **Tests**: ~3 tests
  - All 7 models in __all__
  - All 7 models importable
  - No import errors
- **Acceptance Criteria**:
  - `from src.db.models import ConversationParticipantORM` works for all 7

---

## WAVE 10: Cross-Service Smoke Tests

### P7-53: End-to-end routing smoke test
- **BlockedBy**: P7-49
- **Files**: `tests/test_collaboration/test_routing_e2e.py`
- **Size**: M
- **Agent**: builder
- **Description**: End-to-end test: message -> routing -> agent selection -> log.
- **Tests**: ~5 tests
  - Full routing flow with mocked services
  - ExpertGate -> ExpertSelector -> RoutingLogger chain
  - ENSEMBLE mode: parallel responses -> aggregation
  - Feature flag progression (each level tested)
- **Acceptance Criteria**:
  - Full chain executes without error
  - Each component called in correct order
  - Final result has expected shape

### P7-54: End-to-end delegation smoke test
- **BlockedBy**: P7-46, P7-47
- **Files**: `tests/test_collaboration/test_delegation_e2e.py`
- **Size**: M
- **Agent**: builder
- **Description**: End-to-end test: delegate -> Celery execute -> result.
- **Tests**: ~5 tests
  - Full delegation flow with mocked Celery
  - Sub-delegation chain (depth 2)
  - Cycle detection in chain
  - Timeout handling
- **Acceptance Criteria**:
  - Full delegation lifecycle verified
  - Sub-delegation creates correct parent chain

### P7-55: End-to-end collaboration smoke test
- **BlockedBy**: P7-46
- **Files**: `tests/test_collaboration/test_collaboration_e2e.py`
- **Size**: M
- **Agent**: builder
- **Description**: End-to-end test: start session -> execute pattern -> synthesize.
- **Tests**: ~5 tests
  - SUPERVISOR_WORKER full flow
  - PIPELINE full flow
  - Cost cap triggering during session
  - Session status transitions
- **Acceptance Criteria**:
  - Full session lifecycle for 2 patterns
  - Cost tracking verified
  - Final output produced

### P7-56: Backward compatibility smoke test
- **BlockedBy**: P7-42, P7-43
- **Files**: `tests/test_collaboration/test_backward_compat.py`
- **Size**: S
- **Agent**: builder
- **Description**: Verify that ALL existing functionality works unchanged with Phase 7 flags off.
- **Tests**: ~5 tests
  - All feature flags off: chat works as before
  - Settings loads without errors
  - AgentDependencies initializes without collaboration services
  - CLI startup unaffected
  - Existing API endpoints unaffected
- **Acceptance Criteria**:
  - No regression with default (all off) flags
  - Dependencies dataclass works with all None collaboration fields

---

## WAVE 11: Final Validation

### P7-57: Run full test suite
- **BlockedBy**: P7-53, P7-54, P7-55, P7-56
- **Files**: None (validation only)
- **Size**: M
- **Agent**: tester
- **Description**: Run the complete test suite to verify no regressions.
- **Commands**:
  - `.venv/bin/python -m pytest tests/ -v`
  - Expected: ~935 existing + ~180 new = ~1115 tests, all passing
- **Acceptance Criteria**:
  - ALL tests pass (0 failures)
  - No new warnings
  - Test count increased by ~180

### P7-58: Run lint and type checks
- **BlockedBy**: P7-57
- **Files**: None (validation only)
- **Size**: S
- **Agent**: tester
- **Description**: Run lint and type checking on all new and modified code.
- **Commands**:
  - `ruff check src/ tests/`
  - `ruff format --check src/ tests/`
  - `mypy src/`
- **Acceptance Criteria**:
  - Zero ruff errors
  - Zero ruff format violations
  - mypy passes (or only pre-existing issues)

---

## Critical Path

```
P7-01 -> P7-06 -> P7-19 -> P7-25/P7-20 -> P7-42 -> P7-49 -> P7-53 -> P7-57 -> P7-58
  |         |        |
  |         +-> P7-07 (migration)
  |         +-> P7-21 -> P7-26 -> P7-46 -> P7-55 -> P7-57
  |                |
  |                +-> P7-27 -> P7-47
  |
  +-> P7-12 -> P7-32
  +-> P7-13 -> P7-34
  +-> P7-14 -> P7-33
```

**Longest path**: P7-01 -> P7-06 -> P7-21 -> P7-26 -> P7-46 -> P7-55 -> P7-57 -> P7-58 (depth 8)

## Parallelism Summary

| Wave | Concurrent Tasks | Focus |
|------|-----------------|-------|
| 1 | 5 agents | Models, types, package init, feature flags |
| 2 | 6 agents | ORM, migration, conftest, dependencies |
| 3 | 7 agents | Independent services (highest parallelism) |
| 4 | 6 agents | Dependent services + MoE |
| 5 | 5 agents | Orchestrator, aggregator, Celery, API router |
| 6 | 5 agents | Foundation tests |
| 7 | 7 agents | Remaining service tests |
| 8 | 6 agents | Integration modifications |
| 9 | 5 agents | Integration tests |
| 10 | 4 agents | E2E smoke tests |
| 11 | 2 agents | Final validation |

**Maximum parallelism**: 7 (Waves 3 and 7)
**Total new files**: ~30
**Total modified files**: ~7
**Estimated new test count**: ~180 tests
**Estimated new LOC**: ~5,000-6,000
