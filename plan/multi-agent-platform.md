# Multi-Agent Platform with Intelligent Memory

## 1. Vision & Product Definition

### What Are We Building?

A **multi-agent AI platform** that transforms the existing single-process CLI skill agent into a production-grade system where:

- **Named agents** (Kyra, Luke, etc.) have distinct personalities, expertise, and memory
- **Agents remember everything** -- conversations, preferences, learned patterns, team knowledge
- **Users interact via API, CLI, or messaging platforms** (Telegram, Slack)
- **Teams share knowledge** while agents maintain private learning
- **Background automation** runs on schedules (daily summaries, monitoring, etc.)

### Who Is This For?

| Persona | Need | Example |
|---------|------|---------|
| **Solo developer** | Personal AI assistant that learns over time | "Kyra, remember I prefer TypeScript over JavaScript" |
| **Small team** | Shared knowledge base with specialized agents | Marketing agent + Engineering agent sharing context |
| **Platform builder** | White-label multi-agent API | SaaS product with custom agents per customer |

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Memory retrieval latency | < 200ms p95 | From user message to memories injected in prompt |
| Conversation response (first token) | < 2s p95 | From API request to first SSE token |
| Memory precision | > 80% | Retrieved memories relevant to current query |
| CLI backward compatibility | 100% | `python -m src.cli` works unchanged at all times |
| Concurrent users | 50+ per instance | Load test with k6 or locust |
| Cost per conversation | Tracked, < $0.10 avg | Token usage + embedding costs logged |

### Non-Goals (Explicit)

- **Not** a general-purpose agent framework (use LangGraph/CrewAI for that)
- **Not** a model hosting platform (we call external LLMs)
- **Not** building a frontend/dashboard (API-first, UI can come later)
- **Not** replacing the skill system (extending it with persistence)

---

## 2. Architecture Overview

```
                                    CLIENTS
                    ┌────────────────┬──────────────────┐
                    │                │                  │
               ┌────▼────┐    ┌─────▼─────┐    ┌──────▼──────┐
               │   CLI   │    │ REST API  │    │  Webhooks   │
               │ (Rich)  │    │ (FastAPI) │    │ (Telegram/  │
               │         │    │ + SSE/WS  │    │  Slack)     │
               └────┬────┘    └─────┬─────┘    └──────┬──────┘
                    │               │                  │
                    └───────────────┼──────────────────┘
                                    │
                           ┌────────▼────────┐
                           │  Agent Router   │
                           │  (resolves      │
                           │   named agent)  │
                           └────────┬────────┘
                                    │
                    ┌───────────────┬┴──────────────────┐
                    │               │                   │
              ┌─────▼─────┐  ┌─────▼─────┐     ┌──────▼──────┐
              │  Agent     │  │  Agent     │     │  Agent      │
              │  "Kyra"    │  │  "Luke"    │     │  "Custom"   │
              │            │  │            │     │             │
              │ personality│  │ personality│     │ personality │
              │ skills[]   │  │ skills[]   │     │ skills[]    │
              │ model cfg  │  │ model cfg  │     │ model cfg   │
              └──────┬─────┘  └──────┬─────┘     └──────┬──────┘
                     │               │                   │
                     └───────────────┼───────────────────┘
                                     │
                    ┌────────────────┬┴──────────────────┐
                    │                │                   │
             ┌──────▼──────┐  ┌─────▼─────┐     ┌──────▼──────┐
             │   Skill     │  │  Memory   │     │   Tools     │
             │   System    │  │  System   │     │   (HTTP,    │
             │  (existing  │  │ (retrieve │     │    custom)  │
             │   + DB)     │  │  + store) │     │             │
             └─────────────┘  └─────┬─────┘     └─────────────┘
                                    │
                    ┌───────────────┬┴──────────────────┐
                    │               │                   │
             ┌──────▼──────┐ ┌─────▼─────┐     ┌──────▼──────┐
             │ PostgreSQL  │ │   Redis   │     │  Celery     │
             │ + pgvector  │ │  (cache,  │     │  (jobs,     │
             │ (memories,  │ │  sessions,│     │  memory     │
             │  agents,    │ │  locks)   │     │  consolidn, │
             │  convos)    │ │           │     │  webhooks)  │
             └─────────────┘ └───────────┘     └─────────────┘
```

### Key Architecture Principles

1. **Additive, not destructive** -- Every phase adds capability. Nothing breaks.
2. **Optional infrastructure** -- CLI works with zero infra (filesystem only). DB/Redis/Celery activate when configured.
3. **Agent = Personality + Skills + Memory + Model** -- Agents are configuration, not code.
4. **Memory is a first-class citizen** -- Not bolted on. Deeply integrated into prompt construction.
5. **Skills remain framework-agnostic** -- The filesystem skill format stays. DB adds discoverability.

---

## 3. Architecture Decision Records

### ADR-1: PostgreSQL + pgvector over dedicated vector DB

**Decision**: Use PostgreSQL with pgvector extension for both relational data AND vector search.

**Why not Pinecone/Weaviate/Qdrant?**
- Single database to manage, backup, migrate
- pgvector handles 100K-1M vectors performantly (our scale)
- ACID transactions across relational + vector data
- No additional service to deploy/pay for
- IVFFlat index for fast approximate nearest neighbor

**Trade-off**: At >1M vectors, a dedicated vector DB would outperform. We'll cross that bridge when we get there.

### ADR-2: Celery + Redis over ARQ/Dramatiq/TaskIQ

**Decision**: Celery with Redis broker for background processing.

**Context**: 2025-2026 benchmarks show TaskIQ is 10x faster than ARQ and competitive with Dramatiq. However:

**Why Celery?**
- Battle-tested at massive scale (Instagram, Mozilla)
- Celery Beat for cron scheduling (built-in)
- Extensive monitoring (Flower dashboard)
- Rich retry/error handling primitives
- Largest ecosystem of extensions
- Most production references and StackOverflow answers

**Why not TaskIQ?** Strong performance leader in benchmarks (async-native, modern design). Viable alternative. If we hit Celery's sync-first limitations, TaskIQ is the migration target.
**Why not ARQ?** Poor benchmark performance, limited scheduling. **Why not Dramatiq?** Smaller community, fewer production references.

**Trade-off**: Celery is sync-first. We wrap async calls with `asgiref.sync_to_async` or use `celery[eventlet]`. Slightly more boilerplate than TaskIQ.

**Escape hatch**: If Celery's sync nature causes friction, migrate to TaskIQ (`pip install taskiq taskiq-redis`). The task interface is similar enough for a low-risk migration.

### ADR-3: FastAPI over Litestar/Django

**Decision**: FastAPI for the REST API layer.

**Why?**
- Native Pydantic integration (shared models with our agent)
- First-class SSE/WebSocket support
- Async-native (matches our async agent code)
- Largest Python API framework community
- OpenAPI docs auto-generated

### ADR-4: JWT + API Keys (dual auth)

**Decision**: JWT for user sessions, API keys for programmatic/webhook access.

**Why both?**
- JWT: Short-lived, stateless, good for browser/mobile clients
- API keys: Long-lived, good for CI/CD, webhooks, integrations
- Both are team-scoped (multi-tenant isolation)

### ADR-5: Custom memory over Mem0/Zep/Letta

**Decision**: Build our own memory system rather than using Mem0, Zep, or Letta.

**Context**: Mem0 (`pip install mem0ai`) is the production leader with 66.9% accuracy. Zep offers temporal knowledge graphs. Letta (MemGPT) provides self-editing memory with an agent development environment.

**Why custom?**
- Full control over retrieval scoring weights (tuned per agent)
- No additional SaaS dependency or vendor lock-in
- Deep integration with our skill system and prompt builder
- Custom consolidation strategies per memory type
- We only need ~10K-100K memories per team (not millions)

**When to reconsider**: If memory quality is poor after Phase 2, consider Mem0 as a drop-in replacement for the storage + retrieval layer. The `EmbeddingService` and `MemoryRetriever` interfaces are designed to be swappable.

### ADR-6: Single memory table with type discriminator over table-per-type

**Decision**: One `memory` table with `memory_type` ENUM column.

**Why?**
- Simpler queries (no JOINs for cross-type search)
- Vector index covers all memory types
- Easier consolidation (merge across types without cross-table operations)
- Fewer migrations as we add memory types

**Trade-off**: Table may grow large. Mitigated by partitioning on `memory_type` if needed.

### ADR-7: All memory types from day 1

**Decision**: Implement all memory types in Phase 2. No phased rollout of memory capabilities.

**Why?**
- Memory is the core differentiator. Half-built memory = half-built product.
- Shared memory is essential for multi-agent teams from the start.
- Procedural memory drives agent learning -- without it, agents never improve.
- The cost of adding memory types later is higher than building them correctly once.
- The single-table discriminator design (ADR-6) makes this low-cost anyway.

### ADR-8: Append-only memory (nothing is ever truly deleted)

**Decision**: Memories are NEVER hard-deleted. Superseded memories are marked, archived memories move to cold storage, but raw data is always recoverable.

**Why?**
- "Never forgets" is the core brand promise
- Contradictory information is valuable (shows evolution of preferences)
- Compliance/audit requires history
- Users may want to recover "forgotten" context months later

**Trade-off**: Storage grows indefinitely. Mitigated by tiered storage (L1/L2/L3) and PostgreSQL partitioning by created_at.

### ADR-9: Agent collaboration via task delegation over direct agent calls

**Decision**: Agents collaborate through structured **task delegation** (persisted in `agent_task` table, executed via Celery) rather than direct function calls between agents. All inter-agent communication goes through the `AgentMessageBus`.

**Why?**
- Tasks are auditable (who asked what, what was the result, how much did it cost)
- Async execution via Celery prevents blocking and enables parallelism
- Depth limits and cycle detection prevent runaway chains
- Budget enforcement per-task and per-collaboration prevents cost explosions
- Failed tasks can be retried, dead-lettered, or escalated -- not silently lost
- Collaboration patterns (supervisor-worker, pipeline, etc.) compose naturally from tasks

**Trade-off**: Higher latency than direct calls (~200-500ms per delegation due to Celery queue). Mitigated by parallel task execution and caching agent availability in Redis.

### ADR-10: Mixture of Experts (Model + Agent level)

**Decision**: Implement two-layer MoE -- a **Model Router** that selects the optimal LLM tier per-query based on complexity scoring, and an **Expert Gate** that selects the best agent(s) using multi-signal scoring with support for routing, consultation, ensemble, and cascade strategies.

**Why?**
- Not every query needs the most expensive model (cost savings of 60-80% on simple queries)
- Not every agent is equally suited for every query (skill-based routing improves response quality)
- Ensemble mode allows combining insights from multiple specialist agents
- Load balancing prevents hotspot agents from degrading performance
- Aligns with the "unlimited agents" vision -- more agents = better coverage, not more confusion

**Trade-off**: Adds a classification step (~50-100ms) before each response. Mitigated by using a fast/cheap classifier model and caching recent routing decisions in Redis. Can be disabled entirely via feature flags for single-agent setups.

---

## 3A. Agent Identity System

### The Core Idea

An agent is not code. An agent is a **living identity document** -- a DNA blueprint that defines who it is, how it thinks, what it knows, and how it communicates. Creating a new agent is as simple as writing a config. There is no code per agent. There is no limit on how many agents can exist.

```
┌─────────────────────────────────────────────────────────┐
│                    AGENT DNA                            │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Identity │  │  Skills  │  │  Memory  │  │ Model  │ │
│  │          │  │          │  │          │  │        │ │
│  │ name     │  │ shared[] │  │ private  │  │ name   │ │
│  │ persona  │  │ custom[] │  │ shared   │  │ temp   │ │
│  │ voice    │  │ tools[]  │  │ team     │  │ budget │ │
│  │ rules    │  │          │  │ working  │  │ params │ │
│  │ examples │  │          │  │          │  │        │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Behavioral Boundaries               │   │
│  │  can_do: [...]     cannot_do: [...]              │   │
│  │  escalates_to: "agent-slug"                      │   │
│  │  max_autonomy: "execute" | "suggest" | "ask"     │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Agent DNA Model (Complete)

```python
class AgentDNA(BaseModel):
    """Complete identity document for a named agent."""

    # === IDENTITY ===
    id: UUID
    team_id: UUID
    name: str                        # "Kyra" -- display name
    slug: str                        # "kyra" -- URL-safe unique identifier
    tagline: str                     # "Your friendly AI companion" -- one-liner
    avatar_emoji: str = ""           # Optional visual identifier

    # === PERSONALITY ENGINE ===
    personality: AgentPersonality

    # === SKILLS ===
    shared_skill_names: list[str]    # Skills available to ALL agents in team
    custom_skill_names: list[str]    # Skills ONLY this agent has
    disabled_skill_names: list[str]  # Explicitly disabled (overrides shared)

    # === MODEL CONFIGURATION ===
    model: AgentModelConfig

    # === MEMORY CONFIGURATION ===
    memory: AgentMemoryConfig

    # === BEHAVIORAL BOUNDARIES ===
    boundaries: AgentBoundaries

    # === LIFECYCLE ===
    status: AgentStatus              # active, paused, archived, draft
    created_at: datetime
    updated_at: datetime
    created_by: UUID                 # User who created this agent

    @computed_field
    @property
    def effective_skills(self) -> list[str]:
        """All skills this agent can use (shared + custom - disabled)."""
        return [
            s for s in (self.shared_skill_names + self.custom_skill_names)
            if s not in self.disabled_skill_names
        ]


class AgentPersonality(BaseModel):
    """How the agent thinks, speaks, and behaves."""

    # Core personality prompt -- the "soul" of the agent
    system_prompt_template: str      # Template with {memory_context}, {skills}, etc.

    # Communication style
    tone: Literal[
        "professional", "friendly", "casual", "academic",
        "playful", "empathetic", "direct", "custom"
    ] = "friendly"
    verbosity: Literal["concise", "balanced", "detailed", "verbose"] = "balanced"
    formality: Literal["formal", "semi-formal", "informal", "adaptive"] = "adaptive"
    language: str = "en"             # ISO 639-1

    # Personality traits (weighted 0-1)
    traits: dict[str, float] = {}
    # Example: {"curious": 0.9, "humorous": 0.6, "empathetic": 0.8, "analytical": 0.7}

    # Voice examples -- sample responses that capture the agent's tone
    # These are injected into the system prompt as "how you should sound"
    voice_examples: list[VoiceExample] = []

    # Behavioral rules (always/never)
    always_rules: list[str] = []     # "Always greet the user by name"
    never_rules: list[str] = []      # "Never give medical advice"

    # Custom instructions (free-form)
    custom_instructions: str = ""    # Extra instructions appended to system prompt


class VoiceExample(BaseModel):
    """A sample interaction that demonstrates the agent's voice."""
    user_message: str                # "What's the weather like?"
    agent_response: str              # "Hey! Let me check that for you..."
    context: str = ""                # "Casual greeting"


class AgentModelConfig(BaseModel):
    """LLM configuration per agent."""
    model_name: str = "anthropic/claude-sonnet-4.5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)
    provider_overrides: dict[str, Any] = {}  # Provider-specific params


class AgentMemoryConfig(BaseModel):
    """Memory system configuration per agent."""
    token_budget: int = Field(default=2000, ge=100, le=8000)
    retrieval_weights: RetrievalWeights = Field(default_factory=RetrievalWeights)
    auto_extract: bool = True        # Auto-extract memories after conversation
    auto_pin_preferences: bool = True  # Auto-pin user preferences
    summarize_interval: int = 20     # Messages between auto-summaries
    remember_commands: list[str] = [  # Phrases that trigger explicit memory save
        "remember this",
        "don't forget",
        "keep in mind",
        "note that",
    ]


class AgentBoundaries(BaseModel):
    """What the agent can and cannot do."""
    can_do: list[str] = []           # Explicit capabilities
    cannot_do: list[str] = []        # Explicit restrictions
    escalates_to: Optional[str] = None  # Agent slug to escalate to
    max_autonomy: Literal[
        "execute",   # Do things without asking
        "suggest",   # Suggest actions, wait for approval
        "ask",       # Always ask before acting
    ] = "execute"
    allowed_domains: list[str] = []  # HTTP tool domain allowlist (empty = all)
    max_tool_calls_per_turn: int = Field(default=10, ge=1, le=50)


class AgentStatus(str, Enum):
    DRAFT = "draft"         # Being configured, not yet usable
    ACTIVE = "active"       # Accepting conversations
    PAUSED = "paused"       # Temporarily unavailable
    ARCHIVED = "archived"   # Soft-deleted, data preserved
