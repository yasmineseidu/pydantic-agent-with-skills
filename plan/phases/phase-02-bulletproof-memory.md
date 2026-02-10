# Phase 2: Bulletproof Memory System

> **Timeline**: Week 2 | **Prerequisites**: Phase 1 (Database Foundation) | **Status**: Not Started

## Goal

Build the complete memory system as specified in Section 3B of the main plan -- all 7 memory types, 5-signal retrieval, append-only log, contradiction detection, and context compaction shield. This is the heart of the platform. Phase 2 introduces NO new tables (uses Phase 1 tables) but builds the entire memory intelligence layer.

## Dependencies (Install)

No new dependencies beyond Phase 1. Phase 2 uses:
- `sqlalchemy[asyncio]` (Phase 1) for database access
- `asyncpg` (Phase 1) for async PostgreSQL driver
- `pgvector` (Phase 1) for vector operations
- OpenAI embedding API via `httpx` (already in project) for text embeddings

## Settings Extensions

No new settings fields in Phase 2. Uses Phase 1's `embedding_model`, `embedding_api_key`, and `embedding_dimensions` settings.

Phase 2 adds `FeatureFlags` to `src/settings.py`:

```python
class FeatureFlags(BaseModel):
    """Simple boolean feature flags via environment variables."""
    enable_memory: bool = Field(default=True)                     # Phase 2: Full memory system
    enable_compaction_shield: bool = Field(default=True)          # Phase 2: Double-pass extraction
    enable_contradiction_detection: bool = Field(default=True)    # Phase 2: Conflict detection
    enable_agent_collaboration: bool = Field(default=False)       # Phase 7: Router, handoff
    enable_webhooks: bool = Field(default=False)                  # Phase 9: Outbound webhooks
    enable_integrations: bool = Field(default=False)              # Phase 9: Telegram/Slack
```

## New Directories & Files

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

## Database Tables Introduced

**No new tables.** Phase 2 uses the 9 tables created in Phase 1:
- `memory` -- stores all 7 memory types via the `memory_type` discriminator column
- `memory_log` -- append-only audit trail for all memory lifecycle events
- `memory_tag` -- categorical tagging for memories
- `conversation`, `message` -- for provenance tracking (source_conversation_id, source_message_ids)
- `agent` -- for agent-scoped memory queries and AgentDNA configuration

Reference: `plan/sql/schema.sql` (Phase 1 section)

## Implementation Details

### Memory Types (All 7, Built from Day 1 per ADR-7)

```
MEMORY TYPES (src/memory/types.py)

SEMANTIC ────── Facts, preferences, knowledge
  "User prefers TypeScript"
  "Project deadline is March 15"
  Versioned: contradictions tracked, latest wins in retrieval

EPISODIC ────── Events, conversations, decisions
  "On Feb 9 we decided to use PostgreSQL"
  "User was frustrated about the deploy failure"
  Timestamped: chronological ordering matters

PROCEDURAL ──── Learned workflows, tool patterns
  "Weather queries: load_skill -> http_get -> format"
  "Code review: load_skill -> read checklist -> analyze"
  Scored: success_rate, times_used, last_used

AGENT-PRIVATE ─ Per-agent learning, private insights
  "This user prefers verbose explanations from Kyra"
  "Luke learned to always ask for confirmation before deploy"
  Scoped: only visible to the owning agent

SHARED ──────── Team-wide knowledge
  "Team coding standard: PEP 8, 100 char lines"
  "Production DB is on us-east-1"
  Scoped: visible to ALL agents in the team

IDENTITY ────── Agent's self-knowledge
  "I am Kyra, I specialize in research and communication"
  "Users often tell me I'm helpful when I give examples"
  Protected: NEVER expired, NEVER consolidated, ALWAYS in prompt

USER-PROFILE ── Persistent user facts across all agents
  "User's name is Sarah"
  "User timezone: PST"
  "User's company: Acme Corp"
  Scoped: visible to all agents, attached to user_id
```

### Memory Hierarchy (3 Tiers)

