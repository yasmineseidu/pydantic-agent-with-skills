# Phase 7: Agent Collaboration - ATOMIC Task Breakdown (REVISED)

> **Revision Date**: 2026-02-10
> **Status**: CRITICAL REVIEW - Further Atomization Required
> **Original**: 58 tasks | **Revised**: 78 tasks
> **Constraint**: NO CONTEXT WINDOW FILL - When in doubt, break it down further

---

## Executive Summary

The original 58-task breakdown has been revised to **78 atomic tasks** with deeper decomposition of high-risk, large modules. Key changes:

1. **collaboration/models.py** split into **3 tasks** (Enums, Core Models, Collaboration Models)
2. **7 ORM models** split into **3 tasks** (Routing, Tasks/Messages, Collaboration)
3. **ExpertGate** split into **2 tasks** (4-signal scoring, integration)
4. **TaskDelegator** split into **2 tasks** (core delegation, safety constraints)
5. **CollaborationOrchestrator** split into **4 tasks** (4 patterns + orchestration logic)
6. **API Router** split into **3 tasks** (routing endpoints, task endpoints, collab endpoints)
7. **Tests for large modules** split proportionally

**Result**: Maximum task size reduced from "L" (~400 LOC) to "M" (~200 LOC), ensuring NO task will fill context window even with extensive testing.

---

## Task Size Guidelines (REVISED)

| Size | Implementation LOC | Test LOC | Total LOC | Context Risk |
|------|-------------------|----------|-----------|--------------|
| **S** (Small) | 50-100 | 20-50 | 70-150 | ✅ None |
| **M** (Medium) | 100-200 | 50-100 | 150-300 | ✅ Low |
| **L** (Large) | ❌ ELIMINATED | ❌ ELIMINATED | ❌ TOO RISKY | ❌ HIGH |

**All tasks are now S or M size** to guarantee context window safety.

---

## WAVE 1: Foundation (Zero Dependencies) - 7 tasks

### P7-01A: Create collaboration Enums
- **Files**: `src/collaboration/models.py` (partial - Enums only)
- **Size**: S (~80 LOC)
- **Agent**: builder
- **Description**: Create ALL Enums for collaboration system. This is Phase 1 of models.py.
- **Contains**:
  - `ParticipantRole` (primary, invited, handoff_source)
  - `AgentTaskType` (research, review, analyze, generate, summarize, validate, plan, execute)
  - `AgentTaskStatus` (pending, in_progress, completed, failed, cancelled, timed_out)
  - `TaskPriority` (low, normal, high, urgent)
  - `AgentMessageType` (task_request, task_result, task_status, info_request, info_response, notification, collab_invite, collab_update, handoff_request, feedback)
  - `CollaborationPattern` (supervisor_worker, pipeline, peer_review, brainstorm, consensus, delegation)
  - `CollaborationStatus` (planning, active, synthesizing, completed, failed, timed_out, cancelled)
  - `ReportType` (code_review, security_audit, research_summary, data_analysis, risk_assessment, performance_report, comparison, action_plan)
- **Acceptance Criteria**:
  - All 8 Enums use `str, Enum` base
  - All have docstrings
  - `ruff check src/collaboration/models.py` passes
  - `mypy src/collaboration/models.py` passes

### P7-01B: Create collaboration core Pydantic models
- **BlockedBy**: P7-01A
- **Files**: `src/collaboration/models.py` (add core models)
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: Create core Pydantic models for routing and agents. This is Phase 2 of models.py.
- **Contains**:
  - `RoutingDecision` (agent_slug, confidence, reason)
  - `HandoffResult` (success, new_agent_slug, context)
  - `AgentRecommendation` (slug, name, confidence, matching_skills, tagline, personality_preview)
  - `AgentProfile` (agent_id, slug, name, tagline, effective_skills, active_tasks, status, skill_coverage)
  - `AgentAvailability` (available, active_tasks, active_conversations, estimated_wait_seconds, reason)
  - `AgentTaskCreate` (model for task creation request)
  - `AgentTask` (full model with all fields)
  - `AgentMessage` (message model)
  - Constants: `MAX_DELEGATION_DEPTH=3`, `MAX_CONCURRENT_TASKS=5`
- **Acceptance Criteria**:
  - All models have Google docstrings
  - All fields have type annotations + Field() validators
  - Models build on Enums from P7-01A
  - `ruff & mypy` pass

### P7-01C: Create collaboration session Pydantic models
- **BlockedBy**: P7-01A, P7-01B
- **Files**: `src/collaboration/models.py` (add session models + templates)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Create collaboration session and report models. This is Phase 3 of models.py.
- **Contains**:
  - `ReportRequest` (report_type, title, parameters, max_sections, format)
  - `ReportTemplate` (report_type, required_sections, optional_sections, output_schema)
  - `Report` (parsed report with sections)
  - `CollaborationParticipantInfo` (agent_id, slug, role, stage, task_id, status)
  - `StageOutput` (stage, agent_slug, output, tokens_used, cost_usd, duration_seconds)
  - `CollaborationSession` (full session model with all fields)
  - `ParticipantConfig` (config for starting sessions)
  - `REPORT_TEMPLATES` dict with CODE_REVIEW, RESEARCH_SUMMARY, RISK_ASSESSMENT templates
- **Acceptance Criteria**:
  - All session models complete
  - REPORT_TEMPLATES has 3+ templates
  - Models reference Enums correctly
  - `ruff & mypy` pass
  - **File complete** (all 3 phases merged)

### P7-02: Create MoE Pydantic models
- **Files**: `src/moe/models.py`
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Create Pydantic models for MoE expert routing layer. Follow `model_tier.py` patterns.
- **Contains**:
  - `SelectionStrategy` enum (TOP_1, TOP_K, ENSEMBLE, CASCADE)
  - `ExpertScore` (4 signals + WEIGHTS ClassVar + @computed_field overall)
  - `SelectionResult` (selected_agents, strategy, confidence, fallback_used)
  - `ExpertResponse` (agent_slug, response, relevance_score)
  - `AggregatedResponse` (synthesized_text, per_expert_attribution, sources)
- **Acceptance Criteria**:
  - ExpertScore.WEIGHTS = {skill_match: 0.40, past_performance: 0.25, personality_fit: 0.20, load_balance: 0.15}
  - Sum of WEIGHTS == 1.0
  - `overall` uses `@computed_field @property` returning weighted sum
  - All signal fields have `Field(ge=0.0, le=1.0)`
  - `ruff & mypy` pass

