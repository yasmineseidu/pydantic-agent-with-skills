# Phase 7: Agent Collaboration - Technical Research Report

> Generated: 2026-02-10 | Complexity Score: 8 (Ambiguity=1, Integration=2, Novelty=2, Risk=2, Scale=1)

## 1. Executive Summary

Phase 7 introduces an agent collaboration layer on top of existing Phases 2-6. The implementation spans two major systems:

1. **MoE Agent Routing** (3 new files in `src/moe/`): ExpertGate, ExpertSelector, ResponseAggregator
2. **Collaboration Stack** (10 new files in `src/collaboration/`): Router, Handoff, MultiAgent, TaskDelegator, MessageBus, CollaborationOrchestrator, Discovery, ReportManager, TeamMemoryBus, Models

Plus: 7 new DB tables (migration 004), 1 new API router, integration modifications to 5 existing files.

## 2. Existing Codebase Patterns (Local Grep Results)

### 2.1 MoE Layer (Phase 2) - Pattern to Follow

The existing MoE system (`src/moe/`) provides the exact blueprint for Phase 7's agent routing:

| Existing File | Pattern | Phase 7 Counterpart |
|---|---|---|
| `model_tier.py` | `ComplexityScore(BaseModel)` with `WEIGHTS: ClassVar`, `@computed_field` weighted_total | `ExpertScore(BaseModel)` with 4-signal WEIGHTS (0.40, 0.25, 0.20, 0.15) |
| `complexity_scorer.py` | `QueryComplexityScorer` with LLM scoring + heuristic fallback | `ExpertGate` with 4-signal scoring (TF-IDF, embeddings, classifier) |
| `model_router.py` | `ModelRouter.route()` with force_tier, max_tier, budget_remaining | `ExpertSelector.select()` with strategy, k, confidence_threshold |
| `cost_guard.py` | In-memory budget tracking with `asyncio.Lock` | Collaboration cost caps (per-task $, per-session $0.50) |

**Key pattern**: All MoE models use `Pydantic BaseModel` with `Field(ge=, le=)` validators. The `ComplexityScore` uses `ClassVar[dict[str, float]]` for weights and `@computed_field @property` for `weighted_total`. Phase 7's `ExpertScore` must follow this exact pattern.

### 2.2 ORM Model Pattern

From `src/db/models/agent.py` (line 14-133) and `src/db/base.py`:
- All models inherit `Base, UUIDMixin, TimestampMixin`
- Use `mapped_column()` with SA types: `sa.Uuid()`, `sa.Text()`, `sa.Boolean()`, `sa.Integer()`, `JSONB()`
- ForeignKey pattern: `ForeignKey("table.id", ondelete="CASCADE")`
- Enum handling: `Enum(native_enum=True, create_constraint=True)` or `Text()` for flexibility
- Existing convention: `ARRAY(Text)` for text arrays
- Reserved word mapping: `metadata_json` in Python for `metadata` SQL column

### 2.3 Migration Pattern

From `src/db/migrations/versions/003_phase6_scheduled_job.py`:
- Next revision: `"004"`, down_revision: `"003"`
- Pattern: `op.create_table()` with `sa.Column()` declarations
- Partial indexes via `op.execute("CREATE INDEX ... WHERE ...")`
- Trigger reuse: `trigger_set_updated_at()` created in migration 001
- UUID default: `server_default=sa.text("gen_random_uuid()")`
- Timestamp default: `server_default=sa.text("now()")`

### 2.4 API Router Pattern

From `src/api/routers/chat.py` and `src/api/app.py`:
- Router creation: `router = APIRouter(prefix="/v1/{resource}", tags=["{resource}"])`
- Auth via `Depends()`: `current_user: UserORM = Depends(get_current_user)`
- DB session: `db: AsyncSession = Depends(get_db)`
- Settings: `settings: Settings = Depends(get_settings)`
- Registration: `app.include_router(collaboration_router)` in `create_app()`

