# Phase 7: Agent Collaboration, MoE Expert Gate & Multi-Agent Conversations

> **Timeline**: Week 5 | **Prerequisites**: Phase 2 (Memory), Phase 4 (API + Auth) | **Status**: Not Started

## Goal

Enable agents to collaborate, hand off conversations, participate in multi-agent threads, and share discoveries through team memory. This unlocks the "unlimited agents" promise -- agents aren't just isolated islands, they're a coordinated team.

> **Note**: All 7 memory types and the bulletproof memory architecture are built in Phase 2 (per ADR-7). This phase builds the **inter-agent** layer on top of that foundation.

## Dependencies (Install)

```toml
# No new pyproject.toml additions required for Phase 7.
# All dependencies were introduced in earlier phases:
#   - SQLAlchemy (Phase 1)
#   - FastAPI (Phase 4)
#   - Redis/caching (Phase 3)
#   - Memory system (Phase 2)
```

## Settings Extensions

```python
# src/settings.py -- FeatureFlags addition
class FeatureFlags(BaseModel):
    """Simple boolean feature flags via environment variables."""
    # ... existing flags ...
    enable_agent_collaboration: bool = Field(default=False)  # Phase 7: Router, handoff
    enable_expert_gate: bool = Field(default=False)          # Phase 7: MoE 4-signal scoring
    enable_ensemble_mode: bool = Field(default=False)        # Phase 7: Multi-expert responses

# Checked at runtime:
if settings.feature_flags.enable_agent_collaboration:
    if settings.feature_flags.enable_expert_gate:
        routing = await expert_gate.route(message, team_id, ...)  # MoE routing
    else:
        routing = await router.route(message, team_id, ...)       # Simple skill matching
else:
    agent = await registry.get_agent(team_id, agent_slug)  # Direct dispatch
```

## New Directories & Files

```
src/collaboration/
    __init__.py
    router.py                # AgentRouter - simple skill-based dispatch (baseline)
    handoff.py               # HandoffManager - agent-to-agent transfers
    multi_agent.py           # Multi-agent conversation orchestration
    team_memory_bus.py       # Shared memory propagation across agents
    discovery.py             # Agent discovery/recommendation API (AgentDirectory)
    task_delegator.py        # TaskDelegator - task delegation lifecycle
    message_bus.py           # AgentMessageBus - inter-agent messaging
    report_manager.py        # ReportManager - structured report requests
    orchestrator.py          # CollaborationOrchestrator - multi-agent workflows
    models.py                # RoutingDecision, HandoffResult, AgentRecommendation, AgentTask, AgentMessage, etc.

src/moe/                     # MoE pattern applied at TWO layers:
    # Phase 2 files (model routing):
    model_router.py          # Routes queries to Tier 0/1/2 models (cost optimization)
    complexity_scorer.py     # 5-dimension complexity scoring (0-10 scale)
    tier_selector.py         # Selects model tier based on complexity

    # Phase 7 files (agent routing):
    expert_gate.py           # ExpertGate - 4-signal scoring for agent selection
    expert_selector.py       # ExpertSelector - strategy-based selection (TOP_1, TOP_K, ENSEMBLE, CASCADE)
    response_aggregator.py   # ResponseAggregator - ENSEMBLE mode synthesis
    models.py                # ExpertScore, SelectionStrategy, SelectionResult, ExpertResponse, AggregatedResponse

api/routers/
    collaboration.py         # API endpoints for handoff, multi-agent, discovery

tests/test_collaboration/
    __init__.py
    test_agent_router.py     # Routing decisions, @mention parsing
    test_handoff.py          # Agent-to-agent handoff, context preservation
    test_multi_agent.py      # Multi-participant conversations
    test_team_memory_bus.py  # Shared memory propagation
    test_agent_discovery.py  # Skill-based agent recommendation
    test_expert_gate.py      # 4-signal scoring, thresholds
    test_expert_selector.py  # All 4 strategies, fallback
    test_response_aggregator.py  # ENSEMBLE merge, attribution, dedup
    test_routing_log.py      # Decision logging, analytics queries
```

> **Note**: The `src/moe/` directory houses **two complementary MoE systems**:
> - **Phase 2**: Model routing (Tier 0/1/2) based on query complexity -- optimizes cost
> - **Phase 7**: Agent routing (ExpertGate) based on 4 signals -- optimizes expertise match
>
> Both use the MoE pattern but at different abstraction layers. A single query might flow through:
> 1. **ExpertGate** → selects the best agent(s)
> 2. **ModelRouter** → selects the optimal model tier for that agent's response

## Database Tables Introduced

**7 tables total**: 3 for basic collaboration (conversation_participant, agent_handoff, routing_decision_log) + 4 for full agent collaboration protocol (agent_task, agent_message, collaboration_session, collaboration_participant_v2).

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `conversation_participant` | `id`, `conversation_id` (FK conversation), `agent_id` (FK agent), `role` (participant_role ENUM: 'primary', 'invited', 'handoff_source'), `joined_at`, `left_at` | Tracks which agents participate in a conversation. UNIQUE constraint on (conversation_id, agent_id). |
| `agent_handoff` | `id`, `conversation_id` (FK conversation), `from_agent_id` (FK agent), `to_agent_id` (FK agent), `reason`, `context_summary`, `created_at` | History of agent-to-agent conversation transfers. |
| `routing_decision_log` | `id`, `team_id`, `conversation_id`, `message_id`, `strategy`, `scores` (JSONB), `selected_agents` (TEXT[]), `confidence_threshold`, `fallback_used`, `complexity_score`, `complexity_dimensions` (JSONB), `selected_tier`, `selected_model`, `tier_override_reason`, `estimated_cost`, `actual_cost`, `gate_latency_ms`, `router_latency_ms`, `created_at` | MoE Expert Gate routing decisions, scores, and performance metrics. |
| `agent_task` | `id`, `team_id`, `created_by_agent_id`, `assigned_to_agent_id`, `parent_task_id`, `task_type`, `title`, `instructions`, `context`, `expected_output`, `status`, `result`, `delegation_depth`, `tokens_used`, `cost_usd`, `created_at`, `completed_at` | Task delegation between agents. Max depth=3, no self-delegation. |
| `agent_message` | `id`, `team_id`, `from_agent_id`, `to_agent_id`, `channel`, `message_type`, `content`, `metadata`, `read_at`, `created_at` | Inter-agent messaging. Channels: direct, team, task:{id}, collab:{id}. |
| `collaboration_session` | `id`, `team_id`, `lead_agent_id`, `pattern`, `goal`, `context`, `status`, `total_cost_usd`, `final_output`, `stage_outputs` (JSONB), `created_at`, `completed_at` | Multi-agent collaboration workflows. 5 patterns: supervisor-worker, pipeline, peer-review, brainstorm, consensus. |
| `collaboration_participant_v2` | `id`, `session_id`, `agent_id`, `role`, `stage`, `task_id`, `status`, `created_at` | Participants in collaboration sessions. Renamed to avoid conflict with conversation_participant. |

**Message table update:**
```sql
ALTER TABLE message ADD COLUMN agent_id UUID REFERENCES agent(id);
-- Which agent authored this message -- NULL for user/system messages
```

Reference: `plan/sql/schema.sql` (Phase 7 section, lines 543-578)

### Full SQL from schema.sql