```
L1 HOT ──── In the prompt right now ──── Redis + Prompt
(< 5ms)     Top-scored memories
            Current conversation state
            Agent identity (always)

L2 WARM ─── Retrievable on demand ────── PostgreSQL
(< 200ms)   All active memories
            Searchable by vector, recency, importance
            Contradiction-aware

L3 COLD ─── Archived, never deleted ──── PostgreSQL
(< 2s)      Superseded memories
            Expired low-importance memories
            Historical conversation summaries
            Full provenance chain

RAW LOG ─── Append-only audit trail ──── PostgreSQL
(archival)  Every memory creation/update/supersede event
            Every conversation message (verbatim)
            Never modified, never deleted
            Basis for complete reconstruction
```

### The Seven Guarantees

| # | Guarantee | How |
|---|-----------|-----|
| 1 | **Never loses a memory** | Append-only `memory_log`. Superseded memories move to `tier='cold'`, never deleted |
| 2 | **Never forgets during context compaction** | Pre-compaction extraction: before trimming, extract and persist all facts. Double-extract with verification LLM call |
| 3 | **Always retrieves relevant context** | 5-signal retrieval with fallback cascade: hot cache -> warm DB -> cold archive |
| 4 | **Detects contradictions** | New memories checked against existing. Conflicting facts stored with `contradicts[]` links and `status='disputed'` until resolved |
| 5 | **Tracks provenance** | Every memory knows: which conversation, which messages, which LLM extracted it, when, confidence score |
| 6 | **Preserves agent identity** | Identity memories are `tier='hot'`, `is_pinned=TRUE`, NEVER trimmed from prompt. Layer 1 in prompt builder |
| 7 | **Recoverable at any point in time** | `memory_log` allows reconstructing the exact memory state at any historical timestamp |

### Embedding Service (`src/memory/embedding.py`)

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

### 5-Signal Retrieval Pipeline (`src/memory/retrieval.py`) -- CRITICAL PATH

This is the most important component -- called on every user message. Implements the full 7-step pipeline from Section 3B.