### 2.5 Dependencies Pattern

From `src/dependencies.py` (line 1-123):
- TYPE_CHECKING imports for forward references (avoids circular imports)
- All new fields are `Optional["TypeName"]` with `= None`
- External initialization (not in `initialize()` method)
- Current fields: 10 memory, 3 MoE, 5 cache = 18 Optional fields
- Phase 7 adds ~6-8 new Optional fields (agent_router, expert_gate, expert_selector, handoff_manager, task_delegator, message_bus, collaboration_orchestrator, agent_directory)

### 2.6 Test Fixture Pattern

From `tests/test_moe/conftest.py` and `tests/test_workers/conftest.py`:
- `@pytest.fixture` returning Pydantic model instances or MagicMock/AsyncMock
- `mock_session_factory` with `__aenter__`/`__aexit__` support
- `mock_settings` with all required fields as MagicMock attributes
- Celery testing: `CELERY_ALWAYS_EAGER=true` env var patch

### 2.7 Celery Task Integration

From `workers/celery_app.py` and `workers/tasks/`:
- Tasks discover from `workers.tasks` package
- UUIDs passed as strings (JSON serializable), converted inside tasks
- `asyncio.run()` bridge for async code in sync Celery tasks
- Fresh DB sessions per task (not shared with FastAPI lifecycle)
- Pool size 3 for worker engine

### 2.8 Key Finding: MessageORM Already Has agent_id

`src/db/models/conversation.py` line 115:
```python
agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agent.id"), nullable=True)
```

The `ALTER TABLE message ADD COLUMN agent_id` from the Phase 7 plan is **already done**. Migration 004 does NOT need this column.

## 3. Battle-Tested Patterns from Open Source

### 3.1 MoE/Expert Routing Patterns

**Pattern: Weighted Multi-Signal Scoring**
- Standard approach in ML literature: weighted linear combination with normalization
- Google's Switch Transformer (2021) uses top-k gating with load balancing loss
- Phase 7 adapts this at the agent level: 4 signals instead of learned gates
- Key insight: Fixed weights (0.40/0.25/0.20/0.15) are appropriate for v1; learned weights are a Phase 8+ optimization

**Pattern: Selection Strategy (Top-K, Cascade)**
- LangChain's agent routing uses a "router chain" pattern with confidence thresholds
- AutoGen (Microsoft) implements agent selection via conversation-level routing
- CrewAI uses role-based agent selection with explicit task assignment
- Phase 7's 4 strategies (TOP_1, TOP_K, ENSEMBLE, CASCADE) cover all standard patterns

**Pattern: Response Aggregation**
- "Mixture of Agents" paper (2024) shows that combining LLM outputs via a synthesizer model produces better results than any single model
- The meta-model synthesis pattern (using Tier 1 to combine outputs) is well-established
- Attribution pattern ("According to X...") is standard in multi-source synthesis

### 3.2 Multi-Agent Collaboration Patterns

**Pattern: Supervisor-Worker (Most Common)**
- AutoGen: "GroupChat" with manager agent that delegates
- CrewAI: "Sequential" and "Hierarchical" process patterns
- LangGraph: "Supervisor" node that routes to worker nodes
- Phase 7 matches CrewAI's hierarchical pattern most closely

**Pattern: Pipeline (Sequential Stages)**
- LangGraph: Directed graph with conditional edges
- CrewAI: Sequential process with output passing
- Phase 7's implementation passes previous stage output to next stage, matching standard patterns

**Pattern: Peer Review**
- LangChain: "Critique and Revise" pattern with validator agent
- Constitutional AI: Self-critique with external feedback
- Phase 7 adds multi-round review (max_rounds=5), which is more sophisticated

**Pattern: Consensus**
- Constitutional AI voting patterns
- Multi-agent debate frameworks (Du et al., 2023)
- Phase 7's independent-assess-then-converge matches the debate pattern