```

### Shared vs Custom Skills

```
┌─────────────────────────────────────────────────┐
│                   TEAM LEVEL                    │
│                                                 │
│  Shared Skills: [weather, world_clock, http]    │
│  Available to ALL agents in this team           │
│                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌────────┐  │
│  │    Kyra     │  │    Luke     │  │  Ada   │  │
│  │             │  │             │  │        │  │
│  │ + research  │  │ + code_rev  │  │ + data │  │
│  │ + recipe    │  │ + devops    │  │ + viz  │  │
│  │             │  │             │  │        │  │
│  │ - weather   │  │             │  │        │  │
│  │ (disabled)  │  │             │  │        │  │
│  └─────────────┘  └─────────────┘  └────────┘  │
│                                                 │
│  Kyra sees: world_clock, http, research, recipe │
│  Luke sees: weather, world_clock, http,         │
│             code_review, devops                 │
│  Ada sees:  weather, world_clock, http,         │
│             data_analysis, visualization        │
└─────────────────────────────────────────────────┘
```

Skills resolution order:
1. Start with team's `shared_skill_names`
2. Add agent's `custom_skill_names`
3. Remove agent's `disabled_skill_names`
4. Result = agent's `effective_skills`

### Unlimited Agent Registry

```python
class AgentRegistry:
    """
    Lazy-loading agent registry. No limit on agents.

    Agents are pure configuration rows in PostgreSQL.
    Creating a new agent = INSERT one row.
    No code changes. No deployment. No restart.
    """

    async def create_agent(self, team_id: UUID, dna: AgentDNA) -> AgentDNA:
        """Create a new agent. Validates slug uniqueness within team."""

    async def get_agent(self, team_id: UUID, slug: str) -> AgentDNA:
        """Load agent by slug. Cached in Redis (5min TTL)."""

    async def list_agents(self, team_id: UUID) -> list[AgentSummary]:
        """List all active agents for a team."""

    async def clone_agent(
        self, source_slug: str, new_name: str, team_id: UUID
    ) -> AgentDNA:
        """Clone an agent with a new name. Copies config, not memories."""

    async def build_pydantic_agent(self, dna: AgentDNA) -> Agent:
        """
        Construct a Pydantic AI Agent instance from DNA.

        1. Resolve effective skills
        2. Create SkillLoader with only those skills
        3. Select model from dna.model.model_name
        4. Register skill tools + HTTP tools
        5. Attach memory-aware system prompt decorator
        6. Return ready-to-use Agent instance
        """