```sql
-- conversation_participant
CREATE TABLE conversation_participant (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    role                participant_role NOT NULL DEFAULT 'primary',
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    left_at             TIMESTAMPTZ,         -- NULL = still active

    CONSTRAINT uq_conversation_participant UNIQUE (conversation_id, agent_id)
);

-- agent_handoff
CREATE TABLE agent_handoff (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    from_agent_id       UUID NOT NULL REFERENCES agent(id),
    to_agent_id         UUID NOT NULL REFERENCES agent(id),
    reason              TEXT NOT NULL,
    context_summary     TEXT,                -- Summary passed to target agent
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- routing_decision_log
CREATE TABLE routing_decision_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id                 UUID NOT NULL REFERENCES team(id),
    conversation_id         UUID REFERENCES conversation(id),
    message_id              UUID REFERENCES message(id),
    strategy                TEXT NOT NULL,           -- "top_1", "top_k", "ensemble", "cascade"
    scores                  JSONB NOT NULL,          -- Array of ExpertScore objects
    selected_agents         TEXT[] NOT NULL,         -- Agent slugs selected
    confidence_threshold    FLOAT NOT NULL DEFAULT 0.6,
    fallback_used           BOOLEAN NOT NULL DEFAULT FALSE,
    complexity_score        FLOAT,                   -- Overall complexity (0-10)
    complexity_dimensions   JSONB,                   -- 5-dimension breakdown
    selected_tier           TEXT,                    -- "tier_0", "tier_1", "tier_2"
    selected_model          TEXT,                    -- Model that was used
    tier_override_reason    TEXT,                    -- Why tier was overridden (if applicable)
    estimated_cost          FLOAT,                   -- Estimated cost in USD
    actual_cost             FLOAT,                   -- Actual cost after execution
    gate_latency_ms         FLOAT,                   -- Time spent scoring experts
    router_latency_ms       FLOAT,                   -- Time spent in routing logic
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_participant_conversation ON conversation_participant (conversation_id)
    WHERE left_at IS NULL;
CREATE INDEX idx_participant_agent ON conversation_participant (agent_id)
    WHERE left_at IS NULL;
CREATE INDEX idx_handoff_conversation ON agent_handoff (conversation_id, created_at);
CREATE INDEX idx_routing_log_team ON routing_decision_log (team_id, created_at);
CREATE INDEX idx_routing_log_conversation ON routing_decision_log (conversation_id);
CREATE INDEX idx_routing_log_strategy ON routing_decision_log (strategy);
CREATE INDEX idx_routing_log_scores_gin ON routing_decision_log USING GIN (scores);
```

### Enum Types (from Phase 1 migration, used here)

```sql
CREATE TYPE participant_role AS ENUM (
    'primary',          -- Main agent for this conversation
    'invited',          -- Added to multi-agent conversation
    'handoff_source'    -- Was primary before handoff
);
```

## Implementation Details

### 7.1 Expert Gate (MoE Agent Routing)

The **Expert Gate** replaces the simple AgentRouter with a full Mixture of Experts (MoE) system that scores agents on 4 signals and supports multiple selection strategies.

#### 7.1.1 Baseline: Simple AgentRouter

```python
class AgentRouter:
    """
    BASELINE: Simple skill-based routing (used when enable_expert_gate=False).

    Users can address agents directly ("@kyra help me with...") or
    let the router decide based on skill matching and conversation context.
    """

    async def route(
        self,
        message: str,
        team_id: UUID,
        user_id: UUID,
        current_agent_slug: Optional[str] = None,
    ) -> RoutingDecision:
        """
        Determine which agent should handle this message.

        Strategy:
        1. If user @mentions an agent -> route directly
        2. If current_agent can handle it (has matching skills) -> keep
        3. Score all active agents by skill relevance -> pick best
        4. If no good match -> use team's default agent

        Returns RoutingDecision with:
        - agent_slug: str
        - confidence: float
        - reason: str ("user_mention", "skill_match", "handoff", "default")
        """
```

#### 7.1.2 MoE Expert Gate (4-Signal Scoring)

```python
class ExpertGate:
    """
    Multi-signal gate network for agent selection (MoE Layer 1).

    Replaces the simple AgentRouter with 4-signal scoring
    and configurable selection strategies. Enabled via feature flag.
    """

    async def score_experts(
        self,
        query: str,
        team_id: UUID,
        context: ConversationContext,
    ) -> list[ExpertScore]:
        """
        Score all active agents on 4 signals (weights sum to 1.0):

        1. **Skill match (weight 0.40)**: TF-IDF + embedding similarity
           against agent's effective_skills descriptions. Uses the same
           embeddings as memory retrieval (OpenAI text-embedding-3-small).

        2. **Past performance (weight 0.25)**: Average feedback_rating on
           similar queries over last 30 days. Queries are "similar" if
           cosine similarity > 0.8. New agents default to 0.7 (neutral).

        3. **Personality fit (weight 0.20)**: Tone/style match between
           query and agent personality. Measures formality, humor,
           technical depth. Uses lightweight classifier (Tier 0 model).

        4. **Load balancing (weight 0.15)**: Penalizes agents with high
           active_conversations_count, slow avg_response_latency_ms, or
           deep queue_depth. Ensures fair distribution.

        Returns:
            List of ExpertScore objects sorted by overall score (descending).
            Each score includes per-signal breakdown + explanation.
        """


class ExpertScore(BaseModel):
    """Individual expert's score on all 4 signals."""
    agent_slug: str
    agent_name: str
    skill_match: float = Field(ge=0.0, le=1.0, description="Skill relevance (0.40 weight)")
    past_performance: float = Field(ge=0.0, le=1.0, description="Historical success (0.25 weight)")
    personality_fit: float = Field(ge=0.0, le=1.0, description="Tone/style match (0.20 weight)")
    load_balance: float = Field(ge=0.0, le=1.0, description="Availability (0.15 weight)")
    overall: float = Field(ge=0.0, le=1.0, description="Weighted sum of all signals")
    matching_skills: list[str] = Field(description="Skills that matched the query")
    explanation: str = Field(description="Human-readable reason for this score")


class SelectionStrategy(str, Enum):
    """How to select agents from scored experts."""
    TOP_1 = "top_1"           # Route to single best agent (default)
    TOP_K = "top_k"           # Consult K agents, pick best response
    ENSEMBLE = "ensemble"     # Combine responses from multiple agents
    CASCADE = "cascade"       # Try agents in order until one succeeds


class ExpertSelector:
    """Apply selection strategy to expert scores."""

    async def select(
        self,
        scores: list[ExpertScore],
        strategy: SelectionStrategy = SelectionStrategy.TOP_1,
        k: int = 3,
        confidence_threshold: float = 0.6,
    ) -> SelectionResult:
        """
        Apply selection strategy to scored experts.

        Rules:
        - If best score < confidence_threshold → use default agent + warn user
        - TOP_1: Return highest scoring agent
        - TOP_K: Return top K agents for parallel execution (pick best response)
        - ENSEMBLE: Return all agents above threshold for parallel + aggregation
        - CASCADE: Return ordered list for sequential try (stop on first success)

        Returns:
            SelectionResult with selected agents, strategy, confidence,
            and fallback_used flag.
        """


class ResponseAggregator:
    """Combine responses from multiple experts (ENSEMBLE/TOP_K modes)."""

    async def aggregate(
        self,
        responses: list[ExpertResponse],
        query: str,
    ) -> AggregatedResponse:
        """
        Synthesize multiple expert responses into a coherent answer.

        Process:
        1. Score each response on relevance (0-1) using Tier 1 model
        2. Dedup overlapping content (semantic similarity > 0.9)
        3. Merge complementary insights from different experts
        4. Attribute sources: "According to Luke (code review)..."
        5. Return synthesized response with full attribution

        Uses meta-model call (Tier 1) to generate final synthesis.
        Preserves individual expert identities for transparency.
        """
```

#### 7.1.3 Expert Gate Flow Diagram