### 3.3 Task Delegation Patterns

**Pattern: Depth-Limited Delegation**
- Standard in process management: max fork depth prevents fork bombs
- Phase 7's max_depth=3 matches common practice (2-3 levels in most systems)
- Cycle detection via parent_task_id traversal is the standard approach

**Pattern: Async Task Execution**
- Celery task dispatch is the de facto Python standard for async background work
- Phase 7 correctly uses `execute_agent_task.delay(task_id)` pattern
- Redis pub/sub for result notification is standard (vs. polling)

### 3.4 Inter-Agent Messaging

**Pattern: Channel-Based Messaging**
- Redis pub/sub is the standard lightweight message broker for Python
- Channel naming: `direct:{from}:{to}`, `team:{id}`, `task:{id}` patterns are common
- DB persistence + real-time notification is the standard hybrid approach
- Phase 7's channel scheme matches established patterns

## 4. Integration Risk Assessment

### 4.1 High Risk: Chat Router Integration

`src/api/routers/chat.py` is the most complex file in the codebase (200+ lines, 8-step flow). Phase 7 must inject routing logic at Step 1 (resolve agent). This is the highest-risk integration point because:
- Multiple feature flag checks needed
- Must maintain backward compatibility (direct dispatch when flags off)
- Error in routing breaks ALL chat functionality

**Mitigation**: Feature flag wrapping with fallback to direct dispatch. Integration should be a separate task from service implementation.

### 4.2 Medium Risk: Dependencies Dataclass Growth

`src/dependencies.py` already has 18 Optional fields. Phase 7 adds 6-8 more. Risk:
- Initialization complexity grows
- TYPE_CHECKING imports grow
- Each new field is another potential None check

**Mitigation**: Group Phase 7 fields under a comment block. Consider a nested dataclass in Phase 8 if it grows further.

### 4.3 Medium Risk: Celery Task for Agent Execution

Task delegation via Celery means an agent running inside a Celery worker. This requires:
- Fresh DB session (not shared with FastAPI)
- LLM client initialization inside the worker
- Token/cost tracking independent of the FastAPI request lifecycle
- Proper timeout and error handling

**Mitigation**: Follow Phase 6 patterns exactly (workers/utils.py bridge, fresh sessions). New Celery task: `workers/tasks/collaboration.py`.

### 4.4 Low Risk: Migration 004 Size

7 new tables with ~20 indexes in a single migration. This is large but well-defined. The SQL is exact in the plan.

**Mitigation**: Split into logical sections within the migration file (like 001). Test downgrade path.

### 4.5 Low Risk: Feature Flag Count

5 total collaboration flags (3 existing already planned: agent_collaboration, expert_gate, ensemble_mode; plus 2 new: task_delegation, collaboration). The flag progression is well-defined.

## 5. Complexity Scoring

| Dimension | Score | Rationale |
|---|---|---|
| Ambiguity | 1 | Plan has exact class signatures, SQL schemas, and test scenarios |
| Integration | 2 | Touches chat.py (critical path), dependencies.py, settings.py, moe/__init__.py, db/models/__init__.py |
| Novelty | 2 | Multi-agent orchestration patterns are new to this codebase, though well-established in the ecosystem |
| Risk | 2 | Chat router integration could break all chat; Celery agent execution is complex |
| Scale | 1 | ~20 new files, 7 DB tables, but well-decomposable into independent units |

**Total: 8 -> opus for architecture, sonnet for most agents, opus for orchestrator/chat integration tasks**

## 6. Recommendations for Task Decomposition

1. **Foundation first**: Pydantic models and Enums before services (no dependencies)
2. **DB migration early**: Tables needed by all services
3. **Services bottom-up**: Discovery -> Messaging -> TaskDelegator -> ReportManager -> Orchestrator
4. **MoE separate track**: ExpertGate/Selector/Aggregator are independent of collaboration stack
5. **Integration last**: Chat router, dependencies, settings modifications after all services
6. **Tests per service**: Each service gets its own test task in the next wave
7. **Conftest early**: Shared test fixtures for collaboration tests created before any test tasks
8. **MessageORM skip**: agent_id column already exists, remove from migration