### P7-03: Create collaboration package __init__.py
- **Files**: `src/collaboration/__init__.py`
- **Size**: S (~10 LOC)
- **Agent**: builder
- **Description**: Create package init with docstring and placeholder for exports.
- **Acceptance Criteria**:
  - Module docstring: `"""Agent collaboration, routing, and multi-agent orchestration."""`
  - Empty `__all__` list (populated in Wave 9)

### P7-04: Create test_collaboration package __init__.py
- **Files**: `tests/test_collaboration/__init__.py`
- **Size**: S (~5 LOC)
- **Agent**: builder
- **Description**: Create test package init.
- **Acceptance Criteria**:
  - Docstring: `"""Tests for agent collaboration system."""`

### P7-05: Add feature flags to settings.py
- **Files**: `src/settings.py`
- **Size**: S (~20 LOC)
- **Agent**: builder
- **Description**: Add 4 new feature flags to FeatureFlags class.
- **Changes**:
  - `enable_expert_gate: bool = Field(default=False, description="Phase 7: MoE 4-signal scoring")`
  - `enable_ensemble_mode: bool = Field(default=False, description="Phase 7: Multi-expert responses")`
  - `enable_task_delegation: bool = Field(default=False, description="Phase 7: AgentTask system")`
  - `enable_collaboration: bool = Field(default=False, description="Phase 7: Full collaboration sessions")`
- **Acceptance Criteria**:
  - All default to False
  - Settings loads without errors
  - `ruff & mypy` pass
  - Existing tests pass

---

## WAVE 2: Database Layer - 8 tasks

### P7-06A: Create routing/handoff ORM models
- **BlockedBy**: P7-01A, P7-01B
- **Files**: `src/db/models/collaboration.py` (partial - 3 models)
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: Create ORM models for routing and handoff tables. Follow `src/db/models/agent.py` patterns.
- **Contains**:
  - `ConversationParticipantORM` (conversation_participant table)
  - `AgentHandoffORM` (agent_handoff table)
  - `RoutingDecisionLogORM` (routing_decision_log table)
- **Acceptance Criteria**:
  - All inherit Base, UUIDMixin, TimestampMixin
  - JSONB columns use postgresql.JSONB()
  - UniqueConstraint on (conversation_id, agent_id) for ConversationParticipant
  - GIN index on scores JSONB
  - `ruff & mypy` pass

### P7-06B: Create task/message ORM models
- **BlockedBy**: P7-01A, P7-01B
- **Files**: `src/db/models/collaboration.py` (add 2 models)
- **Size**: M (~180 LOC)
- **Agent**: builder
- **Description**: Create ORM models for task delegation and messaging.
- **Contains**:
  - `AgentTaskORM` (agent_task table) - with CheckConstraints
  - `AgentMessageORM` (agent_message table) - metadata mapped as metadata_json
- **Acceptance Criteria**:
  - CheckConstraint: `delegation_depth <= 3`
  - CheckConstraint: `created_by_agent_id != assigned_to_agent_id`
  - metadata column mapped as metadata_json (SA reserved word)
  - Partial index on agent_message (to_agent_id, read_at) WHERE read_at IS NULL
  - `ruff & mypy` pass

### P7-06C: Create collaboration session ORM models
- **BlockedBy**: P7-01A, P7-01C
- **Files**: `src/db/models/collaboration.py` (add 2 models)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Create ORM models for collaboration sessions.
- **Contains**:
  - `CollaborationSessionORM` (collaboration_session table)
  - `CollaborationParticipantV2ORM` (collaboration_participant_v2 table)
- **Acceptance Criteria**:
  - UniqueConstraint on (session_id, agent_id)
  - JSONB fields for stage_outputs
  - Cost and duration tracking fields
  - `ruff & mypy` pass
  - **File complete** (all 7 ORM models present)

### P7-07: Create Alembic migration 004
- **BlockedBy**: P7-06A, P7-06B, P7-06C
- **Files**: `src/db/migrations/versions/004_phase7_collaboration.py`
- **Size**: M (~250 LOC)
- **Agent**: builder
- **Description**: Create migration 004 with all 7 tables, 1 enum, ~20 indexes. Follow migration 003 pattern.
- **IMPORTANT**: Do NOT add agent_id to message table (already exists).
- **Contains**:
  - upgrade(): Create participant_role enum, 7 tables, ~20 indexes, 7 triggers
  - downgrade(): Drop all 7 tables, drop enum
  - revision="004", down_revision="003"
- **Acceptance Criteria**:
  - Enum created before tables
  - Tables created in dependency order
  - All indexes created (GIN on JSONB, partial on nullable FKs)
  - Triggers use existing trigger_set_updated_at()
  - downgrade drops in reverse order

### P7-08: Update db/models/__init__.py exports
- **BlockedBy**: P7-06A, P7-06B, P7-06C
- **Files**: `src/db/models/__init__.py`
- **Size**: S (~20 LOC)
- **Agent**: builder
- **Description**: Add imports and __all__ for 7 new ORM models.
- **Acceptance Criteria**:
  - All 7 models importable
  - Existing imports unchanged
  - `ruff` passes

### P7-09: Create test_collaboration/conftest.py
- **BlockedBy**: P7-01A, P7-01B, P7-01C, P7-02
- **Files**: `tests/test_collaboration/conftest.py`
- **Size**: M (~180 LOC)
- **Agent**: builder
- **Description**: Create shared test fixtures for all collaboration tests.
- **Contains**:
  - `mock_agent_orm()` - AgentORM with skills/personality
  - `mock_team_agents()` - List of 3-5 agents with varied skills
  - `mock_routing_decision()` - RoutingDecision instance
  - `mock_expert_scores()` - List of ExpertScore with varied values
  - `mock_db_session()` - AsyncMock with execute/commit/rollback/add/flush/refresh
  - `mock_redis_client()` - AsyncMock with publish/subscribe/get/set
  - `mock_embedding_service()` - AsyncMock returning test embeddings
  - `collaboration_settings()` - Settings with all Phase 7 flags enabled
  - `mock_celery_task()` - MagicMock for Celery dispatch