```
User: "Help me optimize this SQL query"
    │
    ├─► ExpertGate.score_experts()
    │     │
    │     ├─ Kyra (general):
    │     │    skill_match=0.2, past_perf=0.7, personality=0.6, load=0.9
    │     │    → overall = 0.2*0.4 + 0.7*0.25 + 0.6*0.2 + 0.9*0.15 = 0.51
    │     │
    │     ├─ Luke (code review):
    │     │    skill_match=0.9, past_perf=0.8, personality=0.8, load=0.7
    │     │    → overall = 0.9*0.4 + 0.8*0.25 + 0.8*0.2 + 0.7*0.15 = 0.83
    │     │
    │     └─ Ada (data analyst):
    │          skill_match=0.8, past_perf=0.9, personality=0.7, load=0.8
    │          → overall = 0.8*0.4 + 0.9*0.25 + 0.7*0.2 + 0.8*0.15 = 0.81
    │
    ├─► ExpertSelector.select(strategy=TOP_1, threshold=0.6)
    │     └─ Selected: Luke (0.83 > 0.6) ✓
    │
    ├─► Log decision to routing_decision_log
    │     {team_id, strategy="top_1", scores=[...], selected_agents=["luke"],
    │      confidence_threshold=0.6, fallback_used=false}
    │
    └─► Route message to Luke
```

#### 7.1.4 ENSEMBLE Mode Flow

```
User: "Help me plan a microservices migration"
    │
    ├─► ExpertGate.score_experts()
    │     ├─ Luke (code):         overall=0.85
    │     ├─ Ada (data):          overall=0.78
    │     └─ Zara (architecture): overall=0.92
    │
    ├─► ExpertSelector.select(strategy=ENSEMBLE, threshold=0.7)
    │     └─ Selected: [Zara, Luke, Ada] (all above 0.7)
    │
    ├─► Execute in parallel:
    │     ├─ Zara: "Start by defining service boundaries..."
    │     ├─ Luke: "Code review is critical during migration..."
    │     └─ Ada:  "Monitor data consistency across services..."
    │
    ├─► ResponseAggregator.aggregate([zara_response, luke_response, ada_response])
    │     │
    │     ├─ Score relevance (Tier 1 model)
    │     ├─ Dedup overlapping content
    │     ├─ Merge complementary insights
    │     └─ Generate synthesis with attribution
    │
    └─► Return: "According to Zara (architecture), start by defining
                 service boundaries... Luke (code review) emphasizes...
                 Ada (data analyst) recommends monitoring..."
```

### 7.2 Agent-to-Agent Handoff

When an agent encounters a question outside its expertise:

```
User asks Kyra about code review
    |
    +-> Kyra recognizes: "code_review" skill is Luke's specialty
    |
    +-> Kyra responds: "Great question! Let me bring in Luke -- he's our
    |   code review specialist. Luke, Sarah is asking about..."
    |
    +-> System creates handoff record:
    |   {from_agent: "kyra", to_agent: "luke", reason: "skill_match",
    |    context_summary: "User needs code review help", conversation_id: "..."}
    |
    +-> Luke receives:
    |   - Full conversation history (from message table)
    |   - Kyra's handoff context summary
    |   - User profile memories (shared across agents)
    |   - Luke's own identity + private memories
    |
    +-> Conversation continues with Luke
        (user can switch back: "@kyra" or "go back to Kyra")
```

```python
class HandoffManager:
    """Manage agent-to-agent conversation transfers."""

    async def initiate_handoff(
        self,
        from_agent_id: UUID,
        to_agent_slug: str,
        conversation_id: UUID,
        reason: str,
        context_summary: str,
    ) -> HandoffResult:
        """
        Transfer conversation to another agent.

        Creates shared episodic memory:
        "Kyra handed off to Luke because: [reason]"
        visible to both agents.
        """

    async def return_to_previous(
        self, conversation_id: UUID
    ) -> HandoffResult:
        """Return to the agent before the last handoff."""
```

### 7.3 Multi-Agent Conversations

A single conversation with multiple agents participating:

```
User: "I need help planning a dinner party"
    |
    +-> Kyra (general): "I'd love to help! Let me pull in some specialists."
    |
    +-> Kyra invites Ada (data) + Chef (recipes):
    |   POST /v1/conversations/{id}/agents
    |   {"add": ["ada", "chef"]}
    |
    +-> System tags messages with responding agent:
    |   {role: "assistant", agent_slug: "kyra", content: "..."}
    |   {role: "assistant", agent_slug: "chef", content: "..."}
    |
    +-> Each agent sees:
        - Full conversation (all agents' messages)
        - Their own identity + private memories
        - Shared memories visible to team
        - User profile (shared)
```

```python
# Database addition
class ConversationParticipant(Base):
    """Track which agents participate in a conversation."""
    conversation_id: UUID   # FK conversation
    agent_id: UUID          # FK agent
    role: str               # "primary", "invited", "handoff_source"
    joined_at: datetime
    left_at: Optional[datetime]

# Message table update
# ALTER TABLE message ADD COLUMN agent_id UUID REFERENCES agent(id);
# (Which agent authored this message -- NULL for user/system messages)
```

### 7.4 Team Memory Bus

When one agent learns something team-relevant, it should be available to all agents:

```
Kyra learns: "User's company switched to PostgreSQL"
    |
    +-> MemoryExtractor classifies: memory_type='shared' (team-relevant fact)
    |
    +-> Stored with: agent_id=NULL, team_id=team_123
    |
    +-> Hot cache invalidated for all agents in team
    |   (they'll pick up the new shared memory on next retrieval)
    |
    +-> All agents now know about the PostgreSQL switch
        without any explicit "tell Luke about this"
```

This happens automatically via the memory extraction pipeline (Phase 2). The agent router and handoff system just ensure that agents can seamlessly transfer context when conversations cross expertise boundaries.

### 7.5 Agent Discovery API

```python
# GET /v1/agents/recommend?query="help me review this code"
class AgentRecommendation(BaseModel):
    slug: str
    name: str
    confidence: float       # How well this agent matches the query
    matching_skills: list[str]  # Skills that matched
    tagline: str
    personality_preview: str  # First 100 chars of personality description

# Returns top 3 agents sorted by confidence
# Used by UIs to suggest "You might want to talk to Luke for this"
```

---

## Full Agent Collaboration Protocol (Section 3D from Master Plan)

This section expands agent collaboration beyond simple handoff and routing. Agents become **autonomous collaborators** that can delegate work, request reports, coordinate multi-step workflows, and learn from each other's results.

### The Five Collaboration Capabilities

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT COLLABORATION STACK                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  5. COLLABORATION SESSIONS                                          │
│     Multi-agent workflows with defined patterns                     │
│     (supervisor-worker, pipeline, peer-review, brainstorm)         │
│                                                                     │
│  4. REPORT SYSTEM                                                   │
│     Structured analysis requests with typed deliverables            │
│     (code_review, research_summary, risk_assessment, data_analysis)│
│                                                                     │
│  3. TASK DELEGATION                                                 │
│     Agent assigns sub-task to specialist, receives result           │
│     (async via Celery, max depth 3, budget-bounded)                │
│                                                                     │
│  2. AGENT MESSAGING                                                 │
│     Point-to-point and broadcast inter-agent communication          │
│     (direct, team channel, task channel)                           │
│                                                                     │
│  1. AGENT DISCOVERY                                                 │
│     Find the right agent for a capability                           │
│     (skill search, availability check, load balancing)             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Safety Constraints (Non-Negotiable)

These prevent runaway agent chains, cost explosions, and deadlocks:

```
┌────────────────────────┬──────────────┬──────────────────────────────────┐
│ Constraint             │ Default      │ Why                              │
├────────────────────────┼──────────────┼──────────────────────────────────┤
│ Max delegation depth   │ 3            │ A→B→C→D max, prevents loops     │
│ Max concurrent tasks   │ 5 per agent  │ Prevents single agent overload   │
│ Task timeout           │ 120s         │ No indefinite waits              │
│ Collaboration timeout  │ 600s         │ Multi-agent sessions time-boxed  │
│ Per-task token budget  │ 4000         │ Cost containment per sub-task    │
│ Per-collab cost cap    │ $0.50        │ Total collaboration spend limit  │
│ Max tool calls/task    │ 10           │ Prevents runaway tool usage      │
│ Cycle detection        │ Enabled      │ A→B→A immediately fails         │
│ Dead-letter queue      │ After 2 retries│ Failed tasks don't block chain │
└────────────────────────┴──────────────┴──────────────────────────────────┘
```