```

**No limits enforced.** A team can have 1 agent or 1,000. The system scales because:
- Agents are config rows, not processes
- Agents are instantiated on-demand per conversation (not pre-loaded)
- Memory queries are scoped by agent_id (indexed)
- Redis caches agent config (5min TTL) to avoid repeated DB lookups

### Agent Identity Preservation

The agent's identity is NEVER lost, even across:

| Scenario | How Identity Survives |
|----------|----------------------|
| Context compaction | Identity prompt is Layer 1 (NEVER trimmed) |
| New conversation | Identity loaded fresh from DB every time |
| Server restart | All config in PostgreSQL, nothing in-memory |
| Memory consolidation | Agent-specific memories tagged with agent_id |
| Model change | Personality prompt is model-agnostic |
| Skill changes | Skills are resolved dynamically, not baked in |

### Personality Prompt Template

```python
KYRA_TEMPLATE = """You are {agent_name}, {agent_tagline}.

## Who You Are
{personality_traits}

## How You Communicate
- Tone: {tone}
- Style: {verbosity}, {formality}
{voice_examples_section}

## Your Rules
ALWAYS:
{always_rules}

NEVER:
{never_rules}

{custom_instructions}

## What You Remember
{memory_context}

## Your Skills
{skill_metadata}

## User Preferences
{user_preferences}

## Conversation Context
{conversation_summary}
"""
```

This template is populated by the MemoryPromptBuilder at runtime. The `{memory_context}` block is the only variable-length section; everything else is fixed and NEVER trimmed.

---

## 3B. Bulletproof Memory Architecture

### The Core Guarantee

**Nothing is ever forgotten.**

Not summarized away. Not expired. Not lost in context compaction. Every piece of information the agent learns is preserved in at least one tier of storage, forever. The system may choose not to RETRIEVE a memory (low relevance), but it will never DESTROY one.

```
┌─────────────────────────────────────────────────────────────┐
│                   MEMORY HIERARCHY                          │
│                                                             │
│   L1 HOT ──── In the prompt right now ──── Redis + Prompt  │
│   (< 5ms)     Top-scored memories                           │
│               Current conversation state                    │
│               Agent identity (always)                       │
│                                                             │
│   L2 WARM ─── Retrievable on demand ────── PostgreSQL      │
│   (< 200ms)   All active memories                           │
│               Searchable by vector, recency, importance     │
│               Contradiction-aware                           │
│                                                             │
│   L3 COLD ─── Archived, never deleted ──── PostgreSQL      │
│   (< 2s)      Superseded memories                           │
│               Expired low-importance memories               │
│               Historical conversation summaries             │
│               Full provenance chain                         │
│                                                             │
│   RAW LOG ─── Append-only audit trail ──── PostgreSQL      │
│   (archival)  Every memory creation/update/supersede event  │
│               Every conversation message (verbatim)         │
│               Never modified, never deleted                 │
│               Basis for complete reconstruction             │
└─────────────────────────────────────────────────────────────┘
```

### Memory Types (All Built from Day 1)

```
┌────────────────────────────────────────────────────────────────────┐
│                       MEMORY TYPES                                │
│                                                                    │
│  SEMANTIC ────── Facts, preferences, knowledge                    │
│  "User prefers TypeScript"                                        │
│  "Project deadline is March 15"                                   │
│  Versioned: contradictions tracked, latest wins in retrieval      │
│                                                                    │
│  EPISODIC ────── Events, conversations, decisions                 │
│  "On Feb 9 we decided to use PostgreSQL"                          │
│  "User was frustrated about the deploy failure"                   │
│  Timestamped: chronological ordering matters                      │
│                                                                    │
│  PROCEDURAL ──── Learned workflows, tool patterns                 │
│  "Weather queries: load_skill → http_get → format"               │
│  "Code review: load_skill → read checklist → analyze"            │
│  Scored: success_rate, times_used, last_used                      │
│                                                                    │
│  AGENT-PRIVATE ─ Per-agent learning, private insights             │
│  "This user prefers verbose explanations from Kyra"              │
│  "Luke learned to always ask for confirmation before deploy"     │
│  Scoped: only visible to the owning agent                        │
│                                                                    │
│  SHARED ──────── Team-wide knowledge                              │
│  "Team coding standard: PEP 8, 100 char lines"                  │
│  "Production DB is on us-east-1"                                 │
│  Scoped: visible to ALL agents in the team                       │
│                                                                    │
│  IDENTITY ────── Agent's self-knowledge                           │
│  "I am Kyra, I specialize in research and communication"         │
│  "Users often tell me I'm helpful when I give examples"          │
│  Protected: NEVER expired, NEVER consolidated, ALWAYS in prompt  │
│                                                                    │
│  USER-PROFILE ── Persistent user facts across all agents          │
│  "User's name is Sarah"                                          │
│  "User timezone: PST"                                            │
│  "User's company: Acme Corp"                                     │
│  Scoped: visible to all agents, attached to user_id              │
└────────────────────────────────────────────────────────────────────┘
```

### Memory Schema (Extended)

```sql
CREATE TABLE memory (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES team(id),
    agent_id UUID REFERENCES agent(id),          -- NULL = shared/user-profile
    user_id UUID REFERENCES "user"(id),          -- NULL = team-wide

    -- Content
    memory_type TEXT NOT NULL,                    -- ENUM values above
    content TEXT NOT NULL,                        -- The actual memory text
    subject TEXT,                                 -- Structured: "user.preference.language"
    embedding vector(1536),                       -- pgvector

    -- Scoring
    importance INT NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    confidence FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    access_count INT DEFAULT 0,
    is_pinned BOOLEAN DEFAULT FALSE,

    -- Provenance
    source_type TEXT NOT NULL DEFAULT 'extraction', -- 'extraction', 'explicit', 'system', 'feedback'
    source_conversation_id UUID REFERENCES conversation(id),
    source_message_ids UUID[],                    -- Exact messages this memory came from
    extraction_model TEXT,                         -- Which LLM extracted this

    -- Versioning & Contradictions
    version INT DEFAULT 1,
    superseded_by UUID REFERENCES memory(id),     -- Points to newer version
    contradicts UUID[],                            -- IDs of memories this contradicts

    -- Relationships
    related_to UUID[],                             -- Soft links to related memories

    -- Metadata
    metadata JSONB DEFAULT '{}',                   -- Flexible: tags, tool_sequence, success_rate, etc.

    -- Lifecycle
    tier TEXT DEFAULT 'warm' CHECK (tier IN ('hot', 'warm', 'cold')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'archived', 'disputed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                        -- NULL = never expires

    -- Constraints
    CONSTRAINT valid_memory_type CHECK (memory_type IN (
        'semantic', 'episodic', 'procedural', 'agent_private',
        'shared', 'identity', 'user_profile'
    ))
);

-- Append-only audit log (NEVER modified, NEVER deleted)
CREATE TABLE memory_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL,                       -- References memory(id) but no FK (survives deletes)
    action TEXT NOT NULL,                           -- 'created', 'updated', 'superseded', 'promoted', 'demoted'
    old_content TEXT,                               -- Content before change (NULL for 'created')
    new_content TEXT,                               -- Content after change
    old_importance INT,
    new_importance INT,
    changed_by TEXT NOT NULL,                       -- 'system', 'user', 'consolidation', 'feedback'
    reason TEXT,                                    -- "Superseded by newer preference"
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### The Seven Guarantees

| # | Guarantee | How |
|---|-----------|-----|
| 1 | **Never loses a memory** | Append-only `memory_log`. Superseded memories move to `tier='cold'`, never deleted |
| 2 | **Never forgets during context compaction** | Pre-compaction extraction: before trimming, extract and persist all facts. Double-extract with verification LLM call |
| 3 | **Always retrieves relevant context** | 5-signal retrieval with fallback cascade: hot cache → warm DB → cold archive |
| 4 | **Detects contradictions** | New memories checked against existing. Conflicting facts stored with `contradicts[]` links and `status='disputed'` until resolved |
| 5 | **Tracks provenance** | Every memory knows: which conversation, which messages, which LLM extracted it, when, confidence score |
| 6 | **Preserves agent identity** | Identity memories are `tier='hot'`, `is_pinned=TRUE`, NEVER trimmed from prompt. Layer 1 in prompt builder |
| 7 | **Recoverable at any point in time** | `memory_log` allows reconstructing the exact memory state at any historical timestamp |

### 5-Signal Retrieval Pipeline

```
User message arrives
    │
    ├─► STEP 1: Generate query embedding
    │
    ├─► STEP 2: Check L1 hot cache (Redis)
    │   ├── HIT: Skip to STEP 4 with cached memories
    │   └── MISS: Continue to STEP 3
    │
    ├─► STEP 3: PARALLEL 5-SIGNAL SEARCH (PostgreSQL)
    │   │
    │   ├─► Signal A: SEMANTIC SIMILARITY (weight: configurable per agent)
    │   │   Cosine similarity against query embedding
    │   │   Filtered: team_id + agent scope + status='active'
    │   │   LIMIT 50
    │   │
    │   ├─► Signal B: RECENCY (weight: configurable)
    │   │   Most recently accessed/created memories
    │   │   Exponential decay: score = exp(-λ * hours_since_access)
    │   │   λ = 0.01 → half-life ~69 hours
    │   │   LIMIT 30
    │   │
    │   ├─► Signal C: IMPORTANCE + PINNED (weight: configurable)
    │   │   Pinned memories (always score 1.0)
    │   │   High importance (≥7) memories
    │   │   Identity memories (always included)
    │   │   LIMIT 30
    │   │
    │   ├─► Signal D: CONVERSATION CONTINUITY (weight: configurable)
    │   │   Memories from current conversation's source
    │   │   Memories recently created in same session
    │   │   Enables "I just told you about X" to work
    │   │   LIMIT 20
    │   │
    │   └─► Signal E: RELATIONSHIP GRAPH (weight: configurable)
    │       Memories linked via `related_to` to any Signal A hit
    │       One hop: if memory A is relevant AND links to memory B,
    │       memory B gets a relationship bonus
    │       LIMIT 20
    │
    ├─► STEP 4: MERGE + DEDUPLICATE + SCORE
    │   │
    │   │  For each unique memory:
    │   │  final_score = (W_sem * semantic_similarity)
    │   │              + (W_rec * recency_score)
    │   │              + (W_imp * normalized_importance)
    │   │              + (W_con * continuity_score)
    │   │              + (W_rel * relationship_bonus)
    │   │
    │   │  Where W_* are from agent.memory.retrieval_weights
    │   │
    │   │  Pinned memories: final_score = max(final_score, 0.95)
    │   │  Identity memories: final_score = 1.0 (always included)
    │   │  Disputed memories: final_score *= 0.5 (deprioritized)
    │   │
    │   └─► Sort by final_score descending
    │
    ├─► STEP 5: TOKEN BUDGET ALLOCATION
    │   │
    │   │  Budget = agent.memory.token_budget (default 2000)
    │   │
    │   │  Allocation priority:
    │   │    1. Identity memories      (reserved: 200 tokens, NEVER cut)
    │   │    2. Pinned memories        (reserved: 300 tokens)
    │   │    3. User-profile memories  (reserved: 200 tokens)
    │   │    4. Remaining by score     (fill remaining budget greedily)
    │   │
    │   │  Each memory: estimate tokens = len(content) / 3.5
    │   │  Add memories until budget exhausted
    │   │
    │   └─► If budget too small for all pinned: WARN in logs, include anyway
    │
    ├─► STEP 6: FORMAT FOR PROMPT
    │   │
    │   │  Group by type, format with clear delimiters:
    │   │
    │   │  ## Your Identity
    │   │  [IDENTITY]: I am Kyra, a friendly research assistant...
    │   │
    │   │  ## About This User
    │   │  [USER-PROFILE]: Name is Sarah, timezone PST, works at Acme
    │   │  [PREFERENCE]: Prefers detailed explanations with examples
    │   │
    │   │  ## What You Know (Facts)
    │   │  [FACT]: Project deadline is March 15 (importance: 8, confidence: 0.9)
    │   │  [FACT]: Team uses PostgreSQL for all services (importance: 7)
    │   │
    │   │  ## Recent Events
    │   │  [EVENT 2026-02-09]: Decided to use pgvector for memory system
    │   │  [EVENT 2026-02-08]: User was debugging auth module
    │   │
    │   │  ## Learned Patterns
    │   │  [PATTERN]: Weather queries → load skill → API call (95% success, 12 uses)
    │   │
    │   │  ## Team Knowledge
    │   │  [TEAM]: Coding standard is PEP 8 with 100 char lines
    │   │
    │   └─► Contradiction markers:
    │       [FACT ⚡DISPUTED]: User prefers Python (contradicts: "prefers TypeScript" from Jan 15)
    │
    └─► STEP 7: UPDATE ACCESS METADATA (async, non-blocking)
        SET access_count = access_count + 1
        SET last_accessed_at = NOW()
        Promote frequently-accessed warm memories to hot cache
```

### Context Compaction Shield

When the conversation approaches the model's context limit and messages must be compressed:

```
BEFORE compaction triggers:
    │
    ├─► EXTRACTION PASS 1 (primary LLM)
    │   "Extract ALL facts, decisions, preferences, events from
    │    these messages. Miss NOTHING. Rate importance 1-10."
    │
    ├─► EXTRACTION PASS 2 (verification LLM -- different prompt)
    │   "Review these messages AND the Pass 1 extractions.
    │    What did Pass 1 miss? What was extracted incorrectly?"
    │
    ├─► MERGE Pass 1 + Pass 2 extractions
    │   Union of both sets (deduplicated by cosine > 0.95)
    │
    ├─► PERSIST all extracted memories to PostgreSQL
    │   With provenance: source_message_ids = [exact message UUIDs]
    │
    ├─► GENERATE conversation summary (for context continuity)
    │   Stored in working memory (Redis) AND as episodic memory (PG)
    │
    └─► NOW safe to compact
        The compacted messages are also preserved in `message` table
        (raw log, never deleted)
```

**Key insight**: We extract BEFORE compacting, not after. The raw messages are preserved in PostgreSQL forever. The extraction is an enrichment step that creates searchable, scored memories from the raw data.

### Contradiction Detection

```python
class ContradictionDetector:
    """Detect and manage contradictory memories."""

    async def check_new_memory(
        self, new_memory: MemoryCreate, existing: list[MemoryRecord]
    ) -> ContradictionResult:
        """
        Compare new memory against existing memories.

        Detection strategies:
        1. SAME SUBJECT: If existing semantic memory has same subject
           (e.g., both about "user.preference.language"), check if
           content conflicts
        2. SEMANTIC OPPOSITION: If cosine similarity > 0.7 but
           sentiment/content is opposite (LLM judgment call)
        3. TEMPORAL OVERRIDE: If new info is more recent and
           contradicts older info, mark older as superseded

        Returns:
            ContradictionResult with:
            - contradicts: list[UUID] -- IDs of conflicting memories
            - action: 'supersede' | 'dispute' | 'coexist'
            - reason: str
        """
```

When a contradiction is detected:
```
New memory: "User prefers JavaScript"
Existing:   "User prefers TypeScript" (from 2 weeks ago)
    │
    ├─► If explicit ("I now prefer JS"): SUPERSEDE old memory
    │   old.status = 'superseded'
    │   old.superseded_by = new.id
    │   new.version = old.version + 1
    │
    ├─► If ambiguous: DISPUTE both
    │   old.status = 'disputed'
    │   old.contradicts = [new.id]
    │   new.status = 'disputed'
    │   new.contradicts = [old.id]
    │   → Both appear in prompt with ⚡DISPUTED marker
    │   → Agent can ask user to clarify
    │
    └─► Log in memory_log: action='contradiction_detected'
```

### Memory Extraction Prompt (Production-Grade)

```python
EXTRACTION_PROMPT = """Analyze this conversation and extract memories.

For EACH piece of information, output a JSON object with:
- type: "semantic" | "episodic" | "procedural" | "user_profile"
- content: The fact/event/pattern in a clear, standalone sentence
- subject: Dot-notation category (e.g., "user.preference.language", "project.deadline")
- importance: 1-10 (see scale below)
- confidence: 0.0-1.0 (how certain is this information?)

IMPORTANCE SCALE:
10 - User explicitly said "remember this" or "don't forget"
9  - User's core identity (name, role, company)
8  - Strong preference ("I always...", "I prefer...", "I hate...")
7  - Decision made ("We decided...", "Let's go with...")
6  - Project-critical fact (deadline, requirement, constraint)
5  - Useful context (tech stack, workflow, team structure)
4  - Mild preference or opinion
3  - Casual mention, might be relevant later
2  - Small talk, unlikely to matter
1  - Ephemeral (greetings, acknowledgments)

RULES:
- Extract EVERY fact, preference, decision, and event. Miss NOTHING.
- Each memory must be a STANDALONE sentence (readable without context)
- Include temporal context ("On Feb 9...", "This week...")
- If user corrects themselves, extract the CORRECTION with high importance
- Extract tool usage patterns as "procedural" type
- Minimum importance 3 to be extracted (skip greetings/small talk)

CONVERSATION:
{messages}

Respond with a JSON array of extracted memories."""
```

### Shared vs Private vs Team Memory Model

```
┌───────────────────────────────────────────────────────────────┐
│                         TEAM                                  │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              SHARED MEMORIES                             │ │
│  │  Visible to ALL agents in team                          │ │
│  │  "Team uses PostgreSQL"  "Office hours are 9-5 PST"    │ │
│  │  agent_id = NULL, memory_type = 'shared'                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              USER PROFILE MEMORIES                       │ │
│  │  Visible to ALL agents, scoped to user                  │ │
│  │  "Sarah's timezone is PST"  "Sarah works at Acme"      │ │
│  │  agent_id = NULL, memory_type = 'user_profile'          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │    KYRA      │  │    LUKE      │  │    ADA       │       │
│  │              │  │              │  │              │       │
│  │ Private:     │  │ Private:     │  │ Private:     │       │
│  │ "Sarah      │  │ "Sarah      │  │ "Sarah      │       │
│  │  likes      │  │  wants      │  │  prefers    │       │
│  │  examples"  │  │  brief      │  │  charts     │       │
│  │             │  │  answers"   │  │  over text" │       │
│  │ Identity:   │  │ Identity:   │  │ Identity:   │       │
│  │ "I am Kyra" │  │ "I am Luke" │  │ "I am Ada"  │       │
│  │             │  │             │  │             │       │
│  │ Procedural: │  │ Procedural: │  │ Procedural: │       │
│  │ "weather→   │  │ "review→    │  │ "query→     │       │
│  │  API call"  │  │  checklist" │  │  visualize" │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└───────────────────────────────────────────────────────────────┘
```

**Memory visibility rules** (enforced at query level):

```sql
-- What agent "kyra" can see:
WHERE team_id = $team
  AND (
    memory_type IN ('shared', 'user_profile')                  -- Team-wide
    OR (agent_id = $kyra_id AND memory_type IN (               -- Kyra's private
        'agent_private', 'identity', 'procedural', 'semantic', 'episodic'
    ))
    OR (agent_id IS NULL AND memory_type IN ('semantic', 'episodic'))  -- Unscoped
  )
  AND status IN ('active', 'disputed')
```

### Memory Promotion & Demotion (Tier Management)

```
                    ┌────────────┐
        ┌──────────►│  L1 HOT    │◄── Auto-promote when access_count > 10
        │           │  (Redis)   │    or importance >= 9 or is_pinned
        │           └──────┬─────┘
        │                  │
        │         Evict when TTL expires
        │         or cache full (LRU)
        │                  │
        │           ┌──────▼─────┐
  Retrieve ────────►│  L2 WARM   │◄── Default tier for new memories
  on demand         │  (PG)      │    Active, searchable, scored
                    └──────┬─────┘
                           │
                  Demote when: superseded
                  OR importance < 3 AND access_count < 2
                  AND age > 90 days AND NOT pinned
                           │
                    ┌──────▼─────┐
                    │  L3 COLD   │◄── Archived, still searchable
                    │  (PG)      │    Lower priority in retrieval
                    │            │    Never deleted
                    └────────────┘
```

Promotion triggers:
- `access_count > 10` in past 7 days → promote warm → hot
- User pins memory → immediate promote to hot
- Feedback positive → boost importance, may promote

Demotion triggers:
- Superseded by newer version → demote to cold
- `importance < 3 AND access_count < 2 AND age > 90 days` → demote to cold
- Never: identity, pinned, or importance >= 8 memories

### Memory API (User-Facing)

Users can directly interact with the memory system:

```python
# POST /v1/memories -- Explicit memory creation
# "Remember that our API key rotates every 30 days"
class ExplicitMemoryCreate(BaseModel):
    content: str
    memory_type: str = "semantic"
    importance: int = 8           # Explicit memories default to high importance
    is_pinned: bool = False
    agent_slug: Optional[str]     # None = shared memory

# GET /v1/memories/search -- Semantic search
class MemorySearchRequest(BaseModel):
    query: str                    # Natural language query
    memory_types: list[str] = []  # Filter by type (empty = all)
    agent_slug: Optional[str]     # Filter by agent
    min_importance: int = 1
    include_cold: bool = False    # Search cold tier too
    limit: int = 20

# DELETE /v1/memories/{id} -- Soft delete (moves to cold, never hard-deleted)

# POST /v1/memories/{id}/pin -- Pin/unpin
# POST /v1/memories/{id}/correct -- Submit correction (creates new version)
class MemoryCorrectionRequest(BaseModel):
    corrected_content: str        # The new correct version
    reason: str = ""              # Why the old version was wrong
```

---

## 3C. Mixture of Experts Architecture

Two independent MoE layers work together to optimize **cost**, **quality**, and **latency**:

```
                          ┌─────────────────────────────────────────┐
                          │           INCOMING MESSAGE              │
                          └───────────────┬─────────────────────────┘
                                          │
                    ┌─────────────────────▼─────────────────────┐
                    │         LAYER 1: EXPERT GATE              │
                    │     (Which agent should handle this?)     │
                    │                                           │
                    │  Signals:                                 │
                    │    ├─ Skill match (0.40)                  │
                    │    ├─ Past performance (0.25)             │
                    │    ├─ Personality fit (0.20)              │
                    │    └─ Load balance (0.15)                 │
                    │                                           │
                    │  Strategies:                              │
                    │    ├─ TOP_1:    Route to best agent       │
                    │    ├─ TOP_K:    Consult K, pick best      │
                    │    ├─ ENSEMBLE: Merge K responses         │
                    │    └─ CASCADE:  Try in order until OK     │
                    └─────────────────┬─────────────────────────┘
                                      │
                    ┌─────────────────▼─────────────────────┐
                    │         LAYER 2: MODEL ROUTER         │
                    │     (Which LLM tier for this query?)  │
                    │                                       │
                    │  Complexity Scorer (5 dimensions):     │
                    │    ├─ Reasoning depth   (0.30)        │
                    │    ├─ Domain specificity (0.25)       │
                    │    ├─ Creativity         (0.20)       │
                    │    ├─ Context dependency (0.15)       │
                    │    └─ Output length      (0.10)       │
                    │                                       │
                    │  Score 0-3 → Tier 1 (Fast/cheap)      │
                    │  Score 4-6 → Tier 2 (Balanced)        │
                    │  Score 7-10 → Tier 3 (Powerful)       │
                    └─────────────────┬─────────────────────┘
                                      │
                    ┌─────────────────▼─────────────────────┐
                    │              LLM CALL                 │
                    │  Agent: selected agent's AgentDNA     │
                    │  Model: selected tier's model         │
                    │  Budget: CostGuard enforced           │
                    └───────────────────────────────────────┘
```

### Layer 1: Expert Gate (Agent-Level MoE)

The Expert Gate replaces the simple `AgentRouter` from Phase 7 with a multi-signal scoring system:

```python
class ExpertGate:
    """
    Multi-signal gate network for agent selection.

    Scores every active agent in the team and selects the best
    using the configured strategy.
    """

    async def score_experts(
        self,
        query: str,
        team_id: UUID,
        context: ConversationContext,
    ) -> list[ExpertScore]:
        """
        Score all active agents in the team on 4 signals.

        Args:
            query: The user's message
            team_id: The team to search for agents
            context: Current conversation context (history, agent, etc.)

        Returns:
            Sorted list of ExpertScores (highest first)
        """

    # Signal 1: Skill Match (weight 0.40)
    # ────────────────────────────────────
    # Compare query against each agent's effective_skills descriptions.
    # Uses TF-IDF keyword matching + optional embedding similarity
    # between query and skill metadata for fast, cache-friendly scoring.

    # Signal 2: Past Performance (weight 0.25)
    # ────────────────────────────────────────
    # How well has this agent handled similar queries?
    # - Average feedback_rating on messages with similar query embeddings
    # - Success rate (positive ratings / total rated) over last 30 days
    # - Penalty for recent negative feedback on similar topics

    # Signal 3: Personality Fit (weight 0.20)
    # ────────────────────────────────────────
    # Does the agent's communication style match the query tone?
    # - Casual query → prefer agents with tone="friendly"/"casual"
    # - Technical query → prefer agents with tone="professional"/"academic"
    # - Emotional query → prefer agents with trait "empathetic" > 0.7

    # Signal 4: Load Balancing (weight 0.15)
    # ────────────────────────────────────────
    # Is this agent overloaded?
    # - Active conversation count (lower = better)
    # - Average response latency over last hour
    # - Queue depth (pending messages awaiting response)


class ExpertScore(BaseModel):
    """Scoring result for a single agent."""
    agent_slug: str
    agent_name: str
    skill_match: float = Field(ge=0.0, le=1.0)
    past_performance: float = Field(ge=0.0, le=1.0)
    personality_fit: float = Field(ge=0.0, le=1.0)
    load_balance: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    matching_skills: list[str]
    explanation: str              # "Matched skills: code_review, testing; high past success"


class SelectionStrategy(str, Enum):
    """How to use expert scores to select agent(s)."""
    TOP_1 = "top_1"              # Route to single best agent
    TOP_K = "top_k"              # Consult K agents, pick best response
    ENSEMBLE = "ensemble"        # Combine responses from multiple agents
    CASCADE = "cascade"          # Try agents in order until one succeeds


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
        Select agent(s) based on strategy.

        Rules:
        - If best score < confidence_threshold → use default agent + log warning
        - TOP_1:    Return highest-scoring agent
        - TOP_K:    Return top K agents for parallel execution
        - ENSEMBLE: Return all agents above threshold for parallel execution
        - CASCADE:  Return ordered list for sequential try
        """


class SelectionResult(BaseModel):
    """Result of agent selection."""
    strategy: SelectionStrategy
    selected_agents: list[ExpertScore]      # Agents chosen (1 for TOP_1, K for others)
    fallback_used: bool = False             # True if no agent met confidence threshold
    routing_time_ms: float                  # Time spent on routing decision


class ResponseAggregator:
    """Combine responses from multiple experts (ENSEMBLE/TOP_K modes)."""

    async def aggregate(
        self,
        responses: list[ExpertResponse],
        query: str,
    ) -> AggregatedResponse:
        """
        Combine expert responses into a single response.

        Strategy:
        1. Score each response on relevance to query
        2. Dedup overlapping content
        3. Merge complementary insights
        4. Attribute contributions: "According to Luke (code review)..."

        Uses a meta-model call (Tier 1 model) to synthesize.
        """


class ExpertResponse(BaseModel):
    """Response from a single expert agent."""
    agent_slug: str
    agent_name: str
    content: str
    confidence: float                # Self-assessed confidence
    tokens_used: int
    latency_ms: float
```

#### Expert Gate Flow

```
User: "Help me optimize this SQL query for PostgreSQL"
    │
    ├─► ExpertGate.score_experts()
    │     ├─ Kyra (general):   skill=0.2, perf=0.7, fit=0.6, load=0.9 → 0.51
    │     ├─ Luke (code):      skill=0.9, perf=0.8, fit=0.8, load=0.7 → 0.83
    │     └─ Ada  (data):      skill=0.8, perf=0.9, fit=0.7, load=0.8 → 0.81
    │
    ├─► ExpertSelector.select(strategy=TOP_1)
    │     └─ Selected: Luke (0.83) — matched skills: [code_review, database]
    │
    └─► Route to Luke with full context
```

#### Ensemble Flow (When Configured)

```
User: "I need a marketing strategy for our developer tool"
    │
    ├─► ExpertGate.score_experts()
    │     ├─ Kyra (general):     0.65
    │     ├─ Ada  (data):        0.72
    │     └─ Max  (marketing):   0.88
    │
    ├─► ExpertSelector.select(strategy=ENSEMBLE, threshold=0.6)
    │     └─ Selected: Max (0.88), Ada (0.72), Kyra (0.65) — all above threshold
    │
    ├─► Parallel execution: all 3 agents respond independently
    │
    └─► ResponseAggregator.aggregate()
          └─ "Max suggests focusing on developer communities (marketing).
              Ada recommends tracking conversion by referral source (data).
              Kyra adds to consider the developer experience angle (general)."
```

### Layer 2: Model Router (Model-Level MoE)

After the Expert Gate selects the agent, the Model Router picks the optimal LLM tier:

```python
class ModelTier(BaseModel):
    """Configuration for a model cost/capability tier."""
    name: str                           # "fast", "balanced", "powerful"
    model_name: str                     # "anthropic/claude-haiku-4.5"
    max_output_tokens: int = 4096
    cost_per_1k_input: float            # Estimated cost in USD
    cost_per_1k_output: float
    suitable_for: list[str]             # ["simple_qa", "classification", "formatting"]

    # Performance characteristics
    avg_latency_ms: int = 500           # Expected average latency
    supports_streaming: bool = True
    supports_tools: bool = True


class ComplexityScore(BaseModel):
    """Multi-dimensional query complexity assessment."""
    reasoning_depth: float = Field(ge=0.0, le=10.0)
    domain_specificity: float = Field(ge=0.0, le=10.0)
    creativity: float = Field(ge=0.0, le=10.0)
    context_dependency: float = Field(ge=0.0, le=10.0)
    output_length: float = Field(ge=0.0, le=10.0)

    @computed_field
    @property
    def overall(self) -> float:
        """Weighted average of all dimensions."""
        weights = [0.30, 0.25, 0.20, 0.15, 0.10]
        scores = [
            self.reasoning_depth, self.domain_specificity,
            self.creativity, self.context_dependency, self.output_length,
        ]
        return sum(w * s for w, s in zip(weights, scores))


class QueryComplexityScorer:
    """
    Score query complexity to determine the optimal model tier.

    Uses a fast classifier (Tier 1 model) to analyze the query
    on 5 dimensions. Result is cached in Redis for identical queries.
    """

    async def score(
        self,
        query: str,
        conversation_history: list[Message],
        agent_dna: AgentDNA,
    ) -> ComplexityScore:
        """
        Analyze query complexity on 5 dimensions.

        Scoring guidelines:
        ┌─────────────────────┬──────────────┬──────────────┬──────────────┐
        │ Dimension           │ Low (0-3)    │ Medium (4-6) │ High (7-10)  │
        ├─────────────────────┼──────────────┼──────────────┼──────────────┤
        │ Reasoning depth     │ "What time?" │ "Compare X"  │ "Debug this" │
        │ Domain specificity  │ General Q&A  │ Industry     │ Expert niche │
        │ Creativity          │ Factual      │ Rewrite      │ Novel story  │
        │ Context dependency  │ Standalone   │ References 1 │ Deep thread  │
        │ Output length       │ One-liner    │ Paragraph    │ Full doc     │
        └─────────────────────┴──────────────┴──────────────┴──────────────┘
        """


class ModelRouter:
    """Route queries to the optimal model tier based on complexity."""

    DEFAULT_TIERS: ClassVar[list[ModelTier]] = [
        ModelTier(
            name="fast",
            model_name="anthropic/claude-haiku-4.5",
            cost_per_1k_input=0.0008,
            cost_per_1k_output=0.004,
            avg_latency_ms=200,
            suitable_for=["simple_qa", "classification", "formatting", "yes_no"],
        ),
        ModelTier(
            name="balanced",
            model_name="anthropic/claude-sonnet-4.5",
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            avg_latency_ms=800,
            suitable_for=["analysis", "conversation", "summarization", "code_review"],
        ),
        ModelTier(
            name="powerful",
            model_name="anthropic/claude-opus-4",
            cost_per_1k_input=0.015,
            cost_per_1k_output=0.075,
            avg_latency_ms=2000,
            suitable_for=["complex_reasoning", "architecture", "novel_code", "research"],
        ),
    ]

    async def route(
        self,
        score: ComplexityScore,
        agent_config: AgentModelConfig,
        budget_remaining: Optional[float] = None,
    ) -> ModelTier:
        """
        Select model tier based on complexity score and constraints.

        Routing rules:
        - Score 0.0-3.0 → Tier 1 (fast)
        - Score 3.1-6.0 → Tier 2 (balanced)
        - Score 6.1-10.0 → Tier 3 (powerful)

        Overrides:
        - agent_config.force_tier → always use specified tier
        - budget_remaining < tier cost → downgrade to cheaper tier
        - agent_config.max_tier → cap at this tier regardless of score
        """


class CostGuard:
    """Enforce per-user and per-team spending limits."""

    async def check_budget(
        self,
        user_id: UUID,
        team_id: UUID,
        estimated_cost: float,
    ) -> BudgetCheck:
        """
        Check if the estimated cost is within budget.

        Returns:
            BudgetCheck with:
            - allowed: bool
            - remaining_user: float (user's remaining daily budget)
            - remaining_team: float (team's remaining monthly budget)
            - suggested_tier: Optional[str] (cheaper tier if over budget)
        """


class BudgetCheck(BaseModel):
    """Result of budget check."""
    allowed: bool
    remaining_user: float
    remaining_team: float
    suggested_tier: Optional[str] = None   # Suggested cheaper tier if over budget
    reason: str = ""                       # Why denied (if not allowed)
```

#### Model Router Flow

```
User: "What's the weather in Paris?"  (simple Q&A)
    │
    ├─► QueryComplexityScorer.score()
    │     reasoning=1.0, domain=1.0, creativity=0.5, context=0.0, length=1.0
    │     overall = 0.30*1.0 + 0.25*1.0 + 0.20*0.5 + 0.15*0.0 + 0.10*1.0 = 0.75
    │
    ├─► ModelRouter.route(score=0.75)  →  Tier 1 (fast: claude-haiku-4.5)
    │
    └─► Cost: ~$0.001 instead of ~$0.02 (95% savings)


User: "Refactor this 500-line module into clean architecture with DI"  (complex)
    │
    ├─► QueryComplexityScorer.score()
    │     reasoning=9.0, domain=8.0, creativity=7.0, context=6.0, length=8.0
    │     overall = 0.30*9.0 + 0.25*8.0 + 0.20*7.0 + 0.15*6.0 + 0.10*8.0 = 7.90
    │
    ├─► ModelRouter.route(score=7.90)  →  Tier 3 (powerful: claude-opus-4)
    │
    └─► Cost: ~$0.10 (justified for complex work)
```

### AgentModelConfig Extensions

Extend the existing `AgentModelConfig` in Section 3A to support MoE:

```python
class AgentModelConfig(BaseModel):
    """LLM configuration per agent -- extended for MoE."""
    model_name: str = "anthropic/claude-sonnet-4.5"   # Default/fallback model
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)
    provider_overrides: dict[str, Any] = {}

    # === MoE Configuration (New) ===
    enable_model_routing: bool = True       # Use Model Router (False = always use model_name)
    force_tier: Optional[str] = None        # Override: always use this tier ("fast"/"balanced"/"powerful")
    max_tier: Optional[str] = None          # Cap: never exceed this tier
    custom_tiers: list[ModelTier] = []      # Agent-specific tiers (empty = use defaults)

    # === Budget ===
    daily_budget_usd: float = Field(default=5.0, ge=0.0)   # Max daily spend per user
    monthly_budget_usd: float = Field(default=100.0, ge=0.0)  # Max monthly spend per team
```

### MoE Integration Points

Where MoE plugs into the existing architecture:

```
┌────────────────────────────────────────────────────────────┐
│                  Phase Integration Map                      │
├──────────┬──────────────────────────────────────────────────┤
│ Phase 2  │ QueryComplexityScorer, ModelRouter, ModelTier,   │
│          │ CostGuard, ComplexityScore, BudgetCheck          │
│          │ + AgentModelConfig MoE extensions                │
│          │ + AgentDependencies gets model_router, cost_guard│
├──────────┼──────────────────────────────────────────────────┤
│ Phase 3  │ Complexity score cache (Redis, TTL 5min)         │
│          │ Routing decision cache (Redis, TTL 1min)         │
│          │ Budget counters (Redis, atomic increment)        │
├──────────┼──────────────────────────────────────────────────┤
│ Phase 4  │ GET /v1/moe/tiers                                │
│          │ GET /v1/moe/routing-stats                         │
│          │ GET /v1/moe/budget?user_id=...                    │
│          │ usage_log tracks model_tier + routing_decision    │
├──────────┼──────────────────────────────────────────────────┤
│ Phase 7  │ ExpertGate, ExpertSelector, ResponseAggregator,  │
│          │ ExpertScore, SelectionStrategy, SelectionResult   │
│          │ + Replaces simple AgentRouter with ExpertGate     │
│          │ + routing_decision_log for analytics              │
└──────────┴──────────────────────────────────────────────────┘
```

### MoE Database Additions

```sql
-- Add to usage_log (Phase 4 table)
ALTER TABLE usage_log ADD COLUMN model_tier TEXT;           -- "fast"/"balanced"/"powerful"
ALTER TABLE usage_log ADD COLUMN complexity_score FLOAT;    -- 0.0-10.0
ALTER TABLE usage_log ADD COLUMN routing_strategy TEXT;     -- "top_1"/"ensemble"/etc.
ALTER TABLE usage_log ADD COLUMN agents_considered INTEGER; -- How many agents were scored

-- New table: routing_decision_log (Phase 7)
CREATE TABLE routing_decision_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES team(id),
    conversation_id UUID REFERENCES conversation(id),
    message_id UUID REFERENCES message(id),

    -- Expert Gate results
    strategy TEXT NOT NULL,                          -- "top_1", "top_k", "ensemble", "cascade"
    scores JSONB NOT NULL,                           -- [{agent_slug, overall, skill_match, ...}]
    selected_agents TEXT[] NOT NULL,                  -- Agent slugs that were selected
    confidence_threshold FLOAT NOT NULL DEFAULT 0.6,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,

    -- Model Router results
    complexity_score FLOAT,                          -- 0.0-10.0
    complexity_dimensions JSONB,                     -- {reasoning, domain, creativity, context, length}
    selected_tier TEXT,                               -- "fast"/"balanced"/"powerful"
    selected_model TEXT,                              -- Actual model name used
    tier_override_reason TEXT,                        -- "force_tier"/"budget_cap"/"agent_config"/NULL

    -- Cost
    estimated_cost FLOAT,
    actual_cost FLOAT,

    -- Timing
    gate_latency_ms FLOAT,                           -- Time for expert scoring
    router_latency_ms FLOAT,                         -- Time for complexity scoring
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_routing_log_team ON routing_decision_log(team_id, created_at DESC);
CREATE INDEX idx_routing_log_conversation ON routing_decision_log(conversation_id);
CREATE INDEX idx_routing_log_tier ON routing_decision_log(selected_tier, created_at DESC);
```

---

## 3D. Agent Collaboration Protocol

Agents are not isolated responders. They are **autonomous collaborators** that can delegate work, request reports, coordinate multi-step workflows, and learn from each other's results. This section defines the protocol that enables agents to interact as a team.

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

### Capability 3: Task Delegation

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

#### Delegation Flow

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

**Peer Review** (iterative quality gate):
```
User: "Write comprehensive API documentation"
    │
    ├─► Kyra assigns: Max (writer) + Luke (reviewer)
    │
    │   Round 1:
    │     Max writes docs → Luke reviews → "Missing error codes section"
    │   Round 2:
    │     Max revises → Luke reviews → "Looks good, approved"
    │
    └─► Kyra delivers Luke-approved documentation to user
```

**Brainstorm** (parallel perspectives):
```
User: "How should we implement real-time notifications?"
    │
    ├─► Kyra sends prompt to all agents in parallel:
    │   ├─ Luke: "WebSockets with Redis pub/sub -- best for bidirectional"
    │   ├─ Ada: "SSE is simpler, sufficient for one-way. Data shows 90%
    │   │        of our notifications are server→client only"
    │   └─ Max: "Consider push notifications for mobile users too"
    │
    └─► Kyra synthesizes: "Recommendation: SSE for web (simpler, covers 90%
        of cases per Ada's analysis), with WebSocket upgrade path for
        real-time features. Add push notifications for mobile (Max's input)."
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

### When Agents Decide to Collaborate

The agent's system prompt includes collaboration guidance:

```
## Collaboration Guidelines

You can delegate tasks to specialist agents when:
1. The query requires expertise you don't have (check your skills)
2. The task has clearly separable sub-problems
3. Multiple perspectives would improve the answer
4. You need data or analysis you can't produce yourself

Available collaboration patterns:
- delegate_task: Quick specialist sub-task (use most often)
- request_report: Formal structured analysis
- start_collaboration: Multi-agent coordinated workflow

DO NOT delegate when:
1. You can answer the question directly from your skills
2. The delegation would cost more than the value it adds
3. The question is a simple factual query
4. You're already at delegation depth 3

Cost awareness: Each delegation = new LLM call. Prefer direct answers
for simple queries. Reserve delegation for genuinely complex tasks.
```

### Collaboration Database Tables

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


-- 22. collaboration_participant
CREATE TABLE collaboration_participant (
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
CREATE INDEX idx_collab_participant_session ON collaboration_participant (session_id, role);
CREATE INDEX idx_collab_participant_agent ON collaboration_participant (agent_id, status);
```

### Collaboration Integration Points

```
┌────────────────────────────────────────────────────────────────┐
│                  Phase Integration Map                          │
├──────────┬──────────────────────────────────────────────────────┤
│ Phase 4  │ API endpoints for collaboration visibility:          │
│          │   GET /v1/tasks (list delegated tasks)               │
│          │   GET /v1/tasks/{id} (task detail + result)          │
│          │   GET /v1/collaborations (active sessions)           │
│          │   GET /v1/collaborations/{id} (session detail)       │
│          │   GET /v1/agents/{slug}/inbox (agent messages)       │
│          │   POST /v1/agents/{slug}/message (send message)      │
├──────────┼──────────────────────────────────────────────────────┤
│ Phase 6  │ Celery task: execute_agent_task(task_id)             │
│          │ Celery task: advance_collaboration(session_id)       │
│          │ Celery task: check_task_timeouts() (periodic, 30s)   │
├──────────┼──────────────────────────────────────────────────────┤
│ Phase 7  │ TaskDelegator, AgentMessageBus, CollaborationOrch,   │
│          │ ReportManager, AgentDirectory                        │
│          │ + 6 agent tools registered on all collab-enabled agents│
│          │ + 4 database tables                                  │
│          │ + Redis pub/sub for real-time task notifications      │
├──────────┼──────────────────────────────────────────────────────┤
│ Phase 8  │ Docker: collaboration worker (Celery queue)          │
│          │ Monitoring: collaboration metrics dashboard          │
└──────────┴──────────────────────────────────────────────────────┘
```

---

## 4. Phased Implementation

### Critical Constraint (Every Phase)

After EVERY phase:
```bash
python -m src.cli                    # CLI still works
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
```

---

### Phase 1: Database Foundation (Week 1)

**Goal**: Add PostgreSQL infrastructure, core ORM models, and Alembic migrations. Zero behavior changes.

#### 1.1 Dependencies

Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    # ... existing ...
    "sqlalchemy[asyncio]~=2.0.36",
    "asyncpg~=0.30.0",
    "alembic~=1.14.0",
    "pgvector~=0.3.6",
]
```

> Note: Pin with `~=` (compatible release) not `>=` (any future version). Prevents breaking upgrades.

#### 1.2 Settings Extension

Extend `src/settings.py` -- all new fields `Optional` so CLI works without DB:

```python
# Database (Optional - enables persistence)
database_url: Optional[str] = Field(
    default=None,
    description="PostgreSQL connection URL (postgresql+asyncpg://...)"
)
database_pool_size: int = Field(default=5, ge=1, le=50)
database_pool_overflow: int = Field(default=10, ge=0, le=100)