```python
class MemoryRetriever:
    """
    5-signal parallel retrieval with tier-aware caching.

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

#### Full 7-Step Pipeline

```
User message arrives
    |
    +-> STEP 1: Generate query embedding
    |
    +-> STEP 2: Check L1 hot cache (Redis)
    |   +-- HIT: Skip to STEP 4 with cached memories
    |   +-- MISS: Continue to STEP 3
    |
    +-> STEP 3: PARALLEL 5-SIGNAL SEARCH (PostgreSQL)
    |   |
    |   +-> Signal A: SEMANTIC SIMILARITY (weight: configurable per agent)
    |   |   Cosine similarity against query embedding
    |   |   Filtered: team_id + agent scope + status='active'
    |   |   LIMIT 50
    |   |
    |   +-> Signal B: RECENCY (weight: configurable)
    |   |   Most recently accessed/created memories
    |   |   Exponential decay: score = exp(-lambda * hours_since_access)
    |   |   lambda = 0.01 -> half-life ~69 hours
    |   |   LIMIT 30
    |   |
    |   +-> Signal C: IMPORTANCE + PINNED (weight: configurable)
    |   |   Pinned memories (always score 1.0)
    |   |   High importance (>=7) memories
    |   |   Identity memories (always included)
    |   |   LIMIT 30
    |   |
    |   +-> Signal D: CONVERSATION CONTINUITY (weight: configurable)
    |   |   Memories from current conversation's source
    |   |   Memories recently created in same session
    |   |   Enables "I just told you about X" to work
    |   |   LIMIT 20
    |   |
    |   +-> Signal E: RELATIONSHIP GRAPH (weight: configurable)
    |       Memories linked via `related_to` to any Signal A hit
    |       One hop: if memory A is relevant AND links to memory B,
    |       memory B gets a relationship bonus
    |       LIMIT 20
    |
    +-> STEP 4: MERGE + DEDUPLICATE + SCORE
    |   |
    |   |  For each unique memory:
    |   |  final_score = (W_sem * semantic_similarity)
    |   |              + (W_rec * recency_score)
    |   |              + (W_imp * normalized_importance)
    |   |              + (W_con * continuity_score)
    |   |              + (W_rel * relationship_bonus)
    |   |
    |   |  Where W_* are from agent.memory.retrieval_weights
    |   |
    |   |  Pinned memories: final_score = max(final_score, 0.95)
    |   |  Identity memories: final_score = 1.0 (always included)
    |   |  Disputed memories: final_score *= 0.5 (deprioritized)
    |   |
    |   +-> Sort by final_score descending
    |
    +-> STEP 5: TOKEN BUDGET ALLOCATION
    |   |
    |   |  Budget = agent.memory.token_budget (default 2000)
    |   |
    |   |  Allocation priority:
    |   |    1. Identity memories      (reserved: 200 tokens, NEVER cut)
    |   |    2. Pinned memories        (reserved: 300 tokens)
    |   |    3. User-profile memories  (reserved: 200 tokens)
    |   |    4. Remaining by score     (fill remaining budget greedily)
    |   |
    |   |  Each memory: estimate tokens = len(content) / 3.5
    |   |  Add memories until budget exhausted
    |   |
    |   +-> If budget too small for all pinned: WARN in logs, include anyway
    |
    +-> STEP 6: FORMAT FOR PROMPT
    |   |
    |   |  Group by type, format with clear delimiters:
    |   |
    |   |  ## Your Identity
    |   |  [IDENTITY]: I am Kyra, a friendly research assistant...
    |   |
    |   |  ## About This User
    |   |  [USER-PROFILE]: Name is Sarah, timezone PST, works at Acme
    |   |  [PREFERENCE]: Prefers detailed explanations with examples
    |   |
    |   |  ## What You Know (Facts)
    |   |  [FACT]: Project deadline is March 15 (importance: 8, confidence: 0.9)
    |   |  [FACT]: Team uses PostgreSQL for all services (importance: 7)
    |   |
    |   |  ## Recent Events
    |   |  [EVENT 2026-02-09]: Decided to use pgvector for memory system
    |   |  [EVENT 2026-02-08]: User was debugging auth module
    |   |
    |   |  ## Learned Patterns
    |   |  [PATTERN]: Weather queries -> load skill -> API call (95% success, 12 uses)
    |   |
    |   |  ## Team Knowledge
    |   |  [TEAM]: Coding standard is PEP 8 with 100 char lines
    |   |
    |   +-> Contradiction markers:
    |       [FACT DISPUTED]: User prefers Python (contradicts: "prefers TypeScript" from Jan 15)
    |
    +-> STEP 7: UPDATE ACCESS METADATA (async, non-blocking)
        SET access_count = access_count + 1
        SET last_accessed_at = NOW()
        Promote frequently-accessed warm memories to hot cache
```

#### Memory Visibility Rules (enforced at query level)

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

### Contradiction Detection (`src/memory/contradiction.py`)

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

    async def check_on_store(
        self, new_memory: MemoryCreate, team_id: UUID, agent_id: UUID
    ) -> ContradictionResult:
        """Check new memory against existing. See Section 3B for full logic."""

    async def check_on_retrieve(
        self, memories: list[ScoredMemory]
    ) -> list[Contradiction]:
        """Flag contradictions within retrieved set for prompt marking."""
```

When a contradiction is detected:

```
New memory: "User prefers JavaScript"
Existing:   "User prefers TypeScript" (from 2 weeks ago)
    |
    +-> If explicit ("I now prefer JS"): SUPERSEDE old memory
    |   old.status = 'superseded'
    |   old.superseded_by = new.id
    |   new.version = old.version + 1
    |
    +-> If ambiguous: DISPUTE both
    |   old.status = 'disputed'
    |   old.contradicts = [new.id]
    |   new.status = 'disputed'
    |   new.contradicts = [old.id]
    |   -> Both appear in prompt with DISPUTED marker
    |   -> Agent can ask user to clarify
    |
    +-> Log in memory_log: action='contradiction_detected'
```