### Capability 1: Agent Discovery

Before an agent can delegate or collaborate, it needs to discover who can help:

```python
class AgentDirectory:
    """
    Registry of agents and their capabilities.

    Every agent's AgentDNA is the source of truth. The directory
    provides fast lookups by skill, availability, and load.
    """

    async def find_experts(
        self,
        required_skills: list[str],
        team_id: UUID,
        exclude_agent_ids: list[UUID] = [],
    ) -> list[AgentProfile]:
        """
        Find agents that have the required skills.

        Args:
            required_skills: Skills needed (e.g., ["code_review", "python"])
            team_id: Scope to this team
            exclude_agent_ids: Don't include these (e.g., the requesting agent)

        Returns:
            Agents sorted by: skill coverage, availability, load (lowest first)
        """

    async def check_availability(
        self, agent_id: UUID
    ) -> AgentAvailability:
        """
        Check if an agent can accept new work.

        Returns:
            AgentAvailability with:
            - available: bool
            - active_tasks: int (current in-progress tasks)
            - active_conversations: int
            - estimated_wait_seconds: int
            - reason: str (why unavailable, if applicable)
        """


class AgentProfile(BaseModel):
    """Lightweight view of an agent for discovery."""
    agent_id: UUID
    slug: str
    name: str
    tagline: str
    effective_skills: list[str]
    active_tasks: int
    status: AgentStatus
    skill_coverage: float           # What % of required skills this agent has
```

### Capability 2: Agent Messaging

Internal communication channel between agents. These messages are **not** user-visible (unless the agent chooses to surface them).

```python
class AgentMessageBus:
    """
    Inter-agent messaging system.

    Messages are persisted in the agent_message table and delivered
    via Redis pub/sub for real-time notification. Agents receive
    messages through their tool interface.
    """

    async def send(
        self,
        from_agent_id: UUID,
        to_agent_id: UUID,
        message_type: AgentMessageType,
        content: str,
        metadata: dict[str, Any] = {},
        channel: str = "direct",
    ) -> AgentMessage:
        """
        Send a message to another agent.

        Channels:
        - "direct": Point-to-point (only recipient sees it)
        - "team": All agents in the team receive it
        - "task:{task_id}": All agents working on a task
        - "collab:{session_id}": All collaboration participants
        """

    async def broadcast(
        self,
        from_agent_id: UUID,
        team_id: UUID,
        message_type: AgentMessageType,
        content: str,
    ) -> list[AgentMessage]:
        """Broadcast to all active agents in a team."""

    async def get_inbox(
        self,
        agent_id: UUID,
        unread_only: bool = True,
        limit: int = 10,
    ) -> list[AgentMessage]:
        """Get pending messages for an agent."""


class AgentMessageType(str, Enum):
    """Types of inter-agent messages."""
    TASK_REQUEST = "task_request"           # "Can you do this for me?"
    TASK_RESULT = "task_result"             # "Here's what I found"
    TASK_STATUS = "task_status"             # "Working on it" / "Blocked"
    INFO_REQUEST = "info_request"           # "What do you know about X?"
    INFO_RESPONSE = "info_response"        # "Here's what I know"
    NOTIFICATION = "notification"           # "FYI: user preferences changed"
    COLLABORATION_INVITE = "collab_invite"  # "Join this collaboration session"
    COLLABORATION_UPDATE = "collab_update"  # "Stage 2 complete, starting stage 3"
    HANDOFF_REQUEST = "handoff_request"     # "Can you take over this conversation?"
    FEEDBACK = "feedback"                   # "Your analysis missed X"
```

### Capability 3: Task Delegation (THE CORE)

The core mechanism: an agent creates a structured task, assigns it to a specialist, and receives the result.

```python
class AgentTask(BaseModel):
    """A task assigned by one agent to another."""
    id: UUID
    team_id: UUID

    # Who
    created_by_agent_id: UUID        # The delegating agent
    assigned_to_agent_id: UUID       # The worker agent
    conversation_id: Optional[UUID]  # Originating user conversation (for context)
    parent_task_id: Optional[UUID]   # Sub-delegation chains

    # What
    task_type: AgentTaskType         # research, review, analyze, generate, summarize, validate
    title: str                       # "Review the authentication module"
    instructions: str                # Detailed instructions from delegating agent
    context: str                     # Relevant context (conversation summary, prior findings)
    expected_output: str             # "A structured code review with severity ratings"
    input_artifacts: list[str]       # File paths, memory IDs, or data passed to worker

    # Constraints
    priority: TaskPriority           # low, normal, high, urgent
    max_tokens: int = 4000           # Token budget for this task
    max_tool_calls: int = 10         # Tool call limit
    timeout_seconds: int = 120       # Max execution time
    model_tier: Optional[str] = None # Force specific model tier, or None for auto (MoE)

    # Status
    status: AgentTaskStatus
    result: Optional[str]            # The deliverable
    result_artifacts: list[str] = [] # Output files, memory IDs created
    error: Optional[str]             # Error message if failed
    delegation_depth: int = 0        # How deep in the delegation chain (max 3)

    # Cost tracking
    tokens_used: int = 0
    cost_usd: float = 0

    # Timing
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class AgentTaskType(str, Enum):
    RESEARCH = "research"           # Gather information on a topic
    REVIEW = "review"               # Review code, content, or plan
    ANALYZE = "analyze"             # Analyze data, logs, or patterns
    GENERATE = "generate"           # Generate code, content, or documents
    SUMMARIZE = "summarize"         # Summarize information
    VALIDATE = "validate"           # Validate assumptions or outputs
    PLAN = "plan"                   # Create a plan or strategy
    EXECUTE = "execute"             # Execute a defined procedure


class AgentTaskStatus(str, Enum):
    PENDING = "pending"             # Created, waiting to be picked up
    IN_PROGRESS = "in_progress"     # Worker agent is executing
    COMPLETED = "completed"         # Successfully finished
    FAILED = "failed"               # Failed after retries
    CANCELLED = "cancelled"         # Cancelled by delegating agent
    TIMED_OUT = "timed_out"         # Exceeded timeout_seconds


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"              # Preempts lower-priority work


class TaskDelegator:
    """
    Manages task lifecycle between agents.

    Safety:
    - Validates delegation_depth < MAX_DEPTH (3)
    - Detects cycles (A→B→A)
    - Enforces per-task and per-collaboration budgets
    - Routes via Celery for async execution
    """

    MAX_DELEGATION_DEPTH: ClassVar[int] = 3
    MAX_CONCURRENT_TASKS: ClassVar[int] = 5

    async def delegate(
        self,
        from_agent_id: UUID,
        to_agent_slug: str,
        task: AgentTaskCreate,
        parent_task_id: Optional[UUID] = None,
    ) -> AgentTask:
        """
        Create and dispatch a task to another agent.

        Flow:
        1. Validate: depth < 3, no cycles, worker available, budget OK
        2. Create AgentTask record (status=pending)
        3. Dispatch via Celery: execute_agent_task.delay(task_id)
        4. Return task (caller can poll or await result)

        Raises:
            DelegationDepthExceeded: If depth >= MAX_DEPTH
            CycleDetected: If delegation would create A→B→A loop
            AgentUnavailable: If target agent is paused/archived
            BudgetExhausted: If collaboration cost cap reached
        """

    async def get_result(
        self,
        task_id: UUID,
        timeout_seconds: int = 120,
    ) -> AgentTask:
        """
        Wait for a delegated task to complete.

        Uses Redis pub/sub for real-time notification.
        Falls back to polling if pub/sub unavailable.
        """

    async def cancel(self, task_id: UUID, reason: str) -> None:
        """Cancel a pending or in-progress task."""
```