- **Acceptance Criteria**:
  - All fixtures use @pytest.fixture
  - AsyncMock for async ops
  - At least 3 agents with different skills
  - Settings has all 5 flags = True

### P7-10: Create MoE test conftest additions
- **BlockedBy**: P7-02
- **Files**: `tests/test_collaboration/conftest_moe.py`
- **Size**: S (~60 LOC)
- **Agent**: builder
- **Description**: Create MoE-specific test fixtures.
- **Contains**:
  - `sample_expert_scores()` - 5 ExpertScore with known values
  - `high_confidence_scores()` - All above 0.6
  - `low_confidence_scores()` - All below 0.6
  - `mixed_confidence_scores()` - Mixed
- **Acceptance Criteria**:
  - Scores mathematically correct (overall = weighted sum)
  - At least one clear winner for TOP_1

### P7-11: Add collaboration deps to AgentDependencies
- **BlockedBy**: P7-01A, P7-01B, P7-01C
- **Files**: `src/dependencies.py`
- **Size**: S (~40 LOC)
- **Agent**: builder
- **Description**: Add TYPE_CHECKING imports and Optional fields for Phase 7.
- **Changes**:
  - TYPE_CHECKING block with 8 imports
  - Comment: `# Collaboration system (Phase 7 - initialized externally)`
  - 8 Optional fields (router, expert_gate, selector, aggregator, directory, handoff, multi_agent, delegator)
- **Acceptance Criteria**:
  - All imports under TYPE_CHECKING
  - All fields Optional with default None
  - `initialize()` unchanged
  - `ruff & mypy` pass

---

## WAVE 3: Services Layer 1 (Independent) - 7 tasks

### P7-12: Implement AgentRouter (baseline)
- **BlockedBy**: P7-01A, P7-01B, P7-06A
- **Files**: `src/collaboration/router.py`
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: Baseline AgentRouter for skill-based routing.
- **Contains**:
  - `AgentRouter.__init__(db_session)`
  - `route(message, team_id, user_id, current_agent_slug)` -> RoutingDecision
  - `_parse_mentions(message)` -> list[str] (regex `r"@(\w+)"`)
  - `_score_agent_skills(query, agent_skills)` -> float (keyword matching)
- **Acceptance Criteria**:
  - @mention routing works
  - Skill matching returns highest score
  - Default fallback when no match
  - Returns RoutingDecision
  - Google docstrings

### P7-13: Implement AgentDirectory
- **BlockedBy**: P7-01A, P7-01B, P7-06A
- **Files**: `src/collaboration/discovery.py`
- **Size**: M (~130 LOC)
- **Agent**: builder
- **Description**: Agent discovery and capability registry.
- **Contains**:
  - `AgentDirectory.__init__(db_session)`
  - `find_experts(required_skills, team_id, exclude_agent_ids)` -> list[AgentProfile]
  - `check_availability(agent_id)` -> AgentAvailability
  - `recommend(query, team_id, limit=3)` -> list[AgentRecommendation]
- **Acceptance Criteria**:
  - Returns agents sorted by skill coverage + availability
  - Excludes specified IDs
  - Availability counts active tasks
  - recommend() returns top-3

### P7-14: Implement HandoffManager
- **BlockedBy**: P7-01A, P7-01B, P7-06A
- **Files**: `src/collaboration/handoff.py`
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Agent-to-agent conversation transfer.
- **Contains**:
  - `HandoffManager.__init__(db_session)`
  - `initiate_handoff(...)` -> HandoffResult
  - `return_to_previous(conversation_id)` -> HandoffResult
- **Acceptance Criteria**:
  - Creates agent_handoff record
  - Updates participant roles
  - return_to_previous reverses last handoff
  - Returns HandoffResult

### P7-15: Implement MultiAgentManager
- **BlockedBy**: P7-01A, P7-01B, P7-06A
- **Files**: `src/collaboration/multi_agent.py`
- **Size**: M (~100 LOC)
- **Agent**: builder
- **Description**: Multi-agent conversation management.
- **Contains**:
  - `MultiAgentManager.__init__(db_session)`
  - `add_agent(conversation_id, agent_id, role)` -> ConversationParticipantORM
  - `remove_agent(conversation_id, agent_id)` -> None (sets left_at)
  - `get_participants(conversation_id, active_only)` -> list[ConversationParticipantORM]
  - `get_agent_conversations(agent_id, active_only)` -> list[UUID]
- **Acceptance Criteria**:
  - Adding creates record
  - Removing sets left_at (soft delete)
  - Active check uses left_at IS NULL
  - UniqueConstraint prevents duplicates

### P7-16: Implement TeamMemoryBus
- **BlockedBy**: P7-01A, P7-01B
- **Files**: `src/collaboration/team_memory_bus.py`
- **Size**: S (~60 LOC)
- **Agent**: builder
- **Description**: Shared memory propagation.
- **Contains**:
  - `TeamMemoryBus.__init__(hot_cache=None)`
  - `propagate_shared_memory(team_id, memory)` -> None
- **Acceptance Criteria**:
  - Invalidates hot cache if available
  - Graceful when hot_cache is None
  - Structured logging

### P7-17: Implement AgentMessageBus
- **BlockedBy**: P7-01A, P7-01B, P7-06B
- **Files**: `src/collaboration/message_bus.py`
- **Size**: M (~180 LOC)
- **Agent**: builder
- **Description**: Inter-agent messaging with Redis pub/sub and DB.
- **Contains**:
  - `AgentMessageBus.__init__(db_session, redis_client=None)`
  - `send(...)` -> AgentMessage
  - `broadcast(...)` -> list[AgentMessage]
  - `get_inbox(...)` -> list[AgentMessage]
  - `mark_read(message_id)` -> None
- **Acceptance Criteria**:
  - DB persistence regardless of Redis
  - Redis publish if available
  - Inbox returns unread sorted by created_at DESC
  - Channel validation (direct, team, task:{uuid}, collab:{uuid})
  - Broadcast to all team agents

### P7-18: Implement RoutingLogger
- **BlockedBy**: P7-01A, P7-01B, P7-06A
- **Files**: `src/collaboration/routing_log.py`
- **Size**: S (~90 LOC)
- **Agent**: builder
- **Description**: Routing decision logging.
- **Contains**:
  - `RoutingLogger.__init__(db_session)`
  - `log_decision(...)` -> RoutingDecisionLogORM
  - `get_analytics(team_id, days=30)` -> dict