### Context Compaction Shield (`src/memory/compaction_shield.py`)

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

Full compaction flow:

```
BEFORE compaction triggers:
    |
    +-> EXTRACTION PASS 1 (primary LLM)
    |   "Extract ALL facts, decisions, preferences, events from
    |    these messages. Miss NOTHING. Rate importance 1-10."
    |
    +-> EXTRACTION PASS 2 (verification LLM -- different prompt)
    |   "Review these messages AND the Pass 1 extractions.
    |    What did Pass 1 miss? What was extracted incorrectly?"
    |
    +-> MERGE Pass 1 + Pass 2 extractions
    |   Union of both sets (deduplicated by cosine > 0.95)
    |
    +-> PERSIST all extracted memories to PostgreSQL
    |   With provenance: source_message_ids = [exact message UUIDs]
    |
    +-> GENERATE conversation summary (for context continuity)
    |   Stored in working memory (Redis) AND as episodic memory (PG)
    |
    +-> NOW safe to compact
        The compacted messages are also preserved in `message` table
        (raw log, never deleted)
```

**Key insight**: We extract BEFORE compacting, not after. The raw messages are preserved in PostgreSQL forever. The extraction is an enrichment step that creates searchable, scored memories from the raw data.

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

### Importance Scoring

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

### Memory Storage Pipeline (`src/memory/storage.py`)

After a conversation ends (or every N messages per `summarize_interval`):

```
Conversation messages
    |
    +-> PASS 1: Primary extraction (see extraction prompt above)
    |   LLM extracts all 7 memory types with importance + confidence scores
    |   Returns: list[ExtractedMemory]
    |
    +-> PASS 2: Verification extraction (different prompt)
    |   "Review the messages AND Pass 1 results. What was missed?"
    |   Returns: list[ExtractedMemory] (additions only)
    |
    +-> MERGE Pass 1 + Pass 2 (deduplicate by cosine > 0.95)
    |
    +-> For each extracted memory:
    |   +-> Generate embedding
    |   +-> Run ContradictionDetector.check_on_store()
    |   |   +-- Contradiction found -> handle per Section 3B rules
    |   |   +-- No contradiction -> continue
    |   +-> Deduplication check (cosine > 0.95 against existing)
    |   |   +-- Exact duplicate -> SKIP (log in audit)
    |   |   +-- Same subject, different content -> VERSION (increment)
    |   |   +-- New -> INSERT
    |   +-> Log to memory_log (append-only audit trail)
    |
    +-> Batch insert new memories with full provenance:
    |   source_conversation_id, source_message_ids, extraction_model
    |
    +-> Auto-classify tier:
    |   importance >= 9 or is_pinned -> L1 hot (Redis)
    |   importance >= 3 -> L2 warm (default)
    |   importance < 3 -> still L2 (we never start at cold)
    |
    +-> Log stats (created, skipped, versioned, contradictions)
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

### Append-Only Audit Log (`src/memory/memory_log.py`)

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

### Tier Manager (`src/memory/tier_manager.py`)

```
                    +------------+
        +---------->|  L1 HOT    |<-- Auto-promote when access_count > 10
        |           |  (Redis)   |    or importance >= 9 or is_pinned
        |           +------+-----+
        |                  |
        |         Evict when TTL expires
        |         or cache full (LRU)
        |                  |
        |           +------v-----+
  Retrieve -------->|  L2 WARM   |<-- Default tier for new memories
  on demand         |  (PG)      |    Active, searchable, scored
                    +------+-----+
                           |
                  Demote when: superseded
                  OR importance < 3 AND access_count < 2
                  AND age > 90 days AND NOT pinned
                           |
                    +------v-----+
                    |  L3 COLD   |<-- Archived, still searchable
                    |  (PG)      |    Lower priority in retrieval
                    |            |    Never deleted
                    +------------+