# Embeddings (Optional - enables semantic search)
embedding_model: str = Field(default="text-embedding-3-small")
embedding_api_key: Optional[str] = Field(
    default=None,
    description="OpenAI API key for embeddings (defaults to llm_api_key)"
)
embedding_dimensions: int = Field(default=1536)
```

#### 1.3 Database Engine Module

```
src/db/
    __init__.py          # Exports get_session, engine
    engine.py            # Async engine + session factory
    base.py              # Declarative base + mixins (TimestampMixin, UUIDMixin)
    models/
        __init__.py      # Import all models for Alembic discovery
        agent.py         # Agent, AgentSkill
        memory.py        # Memory (single table, discriminated)
        conversation.py  # Conversation, Message
        user.py          # User, Team, TeamMembership
    migrations/
        env.py
        versions/
```

#### 1.4 Database Schema (Phase 1 -- 9 tables)

> Reduced from 17 to 9. Additional tables added in later phases when needed.

**Core (3 tables)**:
| Table | Key Columns | Notes |
|-------|-------------|-------|
| `user` | id (UUID), email, password_hash, display_name, created_at | bcrypt hash |
| `team` | id (UUID), name, slug, owner_id (FK user), settings (JSONB) | Multi-tenant root |
| `team_membership` | user_id, team_id, role (ENUM: owner/admin/member/viewer) | RBAC |

**Agent (2 tables)**:
| Table | Key Columns | Notes |
|-------|-------------|-------|
| `agent` | id (UUID), team_id (FK), name, slug, personality_prompt, model_name, skill_names (TEXT[]), config (JSONB), status | Named agents |
| `agent_skill` | Reserved for future DB-stored skills | Not populated in Phase 1 |

**Conversation (2 tables)**:
| Table | Key Columns | Notes |
|-------|-------------|-------|
| `conversation` | id (UUID), agent_id (FK), user_id (FK), team_id (FK), title, message_count, token_count, created_at, last_message_at | |
| `message` | id (UUID), conversation_id (FK), role (ENUM: user/assistant/system/tool), content (TEXT), tool_calls (JSONB), token_count, created_at | Stores full conversation history |

**Memory (2 tables)**:
| Table | Key Columns | Notes |
|-------|-------------|-------|
| `memory` | id (UUID), team_id (FK), agent_id (FK nullable), user_id (FK nullable), memory_type (ENUM), content (TEXT), embedding (vector(1536)), importance (1-10), access_count, is_pinned, source_conversation_id, metadata (JSONB), created_at, last_accessed_at, expires_at, superseded_by (self-FK) | Single table, all types |
| `memory_tag` | id, memory_id (FK), tag (TEXT) | Categorical tagging |

**Indexes**:
```sql
-- Vector similarity search
CREATE INDEX idx_memory_embedding ON memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Filtered vector search (most common query pattern)
CREATE INDEX idx_memory_team_type ON memory (team_id, memory_type)
    WHERE expires_at IS NULL OR expires_at > NOW();

-- Conversation lookup
CREATE INDEX idx_message_conversation ON message (conversation_id, created_at);

-- Agent per team
CREATE INDEX idx_agent_team ON agent (team_id, status);
```

#### 1.5 Pydantic Models

```
src/models/
    __init__.py
    agent_models.py     # AgentDNA, AgentPersonality, AgentModelConfig, AgentMemoryConfig,
                        # AgentBoundaries, AgentStatus, VoiceExample, RetrievalWeights
    memory_models.py    # MemoryCreate, MemoryRecord, MemorySearchRequest, MemorySearchResult
    conversation_models.py  # ConversationCreate, MessageCreate
    user_models.py      # UserCreate, TeamCreate, TeamMembership
```

**AgentDNA model** (central concept -- full definition in Section 3A):
```python
# See Section 3A for the complete AgentDNA model and all supporting models.
# Phase 1 implements the Pydantic models from Section 3A as the source of truth.
# The ORM `agent` table stores AgentDNA as a combination of:
#   - Top-level columns: id, team_id, name, slug, tagline, status, created_at, updated_at
#   - config JSONB: personality, model, memory, boundaries (serialized AgentDNA subsections)
#   - skill_names TEXT[]: shared_skill_names + custom_skill_names + disabled_skill_names

class RetrievalWeights(BaseModel):
    """Weights for 5-signal memory retrieval scoring."""
    semantic: float = Field(default=0.35, ge=0.0, le=1.0)
    recency: float = Field(default=0.20, ge=0.0, le=1.0)
    importance: float = Field(default=0.20, ge=0.0, le=1.0)
    continuity: float = Field(default=0.15, ge=0.0, le=1.0)
    relationship: float = Field(default=0.10, ge=0.0, le=1.0)
```

#### 1.6 Repository Layer

```python
# src/db/repositories/base.py
class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    def __init__(self, session: AsyncSession) -> None: ...
    async def get_by_id(self, id: UUID) -> Optional[T]: ...
    async def create(self, **kwargs) -> T: ...
    async def update(self, id: UUID, **kwargs) -> T: ...
    async def delete(self, id: UUID) -> bool: ...

# src/db/repositories/memory_repo.py
class MemoryRepository(BaseRepository[MemoryORM]):
    async def search_by_embedding(
        self, embedding: list[float], team_id: UUID,
        agent_id: Optional[UUID], memory_types: list[MemoryType],
        limit: int = 20
    ) -> list[MemoryORM]: ...

    async def find_similar(
        self, embedding: list[float], threshold: float = 0.92
    ) -> list[MemoryORM]: ...
```

#### 1.7 Tests for Phase 1

```
tests/
    test_db/
        conftest.py          # Test DB fixtures (async, uses test database)
        test_engine.py       # Connection, session creation
        test_models.py       # ORM model validation, relationships
        test_repositories.py # CRUD operations, vector search
    test_models/
        test_agent_models.py
        test_memory_models.py