- **Acceptance Criteria**:
  - Creates log record
  - Scores stored as JSONB
  - Latency tracked
  - Analytics returns stats

---

## WAVE 4: Services Layer 2 + MoE - 7 tasks

### P7-19A: Implement ExpertGate scoring logic
- **BlockedBy**: P7-02, P7-06A, P7-13
- **Files**: `src/moe/expert_gate.py` (partial - scoring only)
- **Size**: M (~200 LOC)
- **Agent**: builder
- **Description**: Implement 4-signal scoring system. Part 1: scoring logic.
- **Contains**:
  - `ExpertGate.__init__(db_session, embedding_service=None)`
  - `_score_skill_match(query, agent)` -> float
  - `_score_past_performance(query, agent_id, team_id)` -> float
  - `_score_personality_fit(query, agent)` -> float
  - `_score_load_balance(agent_id)` -> float
  - Helper methods for TF-IDF, embeddings (if available), performance query
- **Acceptance Criteria**:
  - Each signal method tested independently
  - Skill match: keyword overlap (embeddings optional)
  - Past performance: avg feedback last 30 days, default 0.7 for new agents
  - Personality fit: tone/style heuristic
  - Load balance: inverse of active load
  - < 50ms per agent (no LLM calls)

### P7-19B: Implement ExpertGate scoring orchestration
- **BlockedBy**: P7-02, P7-19A
- **Files**: `src/moe/expert_gate.py` (complete - orchestration)
- **Size**: M (~100 LOC)
- **Agent**: builder
- **Description**: Implement main ExpertGate.score_experts() that orchestrates scoring. Part 2: orchestration.
- **Contains**:
  - `score_experts(query, team_id, context)` -> list[ExpertScore]
  - Calls all 4 _score_* methods
  - Computes weighted overall score
  - Sorts by overall descending
  - Returns list of ExpertScore models
- **Acceptance Criteria**:
  - Returns ExpertScore for each active agent
  - Scores sorted descending
  - Overall = weighted sum (verified)
  - < 100ms for team of 10 agents
  - **File complete** (both parts merged)

### P7-20: Implement ExpertSelector
- **BlockedBy**: P7-02
- **Files**: `src/moe/expert_selector.py`
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: Strategy-based agent selection from scores.
- **Contains**:
  - `ExpertSelector` class
  - `select(scores, strategy, k=3, confidence_threshold=0.6)` -> SelectionResult
  - TOP_1, TOP_K, ENSEMBLE, CASCADE implementations
  - Fallback logic when best < threshold
- **Acceptance Criteria**:
  - All 4 strategies implemented
  - Confidence threshold check
  - Fallback to default agent sets fallback_used=True
  - TOP_K/ENSEMBLE disabled when enable_ensemble_mode=False

### P7-21A: Implement TaskDelegator core delegation
- **BlockedBy**: P7-01A, P7-01B, P7-06B, P7-13, P7-17
- **Files**: `src/collaboration/task_delegator.py` (partial - core)
- **Size**: M (~180 LOC)
- **Agent**: builder
- **Description**: Implement core task delegation system. Part 1: core flow.
- **Contains**:
  - `TaskDelegator.__init__(db_session, message_bus, celery_dispatch=True)`
  - `delegate(from_agent_id, to_agent_slug, task, parent_task_id)` -> AgentTask
  - `get_result(task_id, timeout_seconds)` -> AgentTask
  - `cancel(task_id, reason)` -> None
  - Basic Celery dispatch: `execute_agent_task.delay(str(task_id))`
  - Redis pub/sub wait (with polling fallback)
- **Acceptance Criteria**:
  - Creates agent_task record (status=pending)
  - Dispatches via Celery
  - get_result waits with timeout
  - cancel updates status to CANCELLED
  - Returns AgentTask

### P7-21B: Implement TaskDelegator safety constraints
- **BlockedBy**: P7-21A
- **Files**: `src/collaboration/task_delegator.py` (complete - safety)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Implement safety constraints for delegation. Part 2: validation.
- **Contains**:
  - `_validate_depth(parent_task_id)` -> int
  - `_detect_cycle(from_agent_id, parent_task_id)` -> bool
  - `_check_availability(agent_id)` -> bool
  - Custom exceptions: DelegationDepthExceeded, CycleDetected, AgentUnavailable, BudgetExhausted
  - Integration into delegate() method
- **Acceptance Criteria**:
  - Depth validation walks parent chain (max 3)
  - Cycle detection: A->B->A fails immediately
  - Concurrent limit: 5 per agent
  - All 4 exceptions defined and raised
  - **File complete** (both parts merged)

### P7-22: Implement ReportManager
- **BlockedBy**: P7-01A, P7-01C, P7-21A
- **Files**: `src/collaboration/report_manager.py`
- **Size**: M (~130 LOC)
- **Agent**: builder
- **Description**: Structured report requests.
- **Contains**:
  - `ReportManager.__init__(task_delegator)`
  - `request_report(...)` -> AgentTask
  - `get_report(task_id)` -> Report
  - REPORT_TEMPLATES integration
  - Report validation
- **Acceptance Criteria**:
  - Converts ReportRequest to AgentTask
  - Template sections in instructions
  - get_report parses to Report
  - Missing sections fail validation
  - 3+ report types defined

### P7-23: Update moe/__init__.py exports
- **BlockedBy**: P7-02, P7-19A, P7-19B, P7-20
- **Files**: `src/moe/__init__.py`
- **Size**: S (~20 LOC)
- **Agent**: builder
- **Description**: Update MoE package init for Phase 7.
- **Acceptance Criteria**:
  - Docstring: "Mixture-of-Experts routing: model tier (Phase 2) + agent expert (Phase 7)."
  - Exports: ExpertGate, ExpertSelector, ExpertScore, SelectionStrategy, SelectionResult
  - Phase 2 functionality unaffected

---

## WAVE 5: Services Layer 3 (High-Dependency) - 8 tasks

### P7-24: Update collaboration __init__.py exports
- **BlockedBy**: P7-12, P7-13, P7-14, P7-15, P7-16, P7-17, P7-18
- **Files**: `src/collaboration/__init__.py`
- **Size**: S (~30 LOC)
- **Agent**: builder
- **Description**: Update collaboration package init.
- **Acceptance Criteria**:
  - All Wave 3 classes importable
  - __all__ list complete
  - `ruff` passes