```

Promotion triggers:
- `access_count > 10` in past 7 days -> promote warm -> hot
- User pins memory -> immediate promote to hot
- Feedback positive -> boost importance, may promote

Demotion triggers:
- Superseded by newer version -> demote to cold
- `importance < 3 AND access_count < 2 AND age > 90 days` -> demote to cold
- Never: identity, pinned, or importance >= 8 memories

### 7-Layer Prompt Builder (`src/memory/prompt_builder.py`)

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

        Trimming priority (first trimmed -> last):
        L7 -> L6 -> L5 -> L4 -> Layers 1+2+3 NEVER trimmed
        """
```

### Personality Prompt Template (from Section 3A)

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

### Shared vs Private vs Team Memory Model

```
+---------------------------------------------------------------+
|                         TEAM                                    |
|                                                                 |
|  +----------------------------------------------------------+  |
|  |              SHARED MEMORIES                              |  |
|  |  Visible to ALL agents in team                           |  |
|  |  "Team uses PostgreSQL"  "Office hours are 9-5 PST"     |  |
|  |  agent_id = NULL, memory_type = 'shared'                 |  |
|  +----------------------------------------------------------+  |
|                                                                 |
|  +----------------------------------------------------------+  |
|  |              USER PROFILE MEMORIES                        |  |
|  |  Visible to ALL agents, scoped to user                   |  |
|  |  "Sarah's timezone is PST"  "Sarah works at Acme"       |  |
|  |  agent_id = NULL, memory_type = 'user_profile'           |  |
|  +----------------------------------------------------------+  |
|                                                                 |
|  +--------------+  +--------------+  +--------------+          |
|  |    KYRA      |  |    LUKE      |  |    ADA       |          |
|  |              |  |              |  |              |          |
|  | Private:     |  | Private:     |  | Private:     |          |
|  | "Sarah likes |  | "Sarah wants |  | "Sarah       |          |
|  |  examples"   |  |  brief       |  |  prefers     |          |
|  |              |  |  answers"    |  |  charts"     |          |
|  | Identity:    |  | Identity:    |  | Identity:    |          |
|  | "I am Kyra"  |  | "I am Luke"  |  | "I am Ada"   |          |
|  |              |  |              |  |              |          |
|  | Procedural:  |  | Procedural:  |  | Procedural:  |          |
|  | "weather->   |  | "review->    |  | "query->     |          |
|  |  API call"   |  |  checklist"  |  |  visualize"  |          |
|  +--------------+  +--------------+  +--------------+          |
+---------------------------------------------------------------+
```

### Extend Dependencies (Backward Compatible)

Add to `AgentDependencies` in `src/dependencies.py`:

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

### Agent Factory

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

### Files Modified (Existing)

| File | Changes |
|------|---------|
| `src/dependencies.py` | Add Optional AgentDNA, memory services, db_session fields |
| `src/agent.py` | Add `create_skill_agent(agent_dna)` factory |
| `src/prompts.py` | Add 7-layer memory-aware prompt template |
| `src/settings.py` | Add FeatureFlags model |

All changes are ADDITIVE. No existing behavior removed or altered.

## Model Router (MoE Layer 2)

Phase 2 builds the Model Router components from Section 3C. These enable per-query model tier selection based on complexity scoring, reducing costs by 60-80% on simple queries while preserving quality on complex ones.

### New Directories & Files

```
src/moe/
    __init__.py
    complexity_scorer.py   # QueryComplexityScorer - 5-dimension analysis
    model_router.py        # ModelRouter - maps complexity → tier
    model_tier.py          # ModelTier, ComplexityScore models
    cost_guard.py          # CostGuard - budget enforcement
```

### QueryComplexityScorer (5-Dimension Analysis)