```

**Acceptance Criteria**:
- [ ] `alembic upgrade head` creates all 9 tables
- [ ] `alembic downgrade base` drops cleanly
- [ ] Repository CRUD works for all entities
- [ ] Vector search returns results sorted by cosine similarity
- [ ] CLI works unchanged (`python -m src.cli`)
- [ ] All existing tests pass

---

### Phase 2: Bulletproof Memory System + Model Router (Week 2)

**Goal**: Build the complete memory system as specified in Section 3B -- all 7 memory types, 5-signal retrieval, append-only log, contradiction detection, and context compaction shield. Also build the Model Router (MoE Layer 2, Section 3C) -- QueryComplexityScorer, ModelRouter, CostGuard -- enabling per-query model tier selection. This is the heart of the platform.

#### 2.1 Memory Module Structure

```
src/memory/
    __init__.py
    types.py              # MemoryType enum (all 7 types), tier constants
    embedding.py          # EmbeddingService (OpenAI API, batch, LRU cache)
    retrieval.py          # MemoryRetriever (5-signal parallel pipeline per Section 3B)
    storage.py            # MemoryExtractor (double-pass extraction)
    contradiction.py      # ContradictionDetector (detect + resolve conflicts)
    compaction_shield.py  # CompactionShield (extract before context trim)
    prompt_builder.py     # MemoryPromptBuilder (7-layer prompt with type sections)
    token_budget.py       # TokenBudgetManager (estimates + reserved allocations)
    tier_manager.py       # TierManager (promote/demote between L1/L2/L3)
    memory_log.py         # MemoryAuditLog (append-only provenance tracking)