#### Delegation Flow Diagram

```
User: "Create a comprehensive security audit of our authentication system"
    │
    ├─► Kyra (general) receives message
    │
    ├─► Kyra decides this needs specialist help:
    │   Uses delegate_task tool internally:
    │
    │   ┌──────────────────────────────────────────────────────┐
    │   │ Task 1 → Luke (code, depth=1)                       │
    │   │   type: review                                       │
    │   │   title: "Review auth module code quality"           │
    │   │   instructions: "Review src/auth/ for security       │
    │   │     vulnerabilities, focusing on: password hashing,  │
    │   │     JWT implementation, API key storage, input        │
    │   │     validation, rate limiting"                        │
    │   │   expected_output: "Severity-rated findings list"     │
    │   ├──────────────────────────────────────────────────────┤
    │   │ Task 2 → Ada (data, depth=1)                        │
    │   │   type: analyze                                      │
    │   │   title: "Analyze authentication logs for anomalies" │
    │   │   instructions: "Look at recent auth logs for:       │
    │   │     brute force patterns, unusual login times,       │
    │   │     geographic anomalies, token reuse"               │
    │   │   expected_output: "Anomaly report with risk scores" │
    │   └──────────────────────────────────────────────────────┘
    │
    │   (Both tasks execute in parallel via Celery)
    │
    ├─► Luke completes Task 1:
    │   result: "Found 3 issues: [HIGH] bcrypt rounds too low (8, need 12),
    │            [MEDIUM] JWT refresh token not rotated on use,
    │            [LOW] API key displayed in plain text on creation response"
    │
    ├─► Ada completes Task 2:
    │   result: "No brute force detected. 2 anomalies: login from
    │            unexpected country (Russia), 3 failed attempts from
    │            same IP in 10 seconds"
    │
    └─► Kyra synthesizes both results into a comprehensive audit report
        for the user, with severity ratings and recommended fixes.
```

#### Sub-Delegation (Depth > 1)

```
Kyra (depth=0) delegates to Luke (depth=1):
    "Review the auth module"
    │
    Luke recognizes he needs test coverage data:
    │
    └─► Luke delegates to Ada (depth=2):
        "Run test coverage analysis on src/auth/"
        │
        Ada runs analysis and returns:
        └─► "Coverage: 67%. Untested: password_reset(), api_key_rotate()"
    │
    Luke incorporates coverage data into his review
    and returns complete result to Kyra.

    ⚠️ Ada CANNOT sub-delegate further (depth=2, max=3 would allow it,
       but depth=3 is the absolute max).
```

### Capability 4: Report System

Structured analysis requests with typed deliverables. Reports are reusable templates that agents can request from each other.

```python
class ReportType(str, Enum):
    """Pre-defined report templates."""
    CODE_REVIEW = "code_review"
    SECURITY_AUDIT = "security_audit"
    RESEARCH_SUMMARY = "research_summary"
    DATA_ANALYSIS = "data_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    PERFORMANCE_REPORT = "performance_report"
    COMPARISON = "comparison"
    ACTION_PLAN = "action_plan"


class ReportRequest(BaseModel):
    """Structured request for a report from another agent."""
    report_type: ReportType
    title: str
    parameters: dict[str, Any]      # Report-specific params
    # e.g., for code_review: {"files": ["src/auth/"], "focus": ["security", "performance"]}
    # e.g., for research_summary: {"topic": "JWT best practices", "depth": "comprehensive"}
    # e.g., for comparison: {"options": ["Redis", "Memcached"], "criteria": ["speed", "features"]}
    max_sections: int = 10
    format: Literal["markdown", "json", "bullet_points"] = "markdown"


class ReportTemplate(BaseModel):
    """Template that defines the structure of a report type."""
    report_type: ReportType
    required_sections: list[str]
    optional_sections: list[str]
    output_schema: Optional[dict[str, Any]]  # JSON schema for structured output


# Pre-defined templates
REPORT_TEMPLATES: dict[ReportType, ReportTemplate] = {
    ReportType.CODE_REVIEW: ReportTemplate(
        report_type=ReportType.CODE_REVIEW,
        required_sections=["summary", "findings", "severity_breakdown", "recommendations"],
        optional_sections=["test_coverage", "performance_notes", "security_notes"],
        output_schema=None,
    ),
    ReportType.RESEARCH_SUMMARY: ReportTemplate(
        report_type=ReportType.RESEARCH_SUMMARY,
        required_sections=["executive_summary", "findings", "sources", "recommendations"],
        optional_sections=["methodology", "limitations", "next_steps"],
        output_schema=None,
    ),
    ReportType.RISK_ASSESSMENT: ReportTemplate(
        report_type=ReportType.RISK_ASSESSMENT,
        required_sections=["risk_matrix", "identified_risks", "mitigations", "residual_risk"],
        optional_sections=["probability_analysis", "impact_analysis", "historical_context"],
        output_schema=None,
    ),
}


class ReportManager:
    """
    Manages report requests between agents.

    A report request is internally a specialized AgentTask with
    task_type=REVIEW or ANALYZE, plus the report template structure
    injected into the instructions.
    """

    async def request_report(
        self,
        from_agent_id: UUID,
        to_agent_slug: str,
        request: ReportRequest,
    ) -> AgentTask:
        """
        Request a structured report from a specialist agent.

        Converts the ReportRequest into an AgentTask with:
        - instructions: template sections + parameters
        - expected_output: structured report matching template
        - model_tier: "balanced" or "powerful" based on report complexity
        """

    async def get_report(self, task_id: UUID) -> Report:
        """
        Retrieve completed report with structured sections.

        Parses the agent's result into Report sections,
        validates against template, and stores as a memory
        (type=procedural) for future reference.
        """
```

### Capability 5: Collaboration Sessions

Multi-agent workflows with defined patterns. A collaboration session coordinates multiple agents toward a shared goal.