```python
class QueryComplexityScorer:
    """Score query complexity to select optimal model tier."""

    CLASSIFIER_MODEL = "anthropic/claude-haiku-4.5"  # Use cheapest model for classification

    async def score(
        self,
        query: str,
        conversation_history: list[Message],
        agent_dna: AgentDNA,
    ) -> ComplexityScore:
        """
        Analyze query on 5 dimensions using a fast classifier.

        Dimensions (0-10 each):
        - reasoning_depth (weight: 0.30): Multi-step logic, debugging, analysis
        - domain_specificity (weight: 0.25): Technical term density, specialized knowledge
        - creativity (weight: 0.20): Ideation, design, novel outputs
        - context_dependency (weight: 0.15): Requires conversation history
        - output_length (weight: 0.10): Expected token count of response

        Results cached in Redis (TTL 5min) keyed by query hash.
        Falls back to heuristic scoring if classifier unavailable.
        """

    def _heuristic_score(self, query: str) -> ComplexityScore:
        """
        Fast fallback when classifier model unavailable.

        Uses simple heuristics:
        - reasoning: presence of "why", "how", "compare", "debug", "analyze"
        - domain: technical term density
        - creativity: "write", "create", "imagine", "design"
        - context: conversation length
        - length: expected output tokens from query structure
        """
```

### ModelRouter (3-Tier Routing)

```python
class ModelRouter:
    """Route queries to optimal model tier based on complexity."""

    DEFAULT_TIERS = [
        ModelTier(name="fast", model_name="anthropic/claude-haiku-4.5",
                  cost_per_1k_input=0.0008, cost_per_1k_output=0.004),
        ModelTier(name="balanced", model_name="anthropic/claude-sonnet-4.5",
                  cost_per_1k_input=0.003, cost_per_1k_output=0.015),
        ModelTier(name="powerful", model_name="anthropic/claude-opus-4",
                  cost_per_1k_input=0.015, cost_per_1k_output=0.075),
    ]

    async def route(
        self, score: ComplexityScore, agent_config: AgentModelConfig,
        budget_remaining: Optional[float] = None,
    ) -> ModelTier:
        """
        Select tier: 0-3 → fast, 3.1-6 → balanced, 6.1-10 → powerful.
        Respects agent_config.force_tier and budget constraints.

        Routing logic:
        1. If agent_config.force_tier set: use that tier (override)
        2. If budget_remaining exhausted: downgrade to cheapest tier
        3. Map complexity score to tier:
           - score 0-3: Tier 1 (fast)
           - score 3.1-6: Tier 2 (balanced)
           - score 6.1-10: Tier 3 (powerful)
        4. If agent_config.max_tier set: cap at that tier
        5. If custom_tiers defined: use those instead of defaults
        """
```

### CostGuard (Budget Enforcement)

```python
class CostGuard:
    """Enforce spending limits per user (daily) and team (monthly)."""

    async def check_budget(
        self, user_id: UUID, team_id: UUID, estimated_cost: float,
    ) -> BudgetCheck:
        """
        Check budget using atomic Redis counters.

        Returns BudgetCheck with:
        - allowed: bool (False if budget exceeded)
        - remaining: float (remaining daily/monthly budget)
        - suggested_tier: Optional[str] (downgrade suggestion if near limit)

        Redis keys:
        - budget:daily:{user_id}:{YYYY-MM-DD} -> atomic counter (TTL 24h)
        - budget:monthly:{team_id}:{YYYY-MM} -> atomic counter (TTL 31 days)
        """
```

### AgentModelConfig Extensions

Reference only (actual model defined in Section 3A, Phase 1):

```python
# Extensions to AgentModelConfig for MoE:
enable_model_routing: bool = True       # Use Model Router (False = single model)
force_tier: Optional[str] = None        # Override: always use this tier
max_tier: Optional[str] = None          # Cap: never exceed this tier
custom_tiers: list[ModelTier] = []      # Agent-specific tiers (empty = defaults)
daily_budget_usd: float = 5.0           # Max daily spend per user
monthly_budget_usd: float = 100.0       # Max monthly spend per team
```

### Integration with AgentDependencies

```python
# Add to AgentDependencies (Phase 2 extensions):
model_router: Optional[ModelRouter] = None
cost_guard: Optional[CostGuard] = None
complexity_scorer: Optional[QueryComplexityScorer] = None
```