### P7-25: Implement ResponseAggregator
- **BlockedBy**: P7-02, P7-19A, P7-19B
- **Files**: `src/moe/response_aggregator.py`
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: ENSEMBLE mode response synthesis.
- **Contains**:
  - `ResponseAggregator.__init__(api_key, base_url, model=None)`
  - `aggregate(responses, query)` -> AggregatedResponse
  - Relevance scoring, dedup, merge, attribution
  - Uses Tier 1 model for synthesis
- **Acceptance Criteria**:
  - Aggregates 2+ responses
  - Attribution present
  - Dedup works (similarity > 0.9)
  - Fallback to concatenation if LLM fails

### P7-26A: Implement CollaborationOrchestrator base
- **BlockedBy**: P7-01A, P7-01C, P7-21A, P7-17, P7-13
- **Files**: `src/collaboration/orchestrator.py` (partial - base)
- **Size**: M (~150 LOC)
- **Agent**: builder
- **Description**: Collaboration orchestrator base + SUPERVISOR_WORKER pattern. Part 1.
- **Contains**:
  - `CollaborationOrchestrator.__init__(db_session, task_delegator, message_bus, directory)`
  - `start(lead_agent_id, pattern, goal, context, participants)` -> CollaborationSession
  - `cancel(session_id, reason)` -> None
  - `_create_session()` helper
  - `_check_cost_cap()`, `_check_duration()` helpers
  - SUPERVISOR_WORKER pattern implementation
- **Acceptance Criteria**:
  - Creates collaboration_session record
  - Creates collaboration_participant_v2 records
  - Cost tracking works
  - Duration tracking works
  - SUPERVISOR_WORKER tested

### P7-26B: Implement PIPELINE + PEER_REVIEW patterns
- **BlockedBy**: P7-26A
- **Files**: `src/collaboration/orchestrator.py` (add 2 patterns)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: Add PIPELINE and PEER_REVIEW patterns. Part 2.
- **Contains**:
  - PIPELINE pattern implementation
  - PEER_REVIEW pattern implementation
  - `advance()` logic for both patterns
- **Acceptance Criteria**:
  - PIPELINE: sequential stages, output feeds next
  - PEER_REVIEW: worker->reviewer loop (max_rounds)
  - advance() transitions correctly

### P7-26C: Implement BRAINSTORM + CONSENSUS + DELEGATION patterns
- **BlockedBy**: P7-26B
- **Files**: `src/collaboration/orchestrator.py` (add 3 patterns)
- **Size**: M (~100 LOC)
- **Agent**: builder
- **Description**: Add BRAINSTORM, CONSENSUS, DELEGATION patterns. Part 3.
- **Contains**:
  - BRAINSTORM pattern
  - CONSENSUS pattern
  - DELEGATION pattern (lightweight)
  - Pattern dispatch logic
- **Acceptance Criteria**:
  - All 6 patterns implemented
  - Pattern selection works

### P7-26D: Implement CollaborationOrchestrator synthesis
- **BlockedBy**: P7-26C
- **Files**: `src/collaboration/orchestrator.py` (complete - synthesis)
- **Size**: M (~80 LOC)
- **Agent**: builder
- **Description**: Implement synthesis and completion logic. Part 4.
- **Contains**:
  - `synthesize(session_id)` -> str
  - Lead agent synthesis of all outputs
  - Session completion logic
  - Status transitions: PLANNING -> ACTIVE -> SYNTHESIZING -> COMPLETED
- **Acceptance Criteria**:
  - synthesize() combines all stage outputs
  - Status transitions correct
  - Final output recorded
  - **File complete** (all 4 parts merged)

### P7-27: Implement Celery collaboration task
- **BlockedBy**: P7-21A
- **Files**: `workers/tasks/collaboration.py`
- **Size**: M (~180 LOC)
- **Agent**: builder
- **Description**: Celery task for agent execution. Follow Phase 6 patterns.
- **Contains**:
  - `execute_agent_task(task_id: str)` Celery task
  - Fresh DB session (pool_size=3)
  - Agent context loading
  - Timeout (soft_time_limit)
  - Token/cost tracking
  - Status updates: pending -> in_progress -> completed/failed
  - Redis publish on completion
  - Error handling + retry (max 2)
- **Acceptance Criteria**:
  - Registered with Celery autodiscover
  - UUID conversion inside task
  - asyncio.run() bridge
  - Fresh session (not shared)
  - Status updates verified
  - Redis notification works

### P7-28A: Implement collaboration API - routing endpoints
- **BlockedBy**: P7-12, P7-13, P7-14, P7-15
- **Files**: `src/api/routers/collaboration.py` (partial - routing)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: API router for routing and agent management. Part 1 of 3.
- **Contains**:
  - `router = APIRouter(prefix="/v1", tags=["collaboration"])`
  - `POST /v1/conversations/{id}/handoff` - Initiate handoff
  - `POST /v1/conversations/{id}/agents` - Add/remove agents
  - `GET /v1/agents/recommend` - Agent discovery
  - Auth: Depends(get_current_user), DB: Depends(get_db)
  - Feature flag checks
  - Request/Response models (inline)
- **Acceptance Criteria**:
  - 3 endpoints implemented
  - Auth required
  - Feature flag checks (403 if disabled)
  - Proper status codes
  - Google docstrings

---

## WAVE 6: API Router + Integration - 6 tasks

### P7-28B: Implement collaboration API - task endpoints
- **BlockedBy**: P7-28A, P7-21A
- **Files**: `src/api/routers/collaboration.py` (add task endpoints)
- **Size**: M (~100 LOC)
- **Agent**: builder
- **Description**: API endpoints for task delegation. Part 2 of 3.
- **Contains**:
  - `POST /v1/tasks/delegate` - Delegate task
  - `GET /v1/tasks/{id}` - Task status
  - `POST /v1/tasks/{id}/cancel` - Cancel task
- **Acceptance Criteria**:
  - 3 task endpoints implemented
  - Auth + feature flags
  - Proper validation