```python
class CollaborationPattern(str, Enum):
    """Defines how agents interact in a collaboration."""

    SUPERVISOR_WORKER = "supervisor_worker"
    # One lead agent coordinates, assigns tasks to workers, synthesizes results.
    # Best for: complex tasks requiring multiple specialists
    #
    # Flow: Lead → assign tasks → Workers execute → Lead synthesizes
    # Example: "Create marketing strategy" → research + data + content agents

    PIPELINE = "pipeline"
    # Sequential stages, each agent's output feeds the next.
    # Best for: workflows with ordered dependencies
    #
    # Flow: Stage 1 → output → Stage 2 → output → Stage 3 → final output
    # Example: "Review code" → Luke (quality) → Ada (security) → Kyra (summary)

    PEER_REVIEW = "peer_review"
    # One agent does work, another reviews, iterate until approved.
    # Best for: quality-critical deliverables
    #
    # Flow: Worker produces → Reviewer checks → approve or request changes → loop
    # Example: "Write API docs" → Max writes → Luke reviews → Max revises

    BRAINSTORM = "brainstorm"
    # Multiple agents contribute perspectives in parallel, then synthesized.
    # Best for: creative problems, strategy, exploring options
    #
    # Flow: All agents respond in parallel → Lead synthesizes perspectives
    # Example: "How should we approach caching?" → each agent's perspective

    CONSENSUS = "consensus"
    # Agents independently assess, then converge on agreement.
    # Best for: critical decisions, risk assessment
    #
    # Flow: All agents assess independently → compare → resolve disagreements
    # Example: "Is this API design secure?" → each agent votes + reasoning

    DELEGATION = "delegation"
    # Simple one-off task assignment (lightweight, no session overhead).
    # Best for: quick specialist queries
    #
    # Flow: Agent A asks Agent B → B responds → done
    # Example: "What's the test coverage for this module?"


class CollaborationSession(BaseModel):
    """A multi-agent collaboration session."""
    id: UUID
    team_id: UUID
    conversation_id: Optional[UUID]  # User conversation that triggered this

    # Configuration
    pattern: CollaborationPattern
    lead_agent_id: UUID              # The coordinating agent
    goal: str                        # "Create comprehensive security audit"
    context: str                     # Background context for all participants

    # Participants
    participants: list[CollaborationParticipantInfo]

    # Constraints
    max_duration_seconds: int = 600
    max_total_cost_usd: float = 0.50
    max_rounds: int = 5              # Max iteration rounds (for PEER_REVIEW)

    # Status
    status: CollaborationStatus
    current_stage: Optional[str]     # For PIPELINE: which stage we're on
    stages_completed: int = 0
    total_cost_usd: float = 0.0

    # Results
    final_output: Optional[str]
    stage_outputs: list[StageOutput] = []  # Output from each stage/participant

    # Timing
    created_at: datetime
    completed_at: Optional[datetime]


class CollaborationParticipantInfo(BaseModel):
    """Participant in a collaboration session."""
    agent_id: UUID
    agent_slug: str
    role: str                        # "lead", "worker", "reviewer", "contributor"
    stage: Optional[int]             # For PIPELINE: which stage (1, 2, 3...)
    task_id: Optional[UUID]          # Their assigned task
    status: str                      # "waiting", "working", "completed", "failed"


class CollaborationStatus(str, Enum):
    PLANNING = "planning"            # Lead agent is setting up
    ACTIVE = "active"                # In progress
    SYNTHESIZING = "synthesizing"    # Lead is combining results
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class StageOutput(BaseModel):
    """Output from one stage or participant in a collaboration."""
    stage: int
    agent_slug: str
    output: str
    tokens_used: int
    cost_usd: float
    duration_seconds: float


class CollaborationOrchestrator:
    """
    Orchestrates multi-agent collaboration sessions.

    Agents don't call this directly -- they use collaboration tools
    (start_collaboration, join_collaboration, submit_stage_output).
    The orchestrator manages the flow.
    """

    async def start(
        self,
        lead_agent_id: UUID,
        pattern: CollaborationPattern,
        goal: str,
        context: str,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """
        Start a new collaboration session.

        Validates:
        - All participants exist and are active
        - Lead agent has authority (any active agent can lead)
        - Budget is within team limits
        - Pattern is valid for participant count

        For PIPELINE: creates stages in order, first stage starts immediately
        For SUPERVISOR_WORKER: creates tasks for all workers in parallel
        For PEER_REVIEW: creates initial task for worker
        For BRAINSTORM: sends prompt to all participants in parallel
        For CONSENSUS: sends assessment prompt to all participants
        """

    async def advance(self, session_id: UUID) -> CollaborationSession:
        """
        Advance the collaboration to the next stage.

        Called automatically when a stage completes.
        For PIPELINE: starts next stage with previous output as input
        For PEER_REVIEW: sends output to reviewer, or applies feedback
        For BRAINSTORM/CONSENSUS: triggers synthesis when all respond
        """

    async def synthesize(self, session_id: UUID) -> str:
        """
        Have the lead agent synthesize all participant outputs.

        The lead receives all stage outputs and produces a final
        combined response. This is the last step before COMPLETED.
        """
```

#### Collaboration Pattern Flows

**Supervisor-Worker** (most common):
```
User: "Create a comprehensive marketing strategy for our developer tool"
    │
    ├─► Kyra (lead) starts CollaborationSession:
    │   pattern: SUPERVISOR_WORKER
    │   participants: [Max (marketing), Ada (data), Luke (tech)]
    │
    │   ┌── PARALLEL EXECUTION ──────────────────────────┐
    │   │                                                 │
    │   │  Max (worker): "Draft strategy + channels"     │
    │   │  Ada (worker): "Market research + data"        │
    │   │  Luke (worker): "Technical feasibility"        │
    │   │                                                 │
    │   └── ALL COMPLETE ────────────────────────────────┘
    │
    ├─► Kyra (lead) receives 3 outputs:
    │   ├─ Max: "Focus on dev communities, content marketing, OSS sponsorships"
    │   ├─ Ada: "TAM: 25M devs, competitors spend $50K/mo on content"
    │   └─ Luke: "Our API supports webhook integrations for Slack/Discord"
    │
    └─► Kyra synthesizes final strategy for user
        (combining marketing + data + technical perspectives)
```

**Pipeline** (sequential stages):
```
User: "Review and ship this PR"
    │
    ├─► Kyra starts Pipeline:
    │   Stage 1: Luke (code quality)
    │   Stage 2: Max (security review, receives Luke's findings)
    │   Stage 3: Ada (test coverage, receives Luke + Max findings)
    │   Stage 4: Kyra (final go/no-go, receives all findings)
    │
    │   Luke ──► Max ──► Ada ──► Kyra
    │   (each stage receives all previous outputs)
    │
    └─► Kyra: "Ship it. Luke found 2 minor style issues (auto-fixed).
        Max found no security concerns. Ada confirmed 89% coverage."
```

### Agent Collaboration Tools

Agents interact with the collaboration system through registered tools:

```python
# These tools are registered on every agent that has collaboration enabled

@agent.tool
async def delegate_task(
    ctx: RunContext[AgentDependencies],
    to_agent: str,                   # Agent slug
    task_type: str,                  # research, review, analyze, generate, etc.
    title: str,                      # Short title
    instructions: str,               # What to do
    expected_output: str,            # What the result should look like
    priority: str = "normal",        # low, normal, high, urgent
    wait_for_result: bool = True,    # Block until done, or fire-and-forget
) -> str:
    """
    Delegate a task to a specialist agent and get their result.

    Use when:
    - You need expertise you don't have (e.g., code review, data analysis)
    - The task can be clearly defined for another agent
    - You want a specialist's perspective on a sub-problem

    The target agent works independently with its own context and tools,
    then returns a structured result.
    """


@agent.tool
async def request_report(
    ctx: RunContext[AgentDependencies],
    from_agent: str,                 # Agent slug of the specialist
    report_type: str,                # code_review, research_summary, risk_assessment, etc.
    title: str,
    parameters: str,                 # JSON string of report-specific parameters
) -> str:
    """
    Request a structured report from a specialist agent.

    Reports follow pre-defined templates with required sections.
    Use for formal, structured analysis rather than ad-hoc questions.
    """


@agent.tool
async def start_collaboration(
    ctx: RunContext[AgentDependencies],
    pattern: str,                    # supervisor_worker, pipeline, peer_review, brainstorm, consensus
    goal: str,                       # What this collaboration aims to achieve
    participants: str,               # JSON: [{"slug": "luke", "role": "worker"}, ...]
) -> str:
    """
    Start a multi-agent collaboration session.

    Use when:
    - A task needs multiple specialists working together
    - You need different perspectives combined
    - The work has clear stages or roles

    You (the calling agent) become the lead and will synthesize results.
    """


@agent.tool
async def check_task_status(
    ctx: RunContext[AgentDependencies],
    task_id: str,
) -> str:
    """Check the status of a previously delegated task."""


@agent.tool
async def send_agent_message(
    ctx: RunContext[AgentDependencies],
    to_agent: str,                   # Agent slug
    message: str,
    message_type: str = "notification",
) -> str:
    """
    Send a message to another agent.

    Use for lightweight communication that doesn't require
    a formal task delegation. Good for notifications, FYIs,
    and quick questions.
    """


@agent.tool
async def get_agent_inbox(
    ctx: RunContext[AgentDependencies],
    unread_only: bool = True,
) -> str:
    """
    Check for messages from other agents.

    Returns pending messages, task results, and collaboration updates.
    """
```

### Collaboration Database Tables (4 New Tables)