**Feature flag**: `enable_model_routing` (default True) — when disabled, falls back to agent's `model_name` from AgentModelConfig.

### Memory API (User-Facing, for future phases)

These Pydantic models are defined in Phase 2 but the API endpoints come in Phase 4:

```python
# POST /v1/memories -- Explicit memory creation
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

## Tests

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
    test_moe/
        conftest.py               # MoE fixtures, mock models, mock budgets
        test_complexity_scorer.py # 5-dimension scoring, heuristic fallback
        test_model_router.py      # Tier selection, overrides, budget caps
        test_cost_guard.py        # Budget enforcement, Redis counters
```

### Key Test Scenarios

- All 7 memory types store and retrieve correctly
- 5-signal retrieval returns semantically relevant memories (mock embeddings)
- Identity memories ALWAYS appear in prompt (never trimmed)
- Pinned memories always appear regardless of recency
- Token budget is respected (never exceeds) with correct priority allocations
- Duplicate memories are detected and merged (cosine > 0.95)
- Contradictions detected: supersede when explicit, dispute when ambiguous
- Compaction shield extracts ALL facts before context trim (double-pass)
- Audit log records every memory lifecycle event (immutable)
- Tier promotion: access_count > 10 -> warm-to-hot
- Tier demotion: superseded memories -> cold (never deleted)
- User "remember X" creates importance=10 pinned memory
- 7-layer prompt layers trim in correct priority order (L7 first, L1-L3 never)
- CLI still works with no DB configured
- AgentDNA personality populates prompt template correctly

## Acceptance Criteria

### Memory System
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

### Model Router (MoE)
- [ ] QueryComplexityScorer produces 5-dimension scores (0-10 each)
- [ ] ModelRouter routes simple queries (score < 3) to Tier 1 (fast)
- [ ] ModelRouter routes complex queries (score > 6) to Tier 3 (powerful)
- [ ] CostGuard blocks requests when budget exhausted, suggests cheaper tier
- [ ] Model routing disabled gracefully when feature flag off (uses single model)
- [ ] Heuristic fallback works when classifier model unavailable

## Rollback Strategy

- Delete `src/memory/` module entirely
- Revert `src/dependencies.py` changes (remove Optional memory service fields)
- Revert `src/agent.py` changes (remove `create_skill_agent` factory)
- Revert `src/prompts.py` changes (remove 7-layer template)
- Revert `src/settings.py` changes (remove FeatureFlags)
- No database rollback needed (Phase 2 introduces no new tables)

## Links to Main Plan

- Architecture: `plan/multi-agent-platform.md` Section 2
- ADRs:
  - ADR-5: Custom memory over Mem0/Zep/Letta (Section 3, why we build our own)
  - ADR-6: Single memory table with type discriminator (Section 3)
  - ADR-7: All memory types from day 1 (Section 3)
  - ADR-8: Append-only memory (Section 3)
- Agent Identity System: Section 3A (AgentDNA, personality template, shared vs custom skills, agent registry)
- Bulletproof Memory Architecture: Section 3B (the complete specification for this phase)
  - Memory hierarchy (L1/L2/L3)
  - Seven guarantees
  - 5-signal retrieval pipeline (7 steps)
  - Context compaction shield
  - Contradiction detection
  - Extraction prompt
  - Shared vs private vs team memory model
  - Tier management (promotion/demotion)
  - Memory API
- Phase 2 implementation details: Section 4, "Phase 2: Bulletproof Memory System"
- Files modified: Section 5 (dependencies.py, agent.py, prompts.py, settings.py)
- Feature flags: Section 23 (FeatureFlags model)
- Rollback: Section 23
- Phase dependency graph: Section 21 (Phase 2 depends on Phase 1, required by Phases 3-9)
- Performance targets: Section 10 (memory retrieval < 200ms, embedding < 500ms)
- Definition of Done: Section 14 (Bulletproof Memory -- The Seven Guarantees)