### P7-28C: Implement collaboration API - session + message endpoints
- **BlockedBy**: P7-28B, P7-26A, P7-17
- **Files**: `src/api/routers/collaboration.py` (complete - sessions + messages)
- **Size**: M (~120 LOC)
- **Agent**: builder
- **Description**: API endpoints for sessions and messaging. Part 3 of 3.
- **Contains**:
  - `POST /v1/collaborations` - Start session
  - `GET /v1/collaborations/{id}` - Session status
  - `GET /v1/agents/{slug}/inbox` - Message inbox
  - `POST /v1/agents/{slug}/messages` - Send message
- **Acceptance Criteria**:
  - 4 endpoints implemented
  - All 10 total endpoints complete
  - Auth + feature flags
  - **File complete** (10 endpoints total)

### P7-29: Update api/routers/__init__.py
- **BlockedBy**: P7-28C
- **Files**: `src/api/routers/__init__.py`
- **Size**: S (~10 LOC)
- **Agent**: builder
- **Description**: Export collaboration_router.
- **Acceptance Criteria**:
  - collaboration_router importable
  - __all__ updated
  - `ruff` passes

### P7-42: Integrate routing into chat.py
- **BlockedBy**: P7-12, P7-19A, P7-19B, P7-20, P7-18, P7-05
- **Files**: `src/api/routers/chat.py`
- **Size**: M (~150 LOC modification)
- **Agent**: builder
- **Description**: Inject routing logic into chat endpoint. **HIGHEST RISK TASK**.
- **Changes**:
  - Add `_route_to_agent(message, team_id, user_id, current_agent_slug, settings)` helper
  - Feature flag cascade: off -> AgentRouter -> ExpertGate
  - Log routing decisions
  - Integrate at Step 1 of 8-step flow
  - Maintain backward compatibility
- **Acceptance Criteria**:
  - All flags off: exact same behavior
  - enable_agent_collaboration: uses AgentRouter
  - enable_expert_gate: uses ExpertGate
  - Routing logged
  - No regression in existing chat tests
  - `ruff & mypy` pass

### P7-43: Register collaboration router in app.py
- **BlockedBy**: P7-28C, P7-29
- **Files**: `src/api/app.py`
- **Size**: S (~15 LOC)
- **Agent**: builder
- **Description**: Register collaboration_router.
- **Changes**:
  - Import collaboration_router
  - `app.include_router(collaboration_router)` in create_app()
- **Acceptance Criteria**:
  - Router registered
  - Endpoints accessible
  - Existing routers unaffected

---

## WAVE 7: Tests Wave 1 (Foundation) - 5 tasks

### P7-30: Test collaboration models
- **BlockedBy**: P7-01A, P7-01B, P7-01C
- **Files**: `tests/test_collaboration/test_models.py`
- **Size**: M (~150 LOC, ~20 tests)
- **Agent**: builder
- **Description**: Test all Pydantic models and Enums.
- **Tests**: Enum serialization, model creation, validation, defaults, constraints, REPORT_TEMPLATES
- **Acceptance Criteria**: All models tested, invalid data raises ValidationError

### P7-31: Test MoE models
- **BlockedBy**: P7-02
- **Files**: `tests/test_collaboration/test_moe_models.py`
- **Size**: M (~120 LOC, ~15 tests)
- **Agent**: builder
- **Description**: Test MoE models including ExpertScore weighted calculation.
- **Tests**: ExpertScore creation, overall computed field, WEIGHTS sum, validators
- **Acceptance Criteria**: Weighted sum verified, WEIGHTS == 1.0, field validation works

### P7-32: Test AgentRouter
- **BlockedBy**: P7-12, P7-09
- **Files**: `tests/test_collaboration/test_agent_router.py`
- **Size**: M (~100 LOC, ~12 tests)
- **Agent**: builder
- **Description**: Test baseline routing.
- **Tests**: @mention parsing, skill matching, default fallback, backward compat
- **Acceptance Criteria**: All routing strategies tested