```sql
-- 19. agent_task (task delegation between agents)
CREATE TABLE agent_task (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES conversation(id),

    -- Who
    created_by_agent_id UUID NOT NULL REFERENCES agent(id),
    assigned_to_agent_id UUID NOT NULL REFERENCES agent(id),
    parent_task_id      UUID REFERENCES agent_task(id),  -- For sub-delegation chains

    -- What
    task_type           TEXT NOT NULL,       -- 'research', 'review', 'analyze', etc.
    title               TEXT NOT NULL,
    instructions        TEXT NOT NULL,
    context             TEXT,
    expected_output     TEXT,
    input_artifacts     JSONB NOT NULL DEFAULT '[]',

    -- Constraints
    priority            TEXT NOT NULL DEFAULT 'normal',
    max_tokens          INT NOT NULL DEFAULT 4000,
    max_tool_calls      INT NOT NULL DEFAULT 10,
    timeout_seconds     INT NOT NULL DEFAULT 120,
    model_tier          TEXT,               -- Force tier or NULL for auto
    delegation_depth    INT NOT NULL DEFAULT 0,

    -- Status
    status              TEXT NOT NULL DEFAULT 'pending',
    result              TEXT,
    result_artifacts    JSONB NOT NULL DEFAULT '[]',
    error               TEXT,

    -- Cost tracking
    tokens_used         INT NOT NULL DEFAULT 0,
    cost_usd            DECIMAL(10,6) NOT NULL DEFAULT 0,

    -- Timing
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    -- Safety
    CONSTRAINT max_delegation_depth CHECK (delegation_depth <= 3),
    CONSTRAINT no_self_delegation CHECK (created_by_agent_id != assigned_to_agent_id)
);


-- 20. agent_message (inter-agent communication)
CREATE TABLE agent_message (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    from_agent_id       UUID NOT NULL REFERENCES agent(id),
    to_agent_id         UUID REFERENCES agent(id),          -- NULL = broadcast
    channel             TEXT NOT NULL DEFAULT 'direct',      -- 'direct', 'team', 'task:{id}', 'collab:{id}'
    message_type        TEXT NOT NULL,                       -- See AgentMessageType enum
    content             TEXT NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}',
    read_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 21. collaboration_session (multi-agent workflows)
CREATE TABLE collaboration_session (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES conversation(id),
    lead_agent_id       UUID NOT NULL REFERENCES agent(id),

    -- Configuration
    pattern             TEXT NOT NULL,                       -- 'supervisor_worker', 'pipeline', etc.
    goal                TEXT NOT NULL,
    context             TEXT,
    max_duration_seconds INT NOT NULL DEFAULT 600,
    max_total_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0.50,
    max_rounds          INT NOT NULL DEFAULT 5,

    -- Status
    status              TEXT NOT NULL DEFAULT 'planning',
    current_stage       INT,
    stages_completed    INT NOT NULL DEFAULT 0,
    total_cost_usd      DECIMAL(10,6) NOT NULL DEFAULT 0,

    -- Results
    final_output        TEXT,
    stage_outputs       JSONB NOT NULL DEFAULT '[]',         -- [{stage, agent_slug, output, cost}]

    -- Timing
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);


-- 22. collaboration_participant_v2 (renamed to avoid conflict with conversation_participant)
CREATE TABLE collaboration_participant_v2 (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES collaboration_session(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    role                TEXT NOT NULL DEFAULT 'worker',      -- 'lead', 'worker', 'reviewer', 'contributor'
    stage               INT,                                 -- For PIPELINE: stage number
    task_id             UUID REFERENCES agent_task(id),
    status              TEXT NOT NULL DEFAULT 'waiting',     -- 'waiting', 'working', 'completed', 'failed'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_session_agent UNIQUE (session_id, agent_id)
);


-- Indexes
CREATE INDEX idx_agent_task_team ON agent_task (team_id, status, created_at DESC);
CREATE INDEX idx_agent_task_assignee ON agent_task (assigned_to_agent_id, status);
CREATE INDEX idx_agent_task_creator ON agent_task (created_by_agent_id, created_at DESC);
CREATE INDEX idx_agent_task_parent ON agent_task (parent_task_id)
    WHERE parent_task_id IS NOT NULL;
CREATE INDEX idx_agent_task_conversation ON agent_task (conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE INDEX idx_agent_message_recipient ON agent_message (to_agent_id, read_at)
    WHERE read_at IS NULL;
CREATE INDEX idx_agent_message_channel ON agent_message (channel, created_at DESC);
CREATE INDEX idx_agent_message_team ON agent_message (team_id, created_at DESC);

CREATE INDEX idx_collab_session_team ON collaboration_session (team_id, status, created_at DESC);
CREATE INDEX idx_collab_session_lead ON collaboration_session (lead_agent_id, status);
CREATE INDEX idx_collab_participant_session ON collaboration_participant_v2 (session_id, role);
CREATE INDEX idx_collab_participant_agent ON collaboration_participant_v2 (agent_id, status);
```

### Feature Flag Progression

```python
# src/settings.py -- FeatureFlags addition
class FeatureFlags(BaseModel):
    # ... existing flags ...
    enable_task_delegation: bool = Field(default=False)  # Phase 7: AgentTask system
    enable_collaboration: bool = Field(default=False)    # Phase 7: Full collaboration sessions
```

Feature flag progression for agent collaboration:
1. **Direct dispatch** (baseline, no flags): All messages route to a fixed agent
2. **Simple routing** (`enable_agent_collaboration=True`): AgentRouter with skill matching
3. **Expert gate** (`enable_expert_gate=True`): MoE 4-signal scoring
4. **Task delegation** (`enable_task_delegation=True`): Agents can delegate via delegate_task tool
5. **Full collaboration** (`enable_collaboration=True`): All 5 collaboration patterns active

## Tests

```
tests/test_collaboration/
    __init__.py
    test_agent_router.py             # Routing decisions, @mention parsing
    test_handoff.py                  # Agent-to-agent handoff, context preservation
    test_multi_agent.py              # Multi-participant conversations
    test_team_memory_bus.py          # Shared memory propagation
    test_agent_discovery.py          # Skill-based agent recommendation
    test_task_delegator.py           # Delegation, depth limits, cycles, timeouts
    test_agent_message_bus.py        # Direct, broadcast, inbox, channels
    test_report_manager.py           # Report request, templates, structured output
    test_collaboration_orchestrator.py  # All 5 patterns, cost caps, timeouts
```

### Key Test Scenarios

#### Baseline Routing (test_agent_router.py)
- @mention routing parses `@kyra` and directs to correct agent
- Skill-based routing scores all agents and picks the best match
- Default agent is used when no agent has a strong skill match
- Single-agent conversations (pre-Phase 7) still work identically (backward compatible)

#### MoE Expert Gate (test_expert_gate.py)
- ExpertGate.score_experts() returns scores for all active team agents
- Skill match signal uses TF-IDF + embeddings correctly
- Past performance signal queries similar conversations from last 30 days
- Personality fit signal measures tone/style match
- Load balance signal penalizes high-load agents
- Overall score is correct weighted sum (0.40 + 0.25 + 0.20 + 0.15 = 1.0)
- Scoring completes in < 100ms for team of 10 agents
- New agents without performance history default to 0.7 neutral score

#### Expert Selector (test_expert_selector.py)
- TOP_1 strategy selects highest scoring agent
- TOP_1 falls back to default agent when best score < threshold
- TOP_K strategy returns K highest scoring agents
- ENSEMBLE strategy returns all agents above threshold
- ENSEMBLE with no agents above threshold falls back to default agent
- CASCADE strategy returns agents ordered by score (descending)
- Selection result includes confidence, strategy, fallback_used flag

#### Response Aggregator (test_response_aggregator.py)
- Aggregates multiple expert responses into coherent synthesis
- Deduplicates overlapping content (semantic similarity > 0.9)
- Preserves complementary insights from different experts
- Attributes sources: "According to Luke (code review)..."
- Uses Tier 1 model for synthesis (cost-effective)