```

#### 2.2 Embedding Service

```python
class EmbeddingService:
    """Generate and cache text embeddings."""

    def __init__(self, api_key: str, model: str, dimensions: int) -> None: ...

    async def embed_text(self, text: str) -> list[float]:
        """Embed single text. Uses in-memory LRU cache (1000 entries)."""

    async def embed_batch(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        """Embed multiple texts in batches. Respects rate limits."""

    def _cache_key(self, text: str) -> str:
        """SHA-256 of normalized text."""
```

**Design decisions:**
- In-memory LRU cache (not Redis) for Phase 2. Redis cache added in Phase 3.
- Batch embedding with configurable batch size (OpenAI supports up to 2048 inputs)
- Automatic retry with exponential backoff on 429s
- Cost tracking: log tokens used per embed call

#### 2.3 Memory Retrieval Pipeline (CRITICAL PATH)

Implements the full 5-signal pipeline from Section 3B. This is the most important component -- called on every user message.

```python
class MemoryRetriever:
    """
    5-signal parallel retrieval with tier-aware caching.

    See Section 3B for the complete 7-step pipeline diagram.
    Signals: semantic similarity, recency, importance/pinned,
    conversation continuity, relationship graph.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        weights: RetrievalWeights,
        hot_cache: Optional[HotMemoryCache] = None,
    ) -> None: ...

    async def retrieve(
        self,
        query: str,
        team_id: UUID,
        agent_id: UUID,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        token_budget: int = 2000,
    ) -> RetrievalResult:
        """
        Full retrieval pipeline.

        Returns RetrievalResult with:
        - memories: list[ScoredMemory] (scored, deduped, within budget)
        - formatted_prompt: str (ready to inject into system prompt)
        - stats: RetrievalStats (signals_hit, cache_hit, total_ms)
        - contradictions: list[Contradiction] (disputed memories found)
        """
```

#### 2.3.1 Contradiction Detection

```python
class ContradictionDetector:
    """Detect conflicting memories during storage and retrieval."""

    async def check_on_store(
        self, new_memory: MemoryCreate, team_id: UUID, agent_id: UUID
    ) -> ContradictionResult:
        """Check new memory against existing. See Section 3B for full logic."""

    async def check_on_retrieve(
        self, memories: list[ScoredMemory]
    ) -> list[Contradiction]:
        """Flag contradictions within retrieved set for prompt marking."""
```

#### 2.3.2 Context Compaction Shield

```python
class CompactionShield:
    """
    Protect memories from context window trimming.

    MUST be called BEFORE any context compaction occurs.
    Implements double-pass extraction from Section 3B.
    """

    async def extract_before_compaction(
        self,
        messages_to_compact: list[MessageRecord],
        team_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
    ) -> CompactionResult:
        """
        Double-pass extraction:
        Pass 1: Primary LLM extracts all facts/events/preferences
        Pass 2: Verification LLM reviews Pass 1 for missed items
        Merge: Union of both passes (deduplicated)
        Persist: All memories saved to PostgreSQL with provenance
        """
```

#### 2.3.3 Append-Only Audit Log

```python
class MemoryAuditLog:
    """
    Immutable record of every memory lifecycle event.

    Writes to memory_log table. NEVER updates or deletes.
    Enables point-in-time memory state reconstruction.
    """

    async def log_created(self, memory_id: UUID, content: str, source: str) -> None: ...
    async def log_updated(self, memory_id: UUID, old: str, new: str, reason: str) -> None: ...
    async def log_superseded(self, old_id: UUID, new_id: UUID, reason: str) -> None: ...
    async def log_promoted(self, memory_id: UUID, old_tier: str, new_tier: str) -> None: ...
    async def log_contradiction(self, memory_a: UUID, memory_b: UUID, resolution: str) -> None: ...

    async def reconstruct_at(self, timestamp: datetime, team_id: UUID) -> list[MemorySnapshot]:
        """Reconstruct exact memory state at any point in history."""
```

#### 2.4 Memory Storage Pipeline (Post-Conversation)

After a conversation ends (or every N messages per `summarize_interval`):

```
Conversation messages
    │
    ├─► PASS 1: Primary extraction (see Section 3B extraction prompt)
    │   LLM extracts all 7 memory types with importance + confidence scores
    │   Returns: list[ExtractedMemory]
    │
    ├─► PASS 2: Verification extraction (different prompt)
    │   "Review the messages AND Pass 1 results. What was missed?"
    │   Returns: list[ExtractedMemory] (additions only)
    │
    ├─► MERGE Pass 1 + Pass 2 (deduplicate by cosine > 0.95)
    │
    ├─► For each extracted memory:
    │   ├─► Generate embedding
    │   ├─► Run ContradictionDetector.check_on_store()
    │   │   ├── Contradiction found → handle per Section 3B rules
    │   │   └── No contradiction → continue
    │   ├─► Deduplication check (cosine > 0.95 against existing)
    │   │   ├── Exact duplicate → SKIP (log in audit)
    │   │   ├── Same subject, different content → VERSION (increment)
    │   │   └── New → INSERT
    │   └─► Log to memory_log (append-only audit trail)
    │
    ├─► Batch insert new memories with full provenance:
    │   source_conversation_id, source_message_ids, extraction_model
    │
    ├─► Auto-classify tier:
    │   importance >= 9 or is_pinned → L1 hot (Redis)
    │   importance >= 3 → L2 warm (default)
    │   importance < 3 → still L2 (we never start at cold)
    │
    └─► Log stats (created, skipped, versioned, contradictions)
```

```python
class MemoryExtractor:
    """Double-pass memory extraction with full provenance."""

    async def extract_from_conversation(
        self,
        messages: list[MessageRecord],
        team_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
    ) -> ExtractionResult:
        """
        Returns ExtractionResult with:
        - memories_created: int
        - memories_versioned: int
        - duplicates_skipped: int
        - contradictions_found: int
        - pass1_count: int
        - pass2_additions: int
        """
```

**Importance scoring** (per Section 3B extraction prompt):

| Signal | Score | Auto-Pin? |
|--------|-------|-----------|
| User says "remember this" / "don't forget" | 10 | Yes |
| User's core identity (name, role, company) | 9 | Yes |
| Strong preference ("I always...", "I prefer...") | 8 | No |
| Decision made ("let's go with...", "we decided...") | 7 | No |
| Project-critical fact (deadline, requirement) | 6 | No |
| Useful context (tech stack, workflow) | 5 | No |
| Mild preference or opinion | 4 | No |
| Casual mention | 3 | No |
| Small talk (filtered out, not stored) | 1-2 | No |

#### 2.5 Prompt Builder (Memory-Aware, 7 Layers)

```python
class MemoryPromptBuilder:
    """Build system prompts with full agent identity and memory context."""

    def build(
        self,
        agent: AgentDNA,
        skill_metadata: str,
        retrieval_result: RetrievalResult,
        conversation_summary: Optional[str] = None,
    ) -> str:
        """
        Construct layered system prompt from AgentDNA + memories:

        Layer 1: Agent Identity + Personality    (~500 tokens, NEVER trimmed)
                 Name, tagline, traits, voice, rules
                 Populated from agent.personality template

        Layer 2: Identity Memories               (~200 tokens, NEVER trimmed)
                 Agent's self-knowledge from memory_type='identity'
                 "I am Kyra, users appreciate when I give examples"

        Layer 3: Skill Metadata (Level 1)        (~100/skill, NEVER trimmed)
                 Effective skills list with descriptions

        Layer 4: User Profile                    (~200 tokens, trim reluctantly)
                 memory_type='user_profile' memories
                 Name, timezone, company, core preferences

        Layer 5: Retrieved Memories              (token_budget, trimmed by score)
                 Formatted by type with contradiction markers
                 See Section 3B Step 6 for formatting spec

        Layer 6: Team Knowledge                  (~300 tokens, trim before L5)
                 memory_type='shared' memories

        Layer 7: Conversation Summary            (~200 tokens, trimmed FIRST)
                 Rolling summary of current conversation

        Trimming priority (first trimmed → last):
        L7 → L6 → L5 → L4 → Layers 1+2+3 NEVER trimmed
        """
```

#### 2.6 Extend Dependencies (Backward Compatible)

Add to `AgentDependencies`:
```python
# Memory (Optional - None when DB not configured)
agent_dna: Optional[AgentDNA] = None        # Full agent identity document (Section 3A)
memory_retriever: Optional[MemoryRetriever] = None
embedding_service: Optional[EmbeddingService] = None
contradiction_detector: Optional[ContradictionDetector] = None
compaction_shield: Optional[CompactionShield] = None
memory_audit_log: Optional[MemoryAuditLog] = None
tier_manager: Optional[TierManager] = None
db_session: Optional[AsyncSession] = None
user_id: Optional[UUID] = None
conversation_id: Optional[UUID] = None
```

`initialize()` updated: if `database_url` is set, create DB session + all memory services + load AgentDNA from DB. Otherwise, existing behavior.

#### 2.7 Agent Factory

Add `create_skill_agent()` factory to `src/agent.py`:

```python
def create_skill_agent(
    model_name: Optional[str] = None,
    agent_dna: Optional[AgentDNA] = None,
) -> Agent:
    """
    Create a Pydantic AI agent instance from AgentDNA.

    Uses module-level singleton pattern for CLI (no args).
    Creates fresh instance for API (with AgentDNA document).

    When AgentDNA is provided:
    1. Resolve effective_skills from DNA (shared + custom - disabled)
    2. Create SkillLoader with only those skills
    3. Select model from dna.model.model_name
    4. Register skill tools + HTTP tools
    5. Attach 7-layer MemoryPromptBuilder as system prompt decorator
    6. Return ready-to-use Agent instance
    """
```

Existing `skill_agent` singleton preserved for CLI. System prompt decorator branched:
- If `agent_dna` + `memory_retriever` exists: use `MemoryPromptBuilder` with 7 layers
- Otherwise: existing `MAIN_SYSTEM_PROMPT.format(skill_metadata=...)`

#### 2.8 Tests for Phase 2

```
tests/
    test_memory/
        conftest.py               # Memory fixtures, test embeddings, mock AgentDNA
        test_embedding.py         # Embedding generation, caching, batching
        test_retrieval.py         # 5-signal search, scoring, token budgeting
        test_storage.py           # Double-pass extraction, deduplication, versioning
        test_prompt_builder.py    # 7-layer prompt, trimming logic, identity preservation
        test_token_budget.py      # Token estimation accuracy, reserved allocations
        test_contradiction.py     # Contradiction detection, supersede vs dispute
        test_compaction_shield.py # Double-pass extraction before context trim
        test_audit_log.py         # Append-only logging, point-in-time reconstruction
        test_tier_manager.py      # Promote/demote between L1/L2/L3
        test_memory_types.py      # All 7 memory types: semantic, episodic, procedural,
                                  # agent_private, shared, identity, user_profile
```

**Key test scenarios:**
- All 7 memory types store and retrieve correctly
- 5-signal retrieval returns semantically relevant memories (mock embeddings)
- Identity memories ALWAYS appear in prompt (never trimmed)
- Pinned memories always appear regardless of recency
- Token budget is respected (never exceeds) with correct priority allocations
- Duplicate memories are detected and merged (cosine > 0.95)
- Contradictions detected: supersede when explicit, dispute when ambiguous
- Compaction shield extracts ALL facts before context trim (double-pass)
- Audit log records every memory lifecycle event (immutable)
- Tier promotion: access_count > 10 → warm-to-hot
- Tier demotion: superseded memories → cold (never deleted)
- User "remember X" creates importance=10 pinned memory
- 7-layer prompt layers trim in correct priority order (L7 first, L1-L3 never)
- CLI still works with no DB configured
- AgentDNA personality populates prompt template correctly

**Acceptance Criteria**:
- [ ] All 7 memory types implemented and tested
- [ ] 5-signal retrieval returns relevant results within 200ms (local DB)
- [ ] Double-pass extraction persists memories with full provenance
- [ ] Contradiction detection resolves supersede vs dispute correctly
- [ ] Compaction shield extracts before trim (zero memory loss)
- [ ] Append-only audit log supports point-in-time reconstruction
- [ ] Tier manager promotes/demotes based on access patterns
- [ ] Deduplication prevents duplicates (>0.95 cosine similarity)
- [ ] 7-layer prompt builder stays within token budget
- [ ] Agent factory creates agents from AgentDNA with memory-aware prompts
- [ ] CLI unchanged, API can use full memory system

---

### Phase 3: Redis + Caching Layer (Week 2-3)

**Goal**: Add Redis for caching, sessions, working memory, and rate limiting. Enables sub-100ms memory retrieval for hot data.

#### 3.1 Dependencies

```toml
"redis[hiredis]~=5.2.0",
```

#### 3.2 Settings Extension

```python
redis_url: Optional[str] = Field(default=None, description="Redis connection URL")
redis_key_prefix: str = Field(default="ska:", description="Redis key namespace prefix")
```

#### 3.3 Redis Module

```
src/cache/
    __init__.py
    client.py           # Async Redis pool creation, health check, cleanup
    working_memory.py   # WorkingMemoryCache (current conversation context)
    hot_cache.py        # HotMemoryCache (pre-warmed frequent memories)
    embedding_cache.py  # EmbeddingCache (avoid re-embedding same text)
    rate_limiter.py     # Token-bucket rate limiter
```

**Redis key namespaces:**
```
ska:working:{conversation_id}      # Current convo context (HASH, TTL 2h)
ska:hot:{agent_id}:{user_id}       # Pre-warmed memories (ZSET, TTL 15m)
ska:embed:{sha256}                  # Cached embeddings (STRING, TTL 24h)
ska:rate:{team_id}:{resource}       # Rate limit counters (STRING, TTL window)
ska:lock:{resource}:{id}            # Distributed locks (STRING, TTL 30s)
```

**Retrieval with cache (updated flow):**
```
User message arrives
    │
    ├─► Check ska:hot:{agent_id}:{user_id}
    │   ├── HIT: Return cached memories (< 5ms)
    │   └── MISS: Fall through to PostgreSQL retrieval
    │              └── After retrieval: populate hot cache
```

#### 3.4 Working Memory

In-conversation state stored in Redis (not PostgreSQL):
```python
class WorkingMemoryCache:
    """Manage active conversation state in Redis."""

    async def set_context(
        self, conversation_id: UUID, context: dict
    ) -> None: ...

    async def get_context(
        self, conversation_id: UUID
    ) -> Optional[dict]: ...

    async def append_turn(
        self, conversation_id: UUID, role: str, content: str
    ) -> None: ...
```

Working memory includes:
- Current conversation summary (auto-generated every 20 messages)
- Active skill context (which skills are loaded)
- Temporary scratchpad (agent can store intermediate results)

#### 3.5 Graceful Degradation

```python
# src/cache/client.py
class RedisManager:
    """Redis with graceful fallback to no-cache."""

    async def get_client(self) -> Optional[Redis]:
        """Returns None if Redis unavailable. All callers handle None."""

    @property
    def available(self) -> bool:
        """Health check without throwing."""
```

If Redis is down:
- Working memory: falls back to in-process dict
- Hot cache: falls back to direct PostgreSQL queries
- Rate limiting: disabled (log warning)
- Embedding cache: falls back to LRU in-memory

#### 3.6 Tests

```
tests/test_cache/
    conftest.py             # Redis test fixtures (fakeredis)
    test_working_memory.py
    test_hot_cache.py
    test_embedding_cache.py
    test_rate_limiter.py
    test_graceful_fallback.py  # Verify behavior when Redis is down
```

**Acceptance Criteria**:
- [ ] Hot cache hit returns memories in < 10ms
- [ ] Cache miss falls through to PostgreSQL correctly
- [ ] Working memory persists across API calls within conversation
- [ ] Rate limiter correctly throttles excessive requests
- [ ] All features degrade gracefully when Redis is unavailable
- [ ] CLI still works (Redis is Optional)

---

### Phase 4: Auth + API Foundation (Week 3)

**Goal**: FastAPI application with authentication, agent CRUD, and non-streaming chat.

#### 4.1 Dependencies

```toml
"fastapi~=0.115.0",
"uvicorn[standard]~=0.32.0",
"python-jose[cryptography]~=3.3.0",
"bcrypt~=4.2.0",
"python-multipart~=0.0.17",  # Form data parsing
```

#### 4.2 Auth Module

```
src/auth/
    __init__.py
    password.py       # bcrypt hash/verify (min 12 rounds)
    jwt.py            # Access token (30min) + refresh token (7d)
    api_keys.py       # API key generation (prefix: ska_), validation
    permissions.py    # Team-scoped RBAC checks
    dependencies.py   # FastAPI Depends: get_current_user, require_role
```

**Security requirements:**
- Passwords: bcrypt, min 12 rounds, min 8 chars
- JWT: RS256 or HS256, short-lived access (30min), refresh (7d)
- API keys: `ska_` prefix + 32-byte random hex, stored as SHA-256 hash
- All endpoints team-scoped (user must be team member with sufficient role)
- Prompt injection defense: user input is NEVER injected into system prompt directly. Memory content is sanitized.

#### 4.3 API Application

```
api/
    __init__.py
    app.py               # FastAPI app factory + lifespan (startup/shutdown)
    dependencies.py      # DI: get_db, get_redis, get_current_user, get_agent_deps
    middleware/
        __init__.py
        error_handler.py  # Global exception -> JSON error response
        request_id.py     # X-Request-ID header for tracing
        cors.py           # CORS configuration
    routers/
        __init__.py
        health.py         # GET /health, GET /ready (DB + Redis checks)
        auth.py           # POST /v1/auth/register, /login, /refresh, /api-keys
        agents.py         # CRUD /v1/agents
        chat.py           # POST /v1/agents/{slug}/chat (non-streaming first)
        memories.py       # GET/POST /v1/memories, POST /v1/memories/search
        conversations.py  # GET /v1/conversations, GET /v1/conversations/{id}/messages
        teams.py          # CRUD /v1/teams, /v1/teams/{slug}/members
    schemas/
        __init__.py
        common.py         # PaginatedResponse[T], ErrorResponse, RequestID
        auth.py           # RegisterRequest, LoginResponse, TokenPair
        agents.py         # AgentCreate, AgentUpdate, AgentResponse
        chat.py           # ChatRequest, ChatResponse
        memories.py       # MemorySearchRequest, MemoryResponse
        conversations.py  # ConversationResponse, MessageResponse
        teams.py          # TeamCreate, TeamResponse
```

> Note: All routes prefixed with `/v1/` for API versioning from day 1.

#### 4.4 Chat Endpoint (Non-Streaming First)

```python
@router.post("/v1/agents/{agent_slug}/chat")
async def chat(
    agent_slug: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message to a named agent.

    Flow:
    1. Resolve agent by slug + team
    2. Load/create conversation
    3. Retrieve relevant memories
    4. Build memory-aware prompt
    5. Run agent with Pydantic AI
    6. Persist messages
    7. Trigger async memory extraction
    8. Return response
    """
```

#### 4.5 App Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    engine = create_async_engine(settings.database_url, ...)
    redis = await create_redis_pool(settings.redis_url)
    app.state.engine = engine
    app.state.redis = redis

    yield

    # Shutdown
    await engine.dispose()
    if redis:
        await redis.close()
```

#### 4.6 Observability

```python
# Request/response logging middleware
class RequestLoggingMiddleware:
    """Log every request with: method, path, status, duration_ms, request_id."""

# Cost tracking
class CostTracker:
    """Track LLM token usage and estimated costs per request."""
    async def log_usage(
        self, request_id: str, model: str,
        input_tokens: int, output_tokens: int,
        embedding_tokens: int = 0,
    ) -> None:
        """Log to structured logger + accumulate in DB."""
```

#### 4.7 Tests

```
tests/test_api/
    conftest.py          # AsyncClient fixtures, test DB, test user
    test_health.py
    test_auth.py         # Register, login, refresh, API keys
    test_agents.py       # CRUD operations
    test_chat.py         # Non-streaming chat, memory integration
    test_memories.py     # Search, create, semantic retrieval
    test_teams.py        # Team CRUD, membership, permissions
    test_conversations.py
tests/test_auth/
    test_password.py
    test_jwt.py
    test_api_keys.py
    test_permissions.py
```

**Acceptance Criteria**:
- [ ] `uvicorn api.app:create_app --factory` starts
- [ ] `/health` returns 200 with DB + Redis status
- [ ] Auth flow: register -> login -> get token -> use token
- [ ] Agent CRUD: create/read/update/delete with team scoping
- [ ] Chat endpoint returns agent response with memories
- [ ] Memories searchable via POST /v1/memories/search
- [ ] Team isolation: users only see their team's data
- [ ] API docs at /docs (OpenAPI)
- [ ] CLI still works

---

### Phase 5: SSE Streaming + WebSocket (Week 3-4)

**Goal**: Add real-time streaming to the chat endpoint. SSE for simple clients, WebSocket for bidirectional.

#### 5.1 SSE Streaming via Pydantic AI UIAdapter

Pydantic AI provides a built-in `UIAdapter` pattern that eliminates manual SSE event formatting. This is the recommended approach.

**Simple dispatch (recommended for most endpoints):**
```python
from pydantic_ai.ui import UIAdapter
from fastapi import Request, Response

@router.post("/v1/agents/{agent_slug}/chat/stream")
async def chat_stream(
    agent_slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream agent response via SSE using Pydantic AI UIAdapter."""
    agent = resolve_agent(agent_slug, current_user.team_id)
    deps = build_deps(agent, current_user)

    # UIAdapter handles SSE encoding, streaming, and error handling
    return await UIAdapter.dispatch_request(
        request,
        agent=agent.pydantic_agent,
        deps=deps,
    )
```

**Advanced control (when we need custom events like memory_context):**
```python
@router.post("/v1/agents/{agent_slug}/chat/stream/advanced")
async def chat_stream_advanced(
    agent_slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Fine-grained streaming with custom events.

    Uses UIAdapter's building blocks individually:
    1. build_run_input() - Parse request
    2. run_stream_events() - Get raw AgentStreamEvents
    3. Custom encoding - Add memory_context, usage events
    4. streaming_response() - Return SSE response
    """
    run_input = await UIAdapter.build_run_input(await request.body())
    adapter = UIAdapter(agent=agent.pydantic_agent, run_input=run_input)

    async def event_generator():
        # Inject memory context event before streaming
        yield f"data: {json.dumps({'type': 'memory_context', 'count': len(memories)})}\n\n"

        async for event in adapter.run_stream_events():
            yield adapter.encode_event(event)

        # Inject usage event after completion
        yield f"data: {json.dumps({'type': 'usage', ...})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

> **Key insight**: Pydantic AI's UIAdapter handles the SSE protocol correctly (event formatting, keep-alive, error boundaries). Don't reinvent this.

#### 5.2 WebSocket (Optional Enhancement)

```python
@router.websocket("/v1/agents/{agent_slug}/ws")
async def agent_websocket(
    websocket: WebSocket,
    agent_slug: str,
):
    """
    Bidirectional WebSocket for agent chat.

    Client -> Server: {"type": "message", "content": "..."}
    Client -> Server: {"type": "cancel"}  # Cancel current generation
    Client -> Server: {"type": "ping"}

    Server -> Client: {"type": "text_delta", "content": "..."}
    Server -> Client: {"type": "tool_call", ...}
    Server -> Client: {"type": "done", ...}
    Server -> Client: {"type": "pong"}
    """
```

WebSocket adds:
- Client can cancel mid-generation
- Typing indicators
- Real-time memory notifications ("I remembered something relevant...")

#### 5.3 Tests

```
tests/test_api/
    test_streaming.py     # SSE event format, ordering, error handling
    test_websocket.py     # WS connect, message, cancel, disconnect
```

**Acceptance Criteria**:
- [ ] SSE endpoint streams token-by-token
- [ ] Tool calls emit structured events during stream
- [ ] Usage stats sent in `done` event
- [ ] Error events sent on failure (not broken stream)
- [ ] WebSocket connects and exchanges messages
- [ ] Client cancel stops generation

---

### Phase 6: Background Processing (Week 4)

**Goal**: Celery workers for memory extraction, consolidation, and scheduled jobs.

#### 6.1 Dependencies

```toml
"celery[redis]~=5.4.0",
```

#### 6.2 Worker Structure

```
workers/
    __init__.py
    celery_app.py         # Celery config (Redis broker, JSON serializer)
    schedules.py          # Celery Beat schedule
    tasks/
        __init__.py
        memory_tasks.py   # extract_memories, consolidate_memories
        agent_tasks.py    # scheduled_agent_run
        cleanup_tasks.py  # expire_tokens, stale_sessions, old_conversations
```

#### 6.3 Memory Consolidation (Celery Beat, every 6 hours)

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

#### 6.4 Scheduled Agent Runs

```python
@celery_app.task(name="agent.scheduled_run")
def scheduled_agent_run(
    agent_id: str, message: str, user_id: str
) -> dict:
    """
    Run an agent on a schedule (e.g., "Summarize my emails daily at 9am").

    Creates a conversation, runs the agent, persists results.
    Optionally delivers result via webhook/integration.
    """
```

#### 6.5 Beat Schedule

```python
beat_schedule = {
    "memory-consolidation": {
        "task": "memory.consolidate",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
    },
    "cleanup-expired": {
        "task": "cleanup.expire_stale",
        "schedule": crontab(minute=0, hour=0),  # Daily midnight UTC
    },
}
# + Dynamic schedules from scheduled_job table
```

#### 6.6 Tests

```
tests/test_workers/
    conftest.py            # Celery test fixtures (eager mode)
    test_memory_tasks.py   # Consolidation logic
    test_agent_tasks.py    # Scheduled runs
    test_cleanup_tasks.py
```

**Acceptance Criteria**:
- [ ] Memory extraction runs after conversation ends
- [ ] Consolidation merges duplicates and summarizes old memories
- [ ] Scheduled agent runs execute at configured times
- [ ] Expired tokens/sessions cleaned up
- [ ] All tasks retry on transient failures (max 3)
- [ ] Task results logged with durations

---

### Phase 7: Agent Collaboration, MoE Expert Gate & Autonomous Teamwork (Week 5)

**Goal**: Build the full agent collaboration stack from Sections 3C and 3D. This includes:
- **MoE Expert Gate** (Section 3C): Multi-signal agent selection with 4 strategies
- **Task Delegation** (Section 3D): Agents assign sub-tasks to specialists with budget/depth limits
- **Agent Messaging** (Section 3D): Internal inter-agent communication
- **Report System** (Section 3D): Structured analysis requests with typed deliverables
- **Collaboration Sessions** (Section 3D): Multi-agent workflows (supervisor-worker, pipeline, peer-review, brainstorm, consensus)
- **Agent Handoff** (existing): Conversation transfers between agents
- **Multi-Agent Conversations** (existing): Multiple agents in one thread

This unlocks the "unlimited agents" promise -- agents aren't isolated responders, they're an **autonomous collaborating team** that can delegate, review each other's work, and coordinate complex workflows.

> **Note**: Model Router (MoE Layer 2) is built in Phase 2. Memory system is built in Phase 2 (ADR-7). This phase builds all **inter-agent** capabilities on top of those foundations. Adds 7 database tables.

#### 7.1 Agent Router (Smart Dispatch)

```python
class AgentRouter:
    """
    Route messages to the best agent for the task.

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
        1. If user @mentions an agent → route directly
        2. If current_agent can handle it (has matching skills) → keep
        3. Score all active agents by skill relevance → pick best
        4. If no good match → use team's default agent

        Returns RoutingDecision with:
        - agent_slug: str
        - confidence: float
        - reason: str ("user_mention", "skill_match", "handoff", "default")
        """
```

#### 7.2 Agent-to-Agent Handoff

When an agent encounters a question outside its expertise:

```
User asks Kyra about code review
    │
    ├─► Kyra recognizes: "code_review" skill is Luke's specialty
    │
    ├─► Kyra responds: "Great question! Let me bring in Luke -- he's our
    │   code review specialist. Luke, Sarah is asking about..."
    │
    ├─► System creates handoff record:
    │   {from_agent: "kyra", to_agent: "luke", reason: "skill_match",
    │    context_summary: "User needs code review help", conversation_id: "..."}
    │
    ├─► Luke receives:
    │   - Full conversation history (from message table)
    │   - Kyra's handoff context summary
    │   - User profile memories (shared across agents)
    │   - Luke's own identity + private memories
    │
    └─► Conversation continues with Luke
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

#### 7.3 Multi-Agent Conversations

A single conversation with multiple agents participating:

```
User: "I need help planning a dinner party"
    │
    ├─► Kyra (general): "I'd love to help! Let me pull in some specialists."
    │
    ├─► Kyra invites Ada (data) + Chef (recipes):
    │   POST /v1/conversations/{id}/agents
    │   {"add": ["ada", "chef"]}
    │
    ├─► System tags messages with responding agent:
    │   {role: "assistant", agent_slug: "kyra", content: "..."}
    │   {role: "assistant", agent_slug: "chef", content: "..."}
    │
    └─► Each agent sees:
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

#### 7.4 Team Memory Bus

When one agent learns something team-relevant, it should be available to all agents:

```
Kyra learns: "User's company switched to PostgreSQL"
    │
    ├─► MemoryExtractor classifies: memory_type='shared' (team-relevant fact)
    │
    ├─► Stored with: agent_id=NULL, team_id=team_123
    │
    ├─► Hot cache invalidated for all agents in team
    │   (they'll pick up the new shared memory on next retrieval)
    │
    └─► All agents now know about the PostgreSQL switch
        without any explicit "tell Luke about this"
```

This happens automatically via the memory extraction pipeline (Phase 2). The agent router and handoff system just ensure that agents can seamlessly transfer context when conversations cross expertise boundaries.

#### 7.5 Agent Discovery API

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

#### 7.6 Tests

```
tests/test_collaboration/
    test_agent_router.py        # Routing decisions, @mention parsing
    test_handoff.py             # Agent-to-agent handoff, context preservation
    test_multi_agent.py         # Multi-participant conversations
    test_team_memory_bus.py     # Shared memory propagation
    test_agent_discovery.py     # Skill-based agent recommendation
```

**Acceptance Criteria**:
- [ ] @mention routing directs to correct agent
- [ ] Skill-based routing picks best agent for query
- [ ] Handoff preserves conversation history + user profile for target agent
- [ ] Multi-agent conversation shows per-agent attribution
- [ ] Shared memories propagate to all agents in team
- [ ] Agent discovery returns relevant recommendations
- [ ] Existing single-agent conversations unaffected (backward compatible)

---

### Phase 8: Docker + Deployment (Week 5-6)

**Goal**: Containerized deployment to Railway/Render.

#### 8.1 Docker Configuration

```
docker/
    Dockerfile            # Multi-stage: python:3.11-slim + uv + app
    Dockerfile.worker     # Same base, celery entrypoint
    docker-compose.yml    # Local dev: api + worker + beat + postgres + redis
    docker-compose.test.yml  # CI: ephemeral test DB + Redis
    .dockerignore
```

**Dockerfile highlights:**
```dockerfile
# Stage 1: Dependencies
FROM python:3.11-slim AS deps
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -e .

# Stage 2: App
FROM python:3.11-slim AS app
COPY --from=deps /usr/local /usr/local
COPY src/ src/
COPY api/ api/
COPY skills/ skills/
COPY alembic.ini .
EXPOSE 8000
CMD ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

#### 8.2 Docker Compose (Local Dev)

```yaml
services:
  api:
    build: { context: ., dockerfile: docker/Dockerfile }
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    env_file: .env

  worker:
    build: { context: ., dockerfile: docker/Dockerfile.worker }
    command: celery -A workers.celery_app worker -l info
    depends_on: [postgres, redis]

  beat:
    build: { context: ., dockerfile: docker/Dockerfile.worker }
    command: celery -A workers.celery_app beat -l info
    depends_on: [redis]

  postgres:
    image: pgvector/pgvector:pg16
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: skill_agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dev}

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

#### 8.3 Deployment Configs

```
deploy/
    railway/
        railway.toml      # 3 services: api (web), worker, beat
        Procfile
    render/
        render.yaml        # Blueprint: web + 2 workers + managed PG + Redis
```

#### 8.4 CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_PASSWORD: test }
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv pip install -e ".[dev]"
      - run: alembic upgrade head
      - run: pytest tests/ -v --tb=short
      - run: ruff check src/ tests/ api/ workers/
      - run: mypy src/
```

#### 8.5 Tests

```
tests/test_docker/
    test_compose.py       # docker-compose up health checks (integration)
```

**Acceptance Criteria**:
- [ ] `docker-compose up` starts all services
- [ ] API reachable at :8000, health check passes
- [ ] Worker processes Celery tasks
- [ ] Migrations run automatically on startup
- [ ] CI pipeline passes on all branches
- [ ] Image size < 500MB

---

### Phase 9: Platform Integrations (Week 6)

**Goal**: Telegram and Slack adapters with webhook receivers.

#### 9.1 Integration Module

```
integrations/
    __init__.py
    base.py              # Abstract PlatformAdapter
    telegram/
        __init__.py
        adapter.py       # TelegramAdapter (format, send, parse)
        webhook.py       # Webhook receiver + signature validation
    slack/
        __init__.py
        adapter.py       # SlackAdapter (Block Kit formatting)
        webhook.py       # Event receiver + signature verification
```

#### 9.2 Abstract Adapter

```python
class PlatformAdapter(ABC):
    """Base class for messaging platform integrations."""

    @abstractmethod
    async def validate_webhook(self, request: Request) -> bool: ...

    @abstractmethod
    async def parse_message(self, payload: dict) -> IncomingMessage: ...

    @abstractmethod
    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    def format_response(self, text: str) -> str:
        """Convert markdown to platform-specific format."""
```

#### 9.3 Integration Flow

```
External platform
    │
    ├─► POST /v1/webhooks/telegram (or /slack)
    │
    ├─► Validate signature (HMAC for Telegram, signing secret for Slack)
    │
    ├─► Parse incoming message -> IncomingMessage
    │
    ├─► Resolve agent (by platform connection config)
    │
    ├─► Respond 200 immediately (Slack requires < 3s)
    │
    ├─► Dispatch to Celery: agent_tasks.handle_platform_message
    │
    └─► Worker: run agent -> format response -> send via platform API
```

#### 9.4 Database Additions

```sql
-- Added in Phase 9 migration
CREATE TABLE platform_connection (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES team(id),
    agent_id UUID REFERENCES agent(id),
    platform TEXT NOT NULL,           -- 'telegram', 'slack'
    credentials JSONB NOT NULL,       -- Encrypted bot tokens
    webhook_url TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### 9.5 Tests

```
tests/test_integrations/
    test_telegram.py     # Webhook validation, message parsing, response formatting
    test_slack.py        # Same for Slack
    test_adapter.py      # Abstract adapter contract tests
```

**Acceptance Criteria**:
- [ ] Telegram bot receives and responds to messages
- [ ] Slack app handles @mentions and DMs
- [ ] Webhook signatures validated (rejects invalid)
- [ ] Responses formatted for each platform (Markdown -> Telegram, Block Kit -> Slack)
- [ ] Platform messages trigger memory extraction

---

## 5. Files Modified (Existing)

| File | Phase | Changes |
|------|-------|---------|
| `pyproject.toml` | 1,3,4,6 | Add dependencies incrementally |
| `src/settings.py` | 1,3 | Add Optional DB/Redis/embedding fields + FeatureFlags |
| `src/dependencies.py` | 2 | Add Optional AgentDNA, memory services, db_session fields |
| `src/agent.py` | 2 | Add `create_skill_agent(agent_dna)` factory |
| `src/prompts.py` | 2 | Add 7-layer memory-aware prompt template |
| `.env.example` | 1 | Add DATABASE_URL, REDIS_URL, EMBEDDING_API_KEY, etc. |

> All changes to existing files are ADDITIVE. No existing behavior removed or altered.

## 6. New Directory Summary

| Directory | Phase | Purpose |
|-----------|-------|---------|
| `src/db/` | 1 | SQLAlchemy engine, ORM, migrations, repositories |
| `src/models/` | 1 | Pydantic models for agents, memories, users, teams |
| `src/memory/` | 2 | Retrieval, storage, embedding, prompt builder |
| `src/cache/` | 3 | Redis client, caches, rate limiter |
| `src/auth/` | 4 | JWT, API keys, passwords, permissions |
| `api/` | 4 | FastAPI app, routers, schemas, middleware |
| `workers/` | 6 | Celery app, tasks, schedules |
| `integrations/` | 9 | Platform adapters (Telegram, Slack) |
| `docker/` | 8 | Dockerfiles, docker-compose |
| `deploy/` | 8 | Railway/Render configs |
| `.github/workflows/` | 8 | CI/CD pipeline |

---

## 7. Observability Strategy

### Layer 1: Logfire (Already Integrated)

The codebase already has Logfire instrumentation in `src/agent.py:19-36`. This provides:
- Pydantic AI agent tracing
- HTTP request instrumentation via httpx
- Structured logging

### Layer 2: Langfuse (Add in Phase 4)

**Why**: Open-source LLM observability leader with 50+ framework connectors including Pydantic AI.

```toml
"langfuse~=2.0.0",
```

**Integration points:**
- Token usage + cost tracking per conversation
- Prompt evaluation scores
- Latency per agent step (retrieval, generation, tool calls)
- Custom cost tracking for embeddings

```python
# api/middleware/observability.py
from langfuse import Langfuse

langfuse = Langfuse()

# Per-request tracing
trace = langfuse.trace(
    name="agent_chat",
    user_id=str(current_user.id),
    metadata={"agent": agent_slug, "team": team_slug},
)

generation = trace.generation(
    name="llm_call",
    model=agent.model_name,
    usage={
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    },
)
```

### Layer 3: Structured Logging (All Phases)

Existing pattern from codebase: `f"action_name: key={value}"`

Extend to all new modules:
```python
logger.info(f"memory_retrieval: team_id={team_id}, memories_found={count}, duration_ms={duration}")
logger.info(f"embedding_generated: model={model}, tokens={tokens}, cost_usd={cost:.6f}")
logger.info(f"agent_chat: agent={slug}, input_tokens={in_t}, output_tokens={out_t}, total_cost_usd={cost:.4f}")
```

### Cost Dashboard (Phase 4+)

Track via database table:
```sql
CREATE TABLE usage_log (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES team(id),
    agent_id UUID REFERENCES agent(id),
    user_id UUID REFERENCES "user"(id),
    conversation_id UUID REFERENCES conversation(id),
    model TEXT NOT NULL,
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    embedding_tokens INT DEFAULT 0,
    estimated_cost_usd DECIMAL(10,6) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API endpoint: GET /v1/teams/{slug}/usage?period=7d
```

---

## 8. Security Deep-Dive

### Prompt Injection Defense (Multi-Layered)

Prompt injection is the #1 OWASP LLM vulnerability (2025). In a multi-tenant platform, this is critical.

**Layer 1: Input Validation**
```python
# src/security/input_validator.py
class InputValidator:
    """Validate user input before it reaches the agent."""

    # Detect common injection patterns
    SUSPICIOUS_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"<\|.*?\|>",  # Special tokens
    ]

    def validate(self, user_input: str) -> ValidationResult:
        """
        Returns ValidationResult with is_safe, risk_score, flagged_patterns.
        Does NOT block -- logs and flags for monitoring.
        """
```

**Layer 2: Memory Content Sanitization**
```python
# Memories from past conversations could contain injected instructions
def sanitize_memory_for_prompt(memory: str) -> str:
    """
    Frame memory content as data, not instructions.

    Wraps in clear delimiters:
    [REMEMBERED FACT]: {content}

    Never inject raw memory content directly into system prompt.
    """
```

**Layer 3: Output Scanning**
```python
# Scan agent responses before delivery
def scan_output(response: str, team_id: UUID) -> ScanResult:
    """
    Check for:
    - System prompt leakage
    - PII from other users/teams
    - Credential exposure
    """
```

**Layer 4: Trust Boundaries**
```
User Input (UNTRUSTED)
    │
    ├─► Input Validation (flag, don't block)
    │
    ├─► Agent processes with CONSTRAINED tools
    │   └─► Tools have per-agent permissions
    │       └─► HTTP tools: allowlist domains
    │       └─► Skill tools: read-only skill files
    │       └─► Memory tools: team-scoped only
    │
    ├─► Output Scanning
    │
    └─► Deliver to user
```

### Multi-Tenant Isolation

```
Team A                          Team B
  │                               │
  ├─ Agents (only see Team A)     ├─ Agents (only see Team B)
  ├─ Memories (team_id filter)    ├─ Memories (team_id filter)
  ├─ Conversations (team_id)      ├─ Conversations (team_id)
  └─ Embeddings (team-scoped)     └─ Embeddings (team-scoped)

Every database query includes WHERE team_id = $current_team
No exceptions. No admin backdoor.
```

### Secrets Management

- All secrets in `.env` (existing pattern via `Settings(BaseSettings)`)
- Platform connection credentials (bot tokens) encrypted at rest in JSONB
- API keys stored as SHA-256 hashes (never plaintext)
- JWT secret rotatable without downtime (support for multiple signing keys)

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Memory retrieval too slow (>500ms) | Medium | High | Redis hot cache, query optimization, pgvector index tuning |
| LLM extraction produces low-quality memories | High | Medium | Structured extraction prompt with examples, human review tool |
| Embedding API costs spiral | Medium | Medium | Batch embedding, aggressive caching, track costs per team |
| pgvector at scale (>1M memories) | Low | High | Partition by team_id, consider dedicated vector DB migration |
| Prompt injection via stored memories | Medium | High | Sanitize memory content, never include raw user input in system prompt without framing |
| Celery worker crashes lose tasks | Low | Medium | Redis persistence (AOF), task acknowledgment, dead letter queue |
| Breaking existing CLI | Low | Critical | Every phase runs CLI tests. All new deps Optional. |
| Agent routing picks wrong agent | Medium | Low | Fallback to user-specified agent; @mention always overrides router |
| Scope creep beyond 6 weeks | High | Medium | Each phase has clear acceptance criteria. Cut Phase 9 if behind. |

---

## 10. Performance Targets

| Operation | Target (p95) | Measurement |
|-----------|-------------|-------------|
| Memory retrieval (hot cache hit) | < 10ms | Redis ZRANGEBYSCORE |
| Memory retrieval (cold, DB) | < 200ms | pgvector + scoring + token budget |
| Embedding generation (single) | < 500ms | OpenAI API call |
| First SSE token | < 2s | API request to first `text_delta` event |
| Agent full response | < 30s | Typical conversation turn |
| Memory extraction (background) | < 10s | Post-conversation Celery task |
| Consolidation (per team) | < 60s | 6-hourly batch job |
| API auth (JWT validation) | < 5ms | Stateless JWT decode |

---

## 11. Migration Path (CLI -> Platform)

The CLI evolves in 3 stages:

**Stage 1 (Phase 1-2)**: CLI works as-is. No database needed.
```bash
python -m src.cli   # Pure filesystem skills, no memory
```

**Stage 2 (Phase 2+)**: CLI optionally uses memory if DB configured.
```bash
# With DATABASE_URL in .env:
python -m src.cli   # Same CLI but with persistent memory!
```

The CLI detects `database_url` in settings. If present, initializes memory services. User gets memory for free without changing their workflow.

**Stage 3 (Phase 4+)**: CLI can connect to the API backend.
```bash
python -m src.cli --agent kyra --api http://localhost:8000
# CLI becomes a thin client to the API
```

---

## 12. Glossary

| Term | Definition |
|------|-----------|
| **AgentDNA** | Complete identity document for a named agent: personality, skills, memory config, model config, boundaries (Section 3A) |
| **Named Agent** | An agent with a unique name, personality, skills, and memory (e.g., Kyra, Luke). Defined by its AgentDNA |
| **Agent Router** | Smart dispatch that routes messages to the best agent based on @mentions, skill matching, or conversation context |
| **Agent Handoff** | Transfer of conversation from one agent to another, preserving full history and user context |
| **Skill** | A modular capability package (SKILL.md + resources) using progressive disclosure |
| **Progressive Disclosure** | 3-level loading: metadata → instructions → resources |
| **Effective Skills** | The resolved skill set for an agent: shared + custom - disabled |
| **5-Signal Retrieval** | Memory retrieval pipeline using 5 parallel signals: semantic similarity, recency, importance/pinned, conversation continuity, relationship graph |
| **Working Memory** | Ephemeral conversation state (Redis, TTL 2h) |
| **Semantic Memory** | Persistent facts and preferences (PostgreSQL + pgvector) |
| **Episodic Memory** | Timestamped events and decisions from conversations |
| **Procedural Memory** | Learned tool-use patterns and workflows with success rates |
| **Agent-Private Memory** | Per-agent learning and insights, visible only to the owning agent |
| **Shared Memory** | Team-wide knowledge accessible to all agents |
| **Identity Memory** | Agent's self-knowledge; always in prompt, never trimmed, never expired |
| **User-Profile Memory** | Persistent user facts (name, timezone, company) visible to all agents |
| **Memory Tier** | Storage level: L1 Hot (Redis, <5ms), L2 Warm (PostgreSQL, <200ms), L3 Cold (PostgreSQL archive, <2s) |
| **Memory Audit Log** | Append-only `memory_log` table recording every memory lifecycle event; never modified, never deleted |
| **Compaction Shield** | Double-pass extraction that persists all facts BEFORE context window trimming occurs |
| **Contradiction Detection** | System that detects conflicting memories, resolving via supersede (explicit) or dispute (ambiguous) |
| **Memory Consolidation** | Periodic job that merges near-duplicates, summarizes old episodic memories, and manages tier demotions |
| **Hot Cache** | Pre-warmed Redis sorted set of frequently-accessed memories (L1 tier) |
| **Token Budget** | Maximum tokens allocated for memory context in system prompt, with reserved allocations per layer |
| **7-Layer Prompt** | System prompt structure: Identity → Identity Memories → Skills → User Profile → Retrieved Memories → Team Knowledge → Conversation Summary |
| **Voice Example** | Sample interaction demonstrating an agent's communication style, injected into the system prompt |
| **Mixture of Experts (MoE)** | Two-layer routing system: Expert Gate (agent selection) + Model Router (LLM tier selection) — see Section 3C |
| **Expert Gate** | Layer 1 MoE: scores all team agents on 4 signals (skill match, past performance, personality fit, load balance) to select the best agent(s) |
| **Model Router** | Layer 2 MoE: scores query complexity on 5 dimensions to select the optimal LLM tier (fast/balanced/powerful) |
| **Complexity Score** | 5-dimension assessment of query complexity (reasoning, domain, creativity, context, output length) → 0-10 overall score |
| **Model Tier** | LLM cost/capability level: Tier 1 Fast (Haiku), Tier 2 Balanced (Sonnet), Tier 3 Powerful (Opus) |
| **Selection Strategy** | How the Expert Gate uses scores: TOP_1 (route), TOP_K (consult), ENSEMBLE (merge), CASCADE (sequential) |
| **CostGuard** | Budget enforcement that caps model tier selection based on per-user daily and per-team monthly spend limits |
| **Response Aggregator** | Combines responses from multiple agents in ENSEMBLE mode into a single attributed response |
| **Task Delegation** | Agent assigns a structured sub-task to a specialist agent, receives result (Section 3D) |
| **Agent Task** | A unit of work assigned by one agent to another, with constraints (budget, timeout, depth limit) |
| **Delegation Depth** | How deep in the A→B→C delegation chain (max 3, prevents infinite loops) |
| **Agent Message Bus** | Internal point-to-point and broadcast messaging between agents (not user-visible) |
| **Collaboration Session** | A multi-agent workflow coordinated by a lead agent using a defined pattern |
| **Collaboration Pattern** | How agents interact: supervisor-worker, pipeline, peer-review, brainstorm, or consensus |
| **Supervisor-Worker** | Pattern where a lead agent assigns parallel tasks to workers and synthesizes results |
| **Pipeline** | Pattern where agents process sequentially, each receiving the previous stage's output |
| **Peer Review** | Pattern where one agent produces work and another reviews it, iterating until approved |
| **Brainstorm** | Pattern where multiple agents contribute perspectives in parallel, then lead synthesizes |
| **Report System** | Structured analysis requests with typed deliverables (code_review, research_summary, etc.) |
| **Agent Directory** | Registry for discovering agents by skill, availability, and load (Section 3D, Capability 1) |

---

## 13. Implementation Sequence Diagram

```
Week 1          Week 2          Week 3          Week 4          Week 5          Week 6
─────────────── ─────────────── ─────────────── ─────────────── ─────────────── ───────────────
Phase 1         Phase 2         Phase 4         Phase 6         Phase 7         Phase 9
DB Foundation   Bulletproof     API + Auth      Background      Agent Collab    Integrations
                Memory                          Processing
  │               │               │               │               │               │
  ├─ Models       ├─ All 7 types  ├─ FastAPI app   ├─ Celery       ├─ Router       ├─ Telegram
  ├─ AgentDNA     ├─ 5-signal     ├─ Auth layer    ├─ Mem extract  ├─ Handoff      ├─ Slack
  ├─ Migrations   ├─ Contradict   ├─ Agent CRUD    ├─ Consolid.    ├─ Multi-agent  ├─ Webhooks
  ├─ Repos        ├─ Compaction   ├─ Chat          ├─ Scheduling   ├─ Team bus     └─ Tests
  └─ Tests        ├─ Audit log    ├─ Memories      └─ Tests        └─ Tests
                  ├─ 7-layer      └─ Tests
                  └─ Tests
                  Phase 3                         Phase 8
                  Redis Cache     Phase 5         Docker
                    │             SSE + WS          │
                    ├─ Hot cache     │              ├─ Dockerfile
                    ├─ Working mem   ├─ SSE stream  ├─ Compose
                    ├─ Rate limit    ├─ WebSocket   ├─ CI/CD
                    └─ Tests         └─ Tests       └─ Deploy
```

---

## 14. Definition of Done (Entire Project)

**Agent Identity:**
- [ ] Agents defined by AgentDNA documents (personality, skills, memory, boundaries)
- [ ] Named agents (Kyra, Luke) respond with distinct personalities and voice
- [ ] Agent identity preserved across context compaction (Layer 1 never trimmed)
- [ ] Agent identity preserved across server restarts (loaded from DB)
- [ ] Creating a new agent = inserting config (no code changes, no restart)
- [ ] Shared + custom + disabled skill resolution works per agent

**Bulletproof Memory (The Seven Guarantees):**
- [ ] All 7 memory types operational: semantic, episodic, procedural, agent-private, shared, identity, user-profile
- [ ] 5-signal retrieval returns relevant memories within 200ms (p95)
- [ ] Memories NEVER lost during context compaction (compaction shield active)
- [ ] Contradictions detected and resolved (supersede or dispute with markers)
- [ ] Append-only audit log records every memory lifecycle event
- [ ] Point-in-time memory reconstruction possible from audit log
- [ ] Identity memories always in prompt, never trimmed, never expired
- [ ] Memory consolidation runs without errors (6-hourly batch job)

**Mixture of Experts (Two-Layer MoE):**
- [ ] Model Router scores query complexity on 5 dimensions (0-10 scale)
- [ ] Simple queries routed to fast/cheap model (Tier 1), complex to powerful (Tier 3)
- [ ] CostGuard enforces per-user daily and per-team monthly budget limits
- [ ] Expert Gate scores all team agents on 4 signals for smart routing
- [ ] TOP_1 routing selects best agent with confidence threshold
- [ ] ENSEMBLE mode combines responses from multiple agents with attribution
- [ ] MoE disabled gracefully via feature flags (falls back to direct dispatch + single model)
- [ ] Routing decisions logged for analytics and continuous improvement

**Agent Collaboration (Section 3D):**
- [ ] Agents can delegate tasks to specialist agents via `delegate_task` tool
- [ ] Delegation depth enforced (max 3), cycle detection prevents A→B→A loops
- [ ] Task timeouts enforced (default 120s), dead-letter queue for failed tasks
- [ ] Agent-to-agent messaging works (direct + broadcast + channel)
- [ ] Report system produces structured deliverables matching templates
- [ ] All 5 collaboration patterns work: supervisor-worker, pipeline, peer-review, brainstorm, consensus
- [ ] Collaboration sessions enforce cost caps (default $0.50) and duration limits (default 600s)
- [ ] Agent discovery finds experts by skill match + availability + load

**Platform:**
- [ ] Memories persist across conversations and sessions
- [ ] CLI works with AND without database
- [ ] API serves chat with SSE streaming
- [ ] Auth flow (register -> login -> chat) works end-to-end
- [ ] Team isolation (users only see their data)
- [ ] Agent-to-agent handoff preserves conversation context
- [ ] Docker Compose runs full stack locally
- [ ] CI/CD pipeline passes on every PR
- [ ] At least one integration (Telegram OR Slack) works
- [ ] All tests pass (unit + integration)
- [ ] No critical security issues (OWASP top 10 addressed)
- [ ] Performance targets met (memory retrieval < 200ms, first token < 2s)
- [ ] Cost tracking logs token usage per conversation

---

## 15. Conversation Lifecycle

### When Does a Conversation Start?

```
POST /v1/agents/{slug}/chat  (conversation_id = null)
  → Create new conversation (auto-generate title from first message via LLM)
  → Return conversation_id in response

POST /v1/agents/{slug}/chat  (conversation_id = "abc-123")
  → Continue existing conversation
  → Append to message history
```

### When Does a Conversation End?

| Trigger | Action |
|---------|--------|
| User sends no message for 30 min | Mark `status=idle`, trigger memory extraction |
| User explicitly closes (`DELETE /v1/conversations/{id}`) | Mark `status=closed`, trigger extraction |
| Message count exceeds 100 | Auto-summarize, continue with summary as context |
| API session ends (client disconnect) | Mark `status=idle` after TTL |

### Context Window Management

When conversation history exceeds the model's context window:

```
Messages [1-100] in database
    │
    ├─► Last 20 messages: sent to LLM verbatim
    ├─► Messages 1-80: LLM-generated rolling summary (~500 tokens)
    └─► Summary injected as Layer 5 in system prompt
```

Auto-summarization triggers:
- Every 20 messages (configurable per agent via `AgentConfig.summarize_interval`)
- Summary stored in working memory (Redis)
- Full history always persisted in PostgreSQL (never lost)

---

## 16. API Design Conventions

### Pagination (Cursor-Based)

```python
# All list endpoints use cursor-based pagination
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    cursor: Optional[str] = None  # Opaque cursor for next page
    has_more: bool
    total: Optional[int] = None   # Only included if cheap to compute

# Usage:
# GET /v1/conversations?limit=20
# GET /v1/conversations?limit=20&cursor=eyJpZCI6Ii4uLiJ9
```

> Why cursor over offset? Offset pagination breaks when items are inserted/deleted between pages. Cursor is stable.

Default `limit=20`, max `limit=100`.

### Error Responses

```python
class ErrorResponse(BaseModel):
    error: str           # Machine-readable code: "agent_not_found", "rate_limited"
    message: str         # Human-readable description
    details: Optional[dict] = None  # Additional context
    request_id: str      # For support/debugging

# Standard HTTP status codes:
# 400 - Validation error (bad input)
# 401 - Not authenticated
# 403 - Not authorized (wrong team/role)
# 404 - Resource not found
# 409 - Conflict (duplicate slug, etc.)
# 422 - Unprocessable (valid JSON but business logic error)
# 429 - Rate limited
# 500 - Internal error (never expose stack traces)
```

### Rate Limits

| Resource | Limit | Window | Scope |
|----------|-------|--------|-------|
| Chat messages | 60 | 1 min | Per user |
| API requests (general) | 300 | 1 min | Per team |
| Memory search | 30 | 1 min | Per user |
| Auth (login/register) | 10 | 1 min | Per IP |
| Embedding generation | 100 | 1 min | Per team |

Rate limit headers on every response:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1707523200
```

---

## 17. Data Lifecycle & Retention

### Retention Policies

| Data Type | Default Retention | Configurable? | Notes |
|-----------|-------------------|---------------|-------|
| Conversations | 90 days | Yes (per team) | Soft delete, then hard delete |
| Messages | Same as conversation | No | Cascade with conversation |
| Memories (semantic) | Indefinite | No | Core value of the platform |
| Memories (episodic) | 180 days | Yes | Auto-summarized after 30 days |
| Usage logs | 365 days | No | Billing/audit trail |
| Audit log | 365 days | No | Compliance |
| Sessions (Redis) | 24 hours | No | Auto-expire TTL |
| Working memory (Redis) | 2 hours | No | Auto-expire TTL |

### User Data Deletion (GDPR-Ready)

```python
# DELETE /v1/users/me
async def delete_user(current_user: User) -> None:
    """
    Hard-delete all user data:
    1. Messages authored by user
    2. Conversations where user is only participant
    3. Memories tagged with user_id
    4. Team memberships
    5. User record
    6. Invalidate all sessions (Redis)
    7. Log deletion in audit_log (anonymized)
    """
```

### Data Export

```
GET /v1/users/me/export
  → Returns ZIP containing:
    - conversations.json (all conversations + messages)
    - memories.json (all memories associated with user)
    - profile.json (user profile data)
    - usage.json (usage history)
```

---

## 18. LLM Provider Resilience

### Provider Fallback Chain

```python
class ResilientModelProvider:
    """Try providers in order until one succeeds."""

    fallback_chain: list[ProviderConfig] = [
        ProviderConfig(provider="openrouter", model="anthropic/claude-sonnet-4.5"),
        ProviderConfig(provider="openai", model="gpt-4o"),
        ProviderConfig(provider="ollama", model="llama3.1:70b"),  # Local fallback
    ]

    async def get_model(self) -> Model:
        for config in self.fallback_chain:
            if await self._health_check(config):
                return self._create_model(config)
        raise AllProvidersUnavailable()
```

**When to fall back:**
- HTTP 503/502/500 from provider
- Timeout > 30s on connection
- Rate limit (429) with no retry budget left

**When NOT to fall back:**
- Auth error (401) -- configuration issue, not transient
- Bad request (400) -- our fault, not provider's

### Embedding Provider Resilience

```python
# If OpenAI embedding API is down:
# 1. Check Redis cache first (may already have embedding)
# 2. Queue for retry (Celery task with exponential backoff)
# 3. Skip memory retrieval for this request (degrade gracefully)
# 4. Log warning: "memory_retrieval_degraded: embedding_api_unavailable"
```

---

## 19. Bootstrap & Seeding

### First-Run Setup

```bash
# After docker-compose up and migrations:
python -m src.seed

# Creates:
# 1. Default admin user (from ADMIN_EMAIL + ADMIN_PASSWORD env vars)
# 2. Default team "Personal" for admin
# 3. Default agent "Kyra" with general-purpose personality
# 4. Syncs filesystem skills to agent_skill table
```

```python
# src/seed.py
async def seed_defaults() -> None:
    """Create default data for first-run experience."""

    # Agent: Kyra (friendly generalist)
    kyra = AgentDNA(
        name="Kyra",
        slug="kyra",
        tagline="Your friendly AI companion",
        personality=AgentPersonality(
            system_prompt_template=KYRA_TEMPLATE,  # See Section 3A
            tone="friendly",
            verbosity="balanced",
            formality="adaptive",
            traits={"curious": 0.9, "empathetic": 0.8, "humorous": 0.6},
            voice_examples=[
                VoiceExample(
                    user_message="What's the weather like?",
                    agent_response="Hey! Let me check that for you real quick.",
                    context="Casual request",
                ),
            ],
            always_rules=["Greet the user by name if known", "Offer follow-up suggestions"],
            never_rules=["Give medical or legal advice"],
        ),
        shared_skill_names=["weather", "world_clock"],
        custom_skill_names=["research_assistant", "recipe_finder"],
        disabled_skill_names=[],
        model=AgentModelConfig(
            model_name=settings.llm_model,
            temperature=0.7,
        ),
        memory=AgentMemoryConfig(
            token_budget=2000,
            auto_extract=True,
            auto_pin_preferences=True,
        ),
        boundaries=AgentBoundaries(
            can_do=["research", "recommendations", "casual conversation"],
            cannot_do=["medical advice", "legal advice", "financial advice"],
            max_autonomy="execute",
        ),
        status=AgentStatus.ACTIVE,
    )

    # Agent: Luke (task-focused code specialist)
    luke = AgentDNA(
        name="Luke",
        slug="luke",
        tagline="Your no-nonsense code review partner",
        personality=AgentPersonality(
            system_prompt_template=LUKE_TEMPLATE,
            tone="direct",
            verbosity="concise",
            formality="semi-formal",
            traits={"analytical": 0.95, "detail_oriented": 0.9, "patient": 0.7},
            always_rules=["Cite specific line numbers", "Suggest concrete fixes"],
            never_rules=["Praise code that has issues"],
        ),
        shared_skill_names=["weather", "world_clock"],
        custom_skill_names=["code_review"],
        disabled_skill_names=["weather"],  # Luke doesn't do weather
        model=AgentModelConfig(
            model_name=settings.llm_model,
            temperature=0.3,  # More deterministic for code analysis
        ),
        memory=AgentMemoryConfig(
            token_budget=1500,
            auto_extract=True,
        ),
        boundaries=AgentBoundaries(
            can_do=["code review", "debugging", "architecture advice"],
            cannot_do=["small talk", "recipe suggestions"],
            escalates_to="kyra",  # Escalate non-code questions to Kyra
            max_autonomy="suggest",  # Always explain before acting
        ),
        status=AgentStatus.ACTIVE,
    )
```

### Skill Sync

On startup, sync filesystem skills to the `agent_skill` table:
```python
async def sync_skills_to_db(skill_loader: SkillLoader, session: AsyncSession) -> None:
    """
    Discover filesystem skills and ensure DB records exist.
    Does NOT overwrite DB records -- filesystem is source of truth for skill content,
    DB is source of truth for agent-skill assignments.
    """
```

---

## 20. Webhook Event Catalog

### Outbound Webhook Events

When a team configures a webhook URL, these events are delivered:

| Event | Payload | Trigger |
|-------|---------|---------|
| `conversation.created` | `{conversation_id, agent_slug, user_id}` | New conversation started |
| `conversation.completed` | `{conversation_id, message_count, duration_s}` | Conversation ended |
| `message.created` | `{message_id, conversation_id, role, content_preview}` | New message (user or assistant) |
| `memory.created` | `{memory_id, memory_type, content_preview, importance}` | New memory extracted |
| `agent.status_changed` | `{agent_id, old_status, new_status}` | Agent activated/paused/archived |
| `job.completed` | `{job_id, agent_id, result_preview}` | Scheduled job finished |
| `job.failed` | `{job_id, agent_id, error}` | Scheduled job failed |

### Webhook Delivery

```
Event occurs
    │
    ├─► Serialize payload + add metadata (event_id, timestamp, team_id)
    ├─► Sign with HMAC-SHA256 (team's webhook secret)
    ├─► POST to webhook URL with headers:
    │     X-Webhook-Signature: sha256=...
    │     X-Webhook-Event: conversation.created
    │     X-Webhook-ID: evt_abc123
    │
    ├─► Success (2xx): done
    └─► Failure: retry with exponential backoff
        Attempt 1: immediate
        Attempt 2: 1 min
        Attempt 3: 5 min
        Attempt 4: 30 min
        Attempt 5: 2 hours
        After 5 failures: mark webhook as `failing`, notify team admin
```

---

## 21. Phase Dependency Graph

```
Phase 1 (DB) ──────► Phase 2 (Memory) ──────► Phase 7 (Collaboration)
    │                    │                          │
    │                    ├──► Phase 3 (Redis) ──► Phase 5 (SSE/WS)
    │                    │                          │
    └────────────────────┴──► Phase 4 (API) ──► Phase 6 (Background)
                                  │                    │
                                  └────────────────────┴──► Phase 8 (Docker)
                                                                │
                                                                └──► Phase 9 (Integrations)
```

**Can overlap:**
- Phase 2 + Phase 3 (memory + Redis are complementary, can develop in parallel)
- Phase 5 + Phase 6 (streaming + background workers are independent)
- Phase 7 + Phase 8 (collaboration + Docker are independent)

**Strictly sequential:**
- Phase 1 must complete before Phase 2 (DB models needed for memory)
- Phase 4 must complete before Phase 5 (need API to add streaming to)
- Phase 4 must complete before Phase 7 (need agent CRUD API for router/handoff)
- Phase 8 must complete before Phase 9 (Docker needed for integration testing)

---

## 22. User Feedback Loop

### Thumbs Up/Down on Responses

```python
# POST /v1/messages/{message_id}/feedback
class FeedbackRequest(BaseModel):
    rating: Literal["positive", "negative"]
    comment: Optional[str] = None  # "This was helpful" / "Wrong information"

# Stored in message table:
# ALTER TABLE message ADD COLUMN feedback_rating TEXT;
# ALTER TABLE message ADD COLUMN feedback_comment TEXT;
```

### Feedback → Memory Quality

```
User gives thumbs-up on response
    │
    ├─► Boost importance of memories used in that response (+1)
    ├─► If procedural memory involved: increment success_rate
    └─► Log: feedback_positive: message_id={id}, memories_used=[...]

User gives thumbs-down on response
    │
    ├─► Decrease importance of memories used (-1, floor 1)
    ├─► If procedural memory involved: decrement success_rate
    ├─► Flag memories for review if importance drops below 3
    └─► Log: feedback_negative: message_id={id}, memories_used=[...]
```

This creates a reinforcement loop: good memories get boosted, bad memories decay faster.

---

## 23. Rollback Strategy

### Per-Phase Rollback

| Phase | Rollback Method |
|-------|----------------|
| Phase 1 (DB) | `alembic downgrade base` removes all tables |
| Phase 2 (Memory) | Delete `src/memory/` module, revert `dependencies.py` changes |
| Phase 3 (Redis) | Delete `src/cache/` module, all Redis keys are TTL-based (auto-expire) |
| Phase 4 (API) | Delete `api/` directory, no existing code touched |
| Phase 5 (SSE) | Remove streaming endpoints from `api/routers/chat.py` |
| Phase 6 (Workers) | Delete `workers/` directory, stop Celery processes |
| Phase 7 (Collaboration) | Delete router/handoff modules, revert message table (drop agent_id column), remove conversation_participant table |
| Phase 8 (Docker) | Delete `docker/` and `deploy/` directories |
| Phase 9 (Integrations) | Delete `integrations/`, `alembic downgrade` drops `platform_connection` |

### Database Migration Safety

```bash
# Before any migration in production:
1. Backup database: pg_dump -Fc skill_agent > backup_$(date +%Y%m%d).dump
2. Test migration on staging first
3. Run migration: alembic upgrade head
4. Verify: alembic current
5. If broken: alembic downgrade -1  (revert last migration)
6. If catastrophic: pg_restore -d skill_agent backup_YYYYMMDD.dump
```

### Feature Flags (Simple)

For gradual rollout of new features without full deployment:

```python
# src/settings.py
class FeatureFlags(BaseModel):
    """Simple boolean feature flags via environment variables."""
    enable_memory: bool = Field(default=True)           # Phase 2: Full memory system
    enable_agent_collaboration: bool = Field(default=False)  # Phase 7: Router, handoff
    enable_webhooks: bool = Field(default=False)         # Phase 9: Outbound webhooks
    enable_integrations: bool = Field(default=False)     # Phase 9: Telegram/Slack
    enable_compaction_shield: bool = Field(default=True) # Phase 2: Double-pass extraction
    enable_contradiction_detection: bool = Field(default=True)  # Phase 2: Conflict detection
    enable_model_routing: bool = Field(default=True)   # Phase 2: Model-level MoE (complexity → tier)
    enable_expert_gate: bool = Field(default=False)    # Phase 7: Agent-level MoE (multi-signal scoring)
    enable_ensemble_mode: bool = Field(default=False)  # Phase 7: Multi-agent response aggregation
    enable_task_delegation: bool = Field(default=False) # Phase 7: Agent-to-agent task delegation
    enable_collaboration: bool = Field(default=False)   # Phase 7: Multi-agent collaboration sessions
```

Checked at runtime:
```python
if settings.feature_flags.enable_memory:
    memories = await retriever.retrieve(query, ...)
else:
    memories = []  # Skip memory retrieval

if settings.feature_flags.enable_expert_gate:
    result = await expert_gate.score_and_select(message, team_id, ...)
elif settings.feature_flags.enable_agent_collaboration:
    routing = await router.route(message, team_id, ...)
else:
    agent = await registry.get_agent(team_id, agent_slug)  # Direct dispatch

if settings.feature_flags.enable_model_routing:
    tier = await model_router.route(complexity_score, agent.model, budget)
else:
    tier = ModelTier(name="default", model_name=agent.model.model_name, ...)
```