### P7-33: Test HandoffManager
- **BlockedBy**: P7-14, P7-09
- **Files**: `tests/test_collaboration/test_handoff.py`
- **Size**: M (~90 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test agent handoff flow.
- **Tests**: Handoff creation, role updates, context summary, return_to_previous, chains
- **Acceptance Criteria**: DB calls verified, roles updated correctly

### P7-34: Test AgentDirectory
- **BlockedBy**: P7-13, P7-09
- **Files**: `tests/test_collaboration/test_agent_discovery.py`
- **Size**: M (~90 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test agent discovery.
- **Tests**: find_experts, skill coverage, exclusion, check_availability, recommend
- **Acceptance Criteria**: Skill coverage correct, exclusion works

---

## WAVE 8: Tests Wave 2 (Service Tests) - 7 tasks

### P7-35: Test ExpertGate
- **BlockedBy**: P7-19A, P7-19B, P7-09, P7-10
- **Files**: `tests/test_collaboration/test_expert_gate.py`
- **Size**: M (~180 LOC, ~15 tests)
- **Agent**: builder
- **Description**: Test 4-signal scoring.
- **Tests**: score_experts, each signal independently, weighted sum, sorting, new agent default
- **Acceptance Criteria**: Each signal tested, math verified

### P7-36: Test ExpertSelector
- **BlockedBy**: P7-20, P7-09, P7-10
- **Files**: `tests/test_collaboration/test_expert_selector.py`
- **Size**: M (~120 LOC, ~12 tests)
- **Agent**: builder
- **Description**: Test all 4 strategies.
- **Tests**: TOP_1, TOP_K, ENSEMBLE, CASCADE, fallback, threshold
- **Acceptance Criteria**: All strategies tested, fallback verified

### P7-37: Test ResponseAggregator
- **BlockedBy**: P7-25, P7-09
- **Files**: `tests/test_collaboration/test_response_aggregator.py`
- **Size**: M (~80 LOC, ~8 tests)
- **Agent**: builder
- **Description**: Test ENSEMBLE synthesis.
- **Tests**: Aggregation, attribution, single response, LLM failure fallback, dedup
- **Acceptance Criteria**: Attribution present, fallback works

### P7-38: Test TaskDelegator
- **BlockedBy**: P7-21A, P7-21B, P7-09
- **Files**: `tests/test_collaboration/test_task_delegator.py`
- **Size**: M (~200 LOC, ~18 tests)
- **Agent**: builder
- **Description**: Test delegation lifecycle + safety.
- **Tests**: delegate, depth validation, cycle detection, concurrent limit, timeout, get_result, cancel, dead-letter, Celery dispatch
- **Acceptance Criteria**: All 4 exceptions tested, depth/cycle verified

### P7-39: Test AgentMessageBus
- **BlockedBy**: P7-17, P7-09
- **Files**: `tests/test_collaboration/test_agent_message_bus.py`
- **Size**: M (~120 LOC, ~12 tests)
- **Agent**: builder
- **Description**: Test inter-agent messaging.
- **Tests**: send, Redis publish, graceful degradation, broadcast, inbox, mark_read, channels
- **Acceptance Criteria**: DB persistence, Redis verified, channels validated

### P7-40: Test ReportManager
- **BlockedBy**: P7-22, P7-09
- **Files**: `tests/test_collaboration/test_report_manager.py`
- **Size**: M (~100 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test structured reports.
- **Tests**: request_report, template injection, get_report, validation, model tier
- **Acceptance Criteria**: Template conversion, validation works

### P7-41: Test RoutingLogger
- **BlockedBy**: P7-18, P7-09
- **Files**: `tests/test_collaboration/test_routing_log.py`
- **Size**: S (~60 LOC, ~6 tests)
- **Agent**: builder
- **Description**: Test routing logging.
- **Tests**: log_decision, JSONB, latency, analytics
- **Acceptance Criteria**: All fields persisted, analytics works

---

## WAVE 9: Integration Tests - 8 tasks

### P7-44: Test MultiAgentManager
- **BlockedBy**: P7-15, P7-09
- **Files**: `tests/test_collaboration/test_multi_agent.py`
- **Size**: M (~90 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test multi-agent conversations.
- **Tests**: add_agent, remove_agent, get_participants, duplicate prevention, soft delete
- **Acceptance Criteria**: All CRUD tested, unique constraint verified

### P7-45: Test TeamMemoryBus
- **BlockedBy**: P7-16, P7-09
- **Files**: `tests/test_collaboration/test_team_memory_bus.py`
- **Size**: S (~50 LOC, ~5 tests)
- **Agent**: builder
- **Description**: Test shared memory propagation.
- **Tests**: Hot cache invalidation, graceful degradation, logging
- **Acceptance Criteria**: Invalidation verified, no-op when unavailable

### P7-46A: Test CollaborationOrchestrator - SUPERVISOR + PIPELINE
- **BlockedBy**: P7-26A, P7-26B, P7-09
- **Files**: `tests/test_collaboration/test_collaboration_orchestrator.py` (partial)
- **Size**: M (~120 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test SUPERVISOR_WORKER and PIPELINE patterns.
- **Tests**: Both patterns (2 tests each), advance(), basic lifecycle
- **Acceptance Criteria**: Patterns work, advance transitions correctly

### P7-46B: Test CollaborationOrchestrator - remaining patterns + constraints
- **BlockedBy**: P7-46A, P7-26C, P7-26D
- **Files**: `tests/test_collaboration/test_collaboration_orchestrator.py` (complete)
- **Size**: M (~120 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test remaining 4 patterns + cost/duration constraints.
- **Tests**: PEER_REVIEW, BRAINSTORM, CONSENSUS, DELEGATION, cost cap, timeout, synthesize, cancel
- **Acceptance Criteria**: All 6 patterns tested (2 per pattern min), constraints enforced

### P7-47: Test Celery collaboration task
- **BlockedBy**: P7-27, P7-09
- **Files**: `tests/test_workers/test_collaboration_tasks.py`
- **Size**: M (~100 LOC, ~8 tests)
- **Agent**: builder
- **Description**: Test Celery task execution.
- **Tests**: Task execution, status transitions, timeout, error, retry, Redis notification, cost tracking
- **Acceptance Criteria**: All statuses tested, timeout works, retry verified

### P7-48: Test collaboration API router
- **BlockedBy**: P7-28A, P7-28B, P7-28C, P7-09
- **Files**: `tests/test_api/test_collaboration_router.py`
- **Size**: M (~180 LOC, ~15 tests)
- **Agent**: builder
- **Description**: Test all 10 API endpoints.
- **Tests**: All endpoints, auth, feature flags, status codes
- **Acceptance Criteria**: All 10 tested, auth enforced, flags checked

### P7-49: Test chat.py routing integration
- **BlockedBy**: P7-42, P7-09
- **Files**: `tests/test_api/test_chat_routing.py`
- **Size**: M (~110 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test routing in chat endpoint.
- **Tests**: Flag cascade, direct dispatch, AgentRouter, ExpertGate, logging, fallback, no regression
- **Acceptance Criteria**: All flag levels tested, backward compat verified

### P7-50: Test ORM models
- **BlockedBy**: P7-06A, P7-06B, P7-06C, P7-09
- **Files**: `tests/test_collaboration/test_orm_models.py`
- **Size**: M (~100 LOC, ~10 tests)
- **Agent**: builder
- **Description**: Test ORM model creation and constraints.
- **Tests**: All 7 models instantiation, UniqueConstraints, CheckConstraints, FKs, JSONB, timestamps
- **Acceptance Criteria**: All 7 models tested, constraints raise errors

---

## WAVE 10: Smoke Tests - 6 tasks

### P7-51: Test migration 004 structure
- **BlockedBy**: P7-07
- **Files**: `tests/test_collaboration/test_migration.py`
- **Size**: S (~50 LOC, ~5 tests)
- **Agent**: builder
- **Description**: Test migration metadata and structure.
- **Tests**: revision, down_revision, table count, enum
- **Acceptance Criteria**: Metadata correct, operation count verified

### P7-52: Test db/models exports
- **BlockedBy**: P7-08
- **Files**: `tests/test_collaboration/test_model_exports.py`
- **Size**: S (~40 LOC, ~3 tests)
- **Agent**: builder
- **Description**: Verify ORM model imports.
- **Tests**: __all__, importability, no errors
- **Acceptance Criteria**: All 7 models importable

### P7-53: E2E routing smoke test
- **BlockedBy**: P7-49
- **Files**: `tests/test_collaboration/test_routing_e2e.py`
- **Size**: M (~80 LOC, ~5 tests)
- **Agent**: builder
- **Description**: End-to-end routing flow.
- **Tests**: Full chain, ENSEMBLE mode, feature flag progression
- **Acceptance Criteria**: Full chain executes, components called in order

### P7-54: E2E delegation smoke test
- **BlockedBy**: P7-46B, P7-47
- **Files**: `tests/test_collaboration/test_delegation_e2e.py`
- **Size**: M (~80 LOC, ~5 tests)
- **Agent**: builder
- **Description**: End-to-end delegation flow.
- **Tests**: Full flow, sub-delegation chain (depth 2), cycle detection, timeout
- **Acceptance Criteria**: Full lifecycle verified, sub-delegation works

### P7-55: E2E collaboration smoke test
- **BlockedBy**: P7-46B
- **Files**: `tests/test_collaboration/test_collaboration_e2e.py`
- **Size**: M (~80 LOC, ~5 tests)
- **Agent**: builder
- **Description**: End-to-end collaboration session.
- **Tests**: SUPERVISOR_WORKER full, PIPELINE full, cost cap trigger, status transitions
- **Acceptance Criteria**: 2 patterns end-to-end, cost tracking verified

### P7-56: Backward compatibility smoke test
- **BlockedBy**: P7-42, P7-43
- **Files**: `tests/test_collaboration/test_backward_compat.py`
- **Size**: S (~60 LOC, ~5 tests)
- **Agent**: builder
- **Description**: Verify no regression with flags off.
- **Tests**: All flags off, settings load, deps initialize, CLI startup, existing API
- **Acceptance Criteria**: No regression with default flags

---

## WAVE 11: Final Validation - 2 tasks

### P7-57: Run full test suite
- **BlockedBy**: P7-53, P7-54, P7-55, P7-56
- **Files**: None (validation)
- **Size**: M
- **Agent**: tester
- **Description**: Run complete test suite.
- **Commands**: `.venv/bin/python -m pytest tests/ -v`
- **Acceptance Criteria**: ~1115 tests pass (935 + 180), 0 failures, no new warnings

### P7-58: Run lint and type checks
- **BlockedBy**: P7-57
- **Files**: None (validation)
- **Size**: S
- **Agent**: tester
- **Description**: Lint + type checking.
- **Commands**: `ruff check src/ tests/`, `ruff format --check`, `mypy src/`
- **Acceptance Criteria**: Zero errors, mypy passes (or only pre-existing)

---

## Summary Stats

| Metric | Original | Revised | Change |
|--------|----------|---------|--------|
| **Total Tasks** | 58 | 78 | +20 (+34%) |
| **Large (L) Tasks** | 12 | 0 | -12 (-100%) ✅ |
| **Medium (M) Tasks** | 29 | 54 | +25 (+86%) |
| **Small (S) Tasks** | 17 | 24 | +7 (+41%) |
| **Waves** | 11 | 11 | 0 |
| **Max Parallelism** | 7 | 7 | 0 |
| **Critical Path Depth** | 8 | 11 | +3 |

## Context Window Risk Assessment

### Original Breakdown
- **12 tasks at risk** (Size L, 300-400 LOC + tests)
- **Est. context consumption per L task**: 60-80% of window with testing

### Revised Breakdown
- **0 tasks at risk** (eliminated all L tasks)
- **Max context consumption per M task**: 30-40% of window with testing
- **Buffer for agent context, codebase reading, exploration**: 50-70% remaining ✅

## File Splits Summary

| Original Task | Split Into | Reason |
|---------------|------------|--------|
| P7-01 (models.py) | P7-01A/B/C | 8 Enums + 15 models → 3 phases |
| P7-06 (7 ORM models) | P7-06A/B/C | 7 models → 3 groups |
| P7-19 (ExpertGate) | P7-19A/B | 4 signals + orchestration → 2 parts |
| P7-21 (TaskDelegator) | P7-21A/B | Core + safety → 2 parts |
| P7-26 (Orchestrator) | P7-26A/B/C/D | 6 patterns → 4 parts |
| P7-28 (API router) | P7-28A/B/C | 10 endpoints → 3 groups |
| P7-46 (Orch tests) | P7-46A/B | 20 tests → 2 parts |

---

## Critical Path (Revised, Depth 11)

```
P7-01A -> P7-01B -> P7-01C -> P7-06A -> P7-06B -> P7-06C -> P7-07
                                  |
                                  +-> P7-21A -> P7-21B -> P7-26A -> P7-26B -> P7-26C -> P7-26D
                                                             |
                                                             +-> P7-46A -> P7-46B -> P7-55 -> P7-57 -> P7-58
```

**Longest path**: P7-01A → ... → P7-58 (depth 11)

---

## Success Criteria

- ✅ No task exceeds 300 total LOC (implementation + tests)
- ✅ All Large (L) tasks eliminated
- ✅ Context window usage < 40% for any single task
- ✅ Testing overhead fully accounted for
- ✅ Build parallelism maintained (max 7 concurrent)
- ✅ All integration points preserved
- ✅ No functionality lost from original 58-task plan

---

## Final Checklist (Phase 7 Complete)

### Code Quality
- [ ] All 78 tasks completed
- [ ] ~1115 tests passing (935 existing + ~180 new)
- [ ] `ruff check src/ tests/` → 0 errors
- [ ] `ruff format --check src/ tests/` → 0 violations
- [ ] `mypy src/` → 0 new errors

### Functionality
- [ ] All 7 DB tables created (migration 004)
- [ ] All 10 API endpoints functional
- [ ] All 4 routing strategies work (TOP_1, TOP_K, ENSEMBLE, CASCADE)
- [ ] All 6 collaboration patterns execute (SUPERVISOR_WORKER, PIPELINE, PEER_REVIEW, BRAINSTORM, CONSENSUS, DELEGATION)
- [ ] Delegation safety constraints enforced (depth, cycles, concurrency)

### Integration
- [ ] Chat routing integration works (feature flag cascade)
- [ ] Backward compatibility verified (all flags off = no change)
- [ ] CLI startup unaffected
- [ ] No regression in existing tests
- [ ] AgentDependencies has 26 Optional fields (18 existing + 8 new)

### Documentation
- [ ] All new files have module docstrings
- [ ] All functions have Google-style docstrings
- [ ] LEARNINGS.md updated with Phase 7 patterns

### Deployment Readiness
- [ ] Migration 004 tested (upgrade + downgrade)
- [ ] All feature flags default to False
- [ ] Celery task registered
- [ ] Redis graceful degradation verified

---

**Approver**: _________________ **Date**: _________________

**Deploy Command**: `go` (to create all 78 tasks in task system)