#### Routing Log (test_routing_log.py)
- Every routing decision is logged to routing_decision_log
- Log includes full scores JSONB, selected agents, strategy
- Log includes complexity_score and tier selection
- Log includes gate_latency_ms and router_latency_ms
- Analytics query: "Which agents are selected most often for 'code review' queries?"
- Analytics query: "What's the average confidence for ENSEMBLE mode?"

#### Handoff & Multi-Agent (test_handoff.py, test_multi_agent.py)
- Handoff creates correct `agent_handoff` record with context summary
- Handoff preserves full conversation history for the receiving agent
- User profile memories are shared across agents during handoff
- Receiving agent gets its own identity + private memories alongside shared context
- `return_to_previous()` correctly restores the prior agent
- Multi-agent conversation correctly tags each message with `agent_id`
- Adding agents to a conversation creates `conversation_participant` records
- Each agent in a multi-agent conversation sees full history from all agents

#### Team Memory Bus (test_team_memory_bus.py)
- Shared memory creation (agent_id=NULL) propagates to all agents in team
- Hot cache is invalidated for all team agents when shared memory is created

#### Agent Discovery (test_agent_discovery.py)
- Agent discovery returns top 3 agents sorted by confidence
- Agent discovery matches skills to query semantics

#### Task Delegation (test_task_delegator.py)
- Delegate task creates AgentTask record with correct fields
- Delegation depth enforced (max 3), deeper delegation fails with DelegationDepthExceeded
- Cycle detection prevents A→B→A loops (fails immediately with CycleDetected)
- Task timeout enforced (120s default), timed-out tasks marked TIMED_OUT
- Dead-letter queue moves failed tasks after 2 retries
- get_result() waits for task completion via Redis pub/sub
- cancel() marks task as CANCELLED and notifies worker agent

#### Agent Messaging (test_agent_message_bus.py)
- send() creates message and delivers via Redis pub/sub
- broadcast() sends to all active agents in team
- get_inbox() returns unread messages ordered by created_at DESC
- Channels work correctly: direct, team, task:{id}, collab:{id}
- read_at timestamp updates when agent reads message

#### Report System (test_report_manager.py)
- request_report() converts ReportRequest to AgentTask with template
- Report templates include required/optional sections
- get_report() parses result into structured Report object
- Report validates against template (missing required sections fail)
- Completed reports stored as procedural memory

#### Collaboration Orchestrator (test_collaboration_orchestrator.py)
- SUPERVISOR_WORKER pattern: parallel tasks, lead synthesizes
- PIPELINE pattern: sequential stages, output feeds next
- PEER_REVIEW pattern: worker→reviewer→revise loop until approved
- BRAINSTORM pattern: parallel perspectives, lead synthesizes
- CONSENSUS pattern: independent assess, converge on agreement
- Cost cap enforced ($0.50 default), session fails when exceeded
- Duration timeout enforced (600s default), session marked TIMED_OUT
- advance() moves to next stage correctly for each pattern
- synthesize() combines all stage outputs via lead agent

## Acceptance Criteria

### Baseline Routing (AgentRouter)
- [ ] @mention routing directs to correct agent
- [ ] Skill-based routing picks best agent for query
- [ ] Existing single-agent conversations unaffected (backward compatible)

### MoE Expert Gate
- [ ] ExpertGate scores all team agents on 4 signals in < 100ms
- [ ] TOP_1 strategy routes to highest-scoring agent correctly
- [ ] TOP_K strategy returns K agents and picks best response
- [ ] ENSEMBLE strategy combines responses with agent attribution
- [ ] CASCADE strategy tries agents in order, stops on first success
- [ ] Fallback to default agent when no expert meets confidence threshold (< 0.6)
- [ ] routing_decision_log records every routing decision with full scores
- [ ] Feature flag enable_expert_gate=False falls back to simple AgentRouter
- [ ] Feature flag enable_ensemble_mode=False disables multi-expert modes

### Collaboration Features (Handoff & Multi-Agent)
- [ ] Handoff preserves conversation history + user profile for target agent
- [ ] Multi-agent conversation shows per-agent attribution
- [ ] Shared memories propagate to all agents in team
- [ ] Agent discovery returns relevant recommendations

### Task Delegation
- [ ] Agents can delegate tasks to specialists via delegate_task tool
- [ ] Delegation depth enforced (max 3), cycle detection prevents A→B→A
- [ ] Task timeouts enforced (120s default), dead-letter after 2 retries
- [ ] Per-task token budget (4000 default) and tool call limit (10 default) enforced
- [ ] Task status polling works (get_result waits via Redis pub/sub)
- [ ] Task cancellation works (cancel marks CANCELLED and notifies worker)

### Agent Messaging
- [ ] Agent messaging works (direct + broadcast + channels)
- [ ] get_agent_inbox returns unread messages correctly
- [ ] Messages delivered via Redis pub/sub for real-time notification
- [ ] All message types supported (TASK_REQUEST, TASK_RESULT, INFO_REQUEST, etc.)

### Report System
- [ ] Report system produces structured deliverables matching templates
- [ ] All report types supported (CODE_REVIEW, RESEARCH_SUMMARY, RISK_ASSESSMENT, etc.)
- [ ] Reports validate against templates (required sections enforced)
- [ ] Completed reports stored as procedural memory

### Collaboration Sessions
- [ ] All 5 collaboration patterns work: supervisor-worker, pipeline, peer-review, brainstorm, consensus
- [ ] Collaboration sessions enforce cost caps ($0.50 default) and duration limits (600s default)
- [ ] advance() correctly moves sessions through stages for each pattern
- [ ] synthesize() combines participant outputs via lead agent
- [ ] Collaboration tools registered on all collaboration-enabled agents

## Critical Constraint

After this phase completes:

```bash
python -m src.cli                    # CLI still works
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
```

## Rollback Strategy

**Phase 7 (Collaboration)**: Delete router/handoff modules, revert message table (drop `agent_id` column), remove `conversation_participant` table.

**Database Migration Safety:**

```bash
# Before any migration in production:
1. Backup database: pg_dump -Fc skill_agent > backup_$(date +%Y%m%d).dump
2. Test migration on staging first
3. Run migration: alembic upgrade head
4. Verify: alembic current
5. If broken: alembic downgrade -1  (revert last migration)
6. If catastrophic: pg_restore -d skill_agent backup_YYYYMMDD.dump
```

**Feature Flags (backward compatibility)**:

- `enable_agent_collaboration` (default `False`): When disabled, all messages go through direct dispatch instead of the agent router. No collaboration features activate until explicitly enabled.

- `enable_expert_gate` (default `False`): When disabled, falls back to simple AgentRouter (skill matching only). When enabled, uses MoE 4-signal scoring.

- `enable_ensemble_mode` (default `False`): When disabled, only TOP_1 and CASCADE strategies are available. ENSEMBLE and TOP_K require this flag.

```python
if settings.feature_flags.enable_agent_collaboration:
    if settings.feature_flags.enable_expert_gate:
        routing = await expert_gate.route(message, team_id, ...)  # MoE routing
    else:
        routing = await router.route(message, team_id, ...)       # Simple skill matching
else:
    agent = await registry.get_agent(team_id, agent_slug)  # Direct dispatch
```

## Links to Main Plan

- **Section 4, Phase 7**: Agent Collaboration & Multi-Agent Conversations (lines 2079-2266)
- **Section 3A**: Agent Identity System (AgentDNA model, skill matching)
- **Section 3B**: Bulletproof Memory Architecture (shared memory, team memory bus)
- **Section 21**: Phase Dependency Graph (Phase 2 + Phase 4 -> Phase 7)
- **Section 23**: Rollback Strategy (Phase 7 rollback details)
- **SQL Schema**: `plan/sql/schema.sql` Phase 7 section (conversation_participant, agent_handoff)