## 7. File Inventory: What Exists vs What's New

### EXISTS (modify)
| File | Modification |
|---|---|
| `src/settings.py` | Add 4 feature flags to FeatureFlags |
| `src/dependencies.py` | Add 6-8 Optional collaboration fields + TYPE_CHECKING imports |
| `src/moe/__init__.py` | Add Phase 7 exports (ExpertGate, ExpertSelector, etc.) |
| `src/db/models/__init__.py` | Add Phase 7 ORM model exports |
| `src/api/routers/__init__.py` | Add collaboration_router export |
| `src/api/app.py` | Register collaboration_router |
| `src/api/routers/chat.py` | Inject routing logic at Step 1 |

### NEW (create)
| File | Purpose |
|---|---|
| `src/collaboration/__init__.py` | Package init with exports |
| `src/collaboration/models.py` | All Pydantic models + Enums |
| `src/collaboration/router.py` | AgentRouter (baseline routing) |
| `src/collaboration/handoff.py` | HandoffManager |
| `src/collaboration/multi_agent.py` | Multi-agent conversation mgmt |
| `src/collaboration/team_memory_bus.py` | Shared memory propagation |
| `src/collaboration/discovery.py` | AgentDirectory |
| `src/collaboration/task_delegator.py` | TaskDelegator |
| `src/collaboration/message_bus.py` | AgentMessageBus |
| `src/collaboration/report_manager.py` | ReportManager |
| `src/collaboration/orchestrator.py` | CollaborationOrchestrator |
| `src/moe/models.py` | ExpertScore, SelectionStrategy, SelectionResult, etc. |
| `src/moe/expert_gate.py` | ExpertGate (4-signal scoring) |
| `src/moe/expert_selector.py` | ExpertSelector (4 strategies) |
| `src/moe/response_aggregator.py` | ResponseAggregator (ENSEMBLE) |
| `src/db/models/collaboration.py` | All 7 ORM models |
| `src/db/migrations/versions/004_phase7_collaboration.py` | Migration for 7 tables |
| `src/api/routers/collaboration.py` | API endpoints |
| `workers/tasks/collaboration.py` | Celery task for agent execution |
| `tests/test_collaboration/__init__.py` | Test package init |
| `tests/test_collaboration/conftest.py` | Shared test fixtures |
| `tests/test_collaboration/test_agent_router.py` | Router tests |
| `tests/test_collaboration/test_handoff.py` | Handoff tests |
| `tests/test_collaboration/test_multi_agent.py` | Multi-agent tests |
| `tests/test_collaboration/test_team_memory_bus.py` | Team memory tests |
| `tests/test_collaboration/test_agent_discovery.py` | Discovery tests |
| `tests/test_collaboration/test_task_delegator.py` | Delegation tests |
| `tests/test_collaboration/test_agent_message_bus.py` | Messaging tests |
| `tests/test_collaboration/test_report_manager.py` | Report tests |
| `tests/test_collaboration/test_collaboration_orchestrator.py` | Orchestrator tests |
| `tests/test_collaboration/test_expert_gate.py` | Expert gate tests |
| `tests/test_collaboration/test_expert_selector.py` | Expert selector tests |
| `tests/test_collaboration/test_response_aggregator.py` | Response aggregator tests |
| `tests/test_collaboration/test_routing_log.py` | Routing log tests |
| `tests/test_moe/test_expert_gate.py` | (or in test_collaboration/) |
| `tests/test_moe/test_expert_selector.py` | (or in test_collaboration/) |
| `tests/test_moe/test_response_aggregator.py` | (or in test_collaboration/) |

**Total: ~7 modified files + ~30 new files = ~37 files**
