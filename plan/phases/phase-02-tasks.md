# Phase 2: Bulletproof Memory System -- Task Decomposition

> **Generated**: 2026-02-09 | **Complexity Score**: 7 (A:1, I:2, N:1, R:1, S:2)
> **Total Tasks**: 24 atomic tasks across 8 tracks
> **Estimated Waves**: 7 (with maximum parallelism)
> **Critical Path**: T1.1 -> T2.1 -> T3.1 -> T3.3 -> T3.5 -> T4.1 -> T6.1 -> T7.1 (8 deep)

## Codebase Context (Phase 1 Complete)

### Existing Assets (DO NOT recreate)
- `src/db/models/memory.py` -- MemoryORM, MemoryLogORM, MemoryTagORM (with enums)
- `src/db/models/agent.py` -- AgentORM with personality JSONB
- `src/db/models/conversation.py` -- ConversationORM, MessageORM
- `src/db/repositories/memory_repo.py` -- MemoryRepository (search_by_embedding, find_similar, get_by_team)
- `src/db/repositories/base.py` -- BaseRepository[T] generic CRUD
- `src/db/engine.py` -- get_engine(), get_session() async generator
- `src/models/memory_models.py` -- MemoryType, MemoryStatus, MemoryTier, MemorySource enums + MemoryCreate, MemoryRecord, MemorySearchRequest, MemorySearchResult
- `src/models/agent_models.py` -- AgentDNA, AgentPersonality, AgentModelConfig, AgentMemoryConfig (with RetrievalWeights), AgentBoundaries, VoiceExample
- `src/models/conversation_models.py` -- MessageRecord, ConversationRecord
- `src/settings.py` -- Settings with database_url, embedding_model, embedding_api_key, embedding_dimensions
- `src/dependencies.py` -- AgentDependencies @dataclass with skill_loader, session_id, settings
- `src/agent.py` -- skill_agent singleton with system_prompt decorator
- `src/prompts.py` -- MAIN_SYSTEM_PROMPT with {skill_metadata}

### Key Patterns
- Absolute imports: `from src.module import Class`
- Error returns from tools: `return f"Error: ..."`
- Structured logging: `f"action_name: key={value}"`
- DI: `@dataclass AgentDependencies` with `async initialize()`
- ORM suffix: `MemoryORM` (avoids Pydantic collision)
- SA metadata: mapped as `metadata_json` in Python
- Repository pattern: `BaseRepository[T]` with flush+refresh
- Session: `async_sessionmaker(engine, expire_on_commit=False)`

---

## Track 1: Foundation Types & Models

### T1.1 -- Create src/memory/ package with types module
**Description**: Create `src/memory/__init__.py` and `src/memory/types.py`. The types module re-exports the existing enums from `src/models/memory_models.py` and defines additional Phase 2 data models needed by the memory pipeline: `ScoredMemory`, `RetrievalResult`, `RetrievalStats`, `Contradiction`, `ContradictionResult`, `CompactionResult`, `ExtractionResult`, `ExtractedMemory`, `MemorySnapshot`, `BudgetAllocation`.

**Files to create**:
- `src/memory/__init__.py`
- `src/memory/types.py`

**Dependencies**: None (leaf node)

**Acceptance criteria**:
- `from src.memory.types import ScoredMemory, RetrievalResult` works
- All Pydantic models have type annotations and docstrings
- `ScoredMemory` wraps MemoryRecord + final_score float + signal_scores dict
- `RetrievalResult` has memories list, formatted_prompt str, stats, contradictions
- `RetrievalStats` has signals_hit int, cache_hit bool, total_ms float, query_tokens int
- `Contradiction` has memory_a UUID, memory_b UUID, reason str
- `ContradictionResult` has contradicts list[UUID], action Literal['supersede','dispute','coexist'], reason str
- `CompactionResult` has memories_extracted int, summary str, pass1_count int, pass2_additions int
- `ExtractionResult` has memories_created, memories_versioned, duplicates_skipped, contradictions_found, pass1_count, pass2_additions ints
- `ExtractedMemory` has type MemoryType, content str, subject Optional[str], importance int, confidence float
- `MemorySnapshot` has memory_id UUID, content str, status str, tier str, timestamp datetime
- `BudgetAllocation` has identity_tokens, pinned_tokens, profile_tokens, remaining_tokens ints
- ruff check passes, mypy passes

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 1

---

### T1.2 -- Create src/moe/ package with model_tier module
**Description**: Create `src/moe/__init__.py` and `src/moe/model_tier.py`. Defines `ModelTier` (name, model_name, cost_per_1k_input, cost_per_1k_output), `ComplexityScore` (5 dimensions + weighted_total computed_field), and `BudgetCheck` (allowed bool, remaining float, suggested_tier Optional[str]).

**Files to create**:
- `src/moe/__init__.py`
- `src/moe/model_tier.py`

**Dependencies**: None (leaf node)

**Acceptance criteria**:
- `from src.moe.model_tier import ModelTier, ComplexityScore, BudgetCheck` works
- `ComplexityScore` has reasoning_depth, domain_specificity, creativity, context_dependency, output_length (all float 0-10) with weights and a computed `weighted_total`
- `ModelTier` has name str, model_name str, cost_per_1k_input float, cost_per_1k_output float
- `BudgetCheck` has allowed bool, remaining float, suggested_tier Optional[str]
- All models have Google docstrings
- ruff check passes, mypy passes

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 1

---

### T1.3 -- Add FeatureFlags to src/settings.py
**Description**: Add `FeatureFlags` BaseModel to `src/settings.py` with boolean flags: `enable_memory` (True), `enable_compaction_shield` (True), `enable_contradiction_detection` (True), `enable_agent_collaboration` (False), `enable_webhooks` (False), `enable_integrations` (False). Add `feature_flags: FeatureFlags` field to `Settings` class with `Field(default_factory=FeatureFlags)`.

**Files to modify**:
- `src/settings.py`

**Dependencies**: None (leaf node)

**Acceptance criteria**:
- `settings.feature_flags.enable_memory` returns True by default
- All 6 flags accessible
- `FEATURE_FLAGS__ENABLE_MEMORY=false` env var disables memory
- Existing Settings behavior unchanged (backward compatible)
- Existing tests still pass
- ruff check passes

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 1

---

### T1.4 -- Create tests/test_memory/ conftest and type tests
**Description**: Create `tests/test_memory/__init__.py`, `tests/test_memory/conftest.py` with shared fixtures (mock embeddings, sample MemoryRecord factory, sample AgentDNA factory, mock AsyncSession), and `tests/test_memory/test_memory_types.py` testing all Phase 2 Pydantic models from T1.1.

**Files to create**:
- `tests/test_memory/__init__.py`
- `tests/test_memory/conftest.py`
- `tests/test_memory/test_memory_types.py`

**Dependencies**: T1.1

**Acceptance criteria**:
- `conftest.py` provides: `sample_memory_record()` factory, `sample_agent_dna()` factory, `mock_embedding()` fixture (returns 1536-dim list[float]), `mock_session()` fixture
- Tests validate all Pydantic model fields, defaults, and validation errors
- Tests verify ScoredMemory, RetrievalResult, ComplexityScore computed fields
- All tests pass with `.venv/bin/python -m pytest tests/test_memory/ -v`

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 2

---

### T1.5 -- Create tests/test_moe/ conftest and model_tier tests
**Description**: Create `tests/test_moe/__init__.py`, `tests/test_moe/conftest.py` with MoE fixtures, and `tests/test_moe/test_model_tier.py` testing ModelTier, ComplexityScore, BudgetCheck from T1.2.

**Files to create**:
- `tests/test_moe/__init__.py`
- `tests/test_moe/conftest.py`
- `tests/test_moe/test_model_tier.py`

**Dependencies**: T1.2

**Acceptance criteria**:
- ComplexityScore weighted_total computed correctly for known inputs
- ModelTier validation works (positive costs)
- BudgetCheck defaults correct
- All tests pass

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 2

---

## Track 2: Embedding Service

### T2.1 -- Implement EmbeddingService
**Description**: Create `src/memory/embedding.py` with `EmbeddingService` class. Uses httpx to call OpenAI embeddings API. Features: LRU cache (1000 entries, keyed by SHA-256 of normalized text), batch embedding with configurable batch_size (default 100), exponential backoff on 429 errors (max 3 retries), cost tracking via structured logging. Constructor takes api_key, model, dimensions. Uses `src/settings.py` values.

**Files to create**:
- `src/memory/embedding.py`

**Dependencies**: T1.1 (needs types module for imports)

**Acceptance criteria**:
- `embed_text(text)` returns list[float] of correct dimension
- `embed_batch(texts)` processes in configurable batch sizes
- LRU cache prevents duplicate API calls (same text -> cache hit)
- `_cache_key(text)` uses SHA-256 of lowercased stripped text
- Exponential backoff on HTTP 429 (3 retries, base 1s)
- Logs: `embedding_generated: text_length={n}, cached={bool}, tokens_used={n}`
- Uses httpx.AsyncClient with 30s timeout
- Never logs the API key
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T2.2 -- Test EmbeddingService
**Description**: Create `tests/test_memory/test_embedding.py` with unit tests for EmbeddingService. Mock httpx responses. Test: single embed, batch embed, cache hit/miss, retry on 429, error on 500, correct dimensions, SHA-256 cache key.

**Files to create**:
- `tests/test_memory/test_embedding.py`

**Dependencies**: T2.1, T1.4

**Acceptance criteria**:
- Test single text embedding returns correct dimensions
- Test batch embedding splits into correct number of API calls
- Test cache hit (same text twice -> 1 API call)
- Test 429 retry (mock 429 then 200 -> succeeds)
- Test 500 error returns error string (doesn't raise)
- Test cache key is SHA-256 of normalized text
- All tests pass

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 3

---

## Track 3: Core Memory Pipeline

### T3.1 -- Implement MemoryAuditLog
**Description**: Create `src/memory/memory_log.py` with `MemoryAuditLog` class. Wraps MemoryLogORM writes. Methods: `log_created()`, `log_updated()`, `log_superseded()`, `log_promoted()`, `log_contradiction()`, `reconstruct_at()`. All writes use the existing MemoryLogORM from `src/db/models/memory.py`. Session passed via constructor. All log methods are async, append-only (never update/delete).

**Files to create**:
- `src/memory/memory_log.py`

**Dependencies**: T1.1 (types), existing MemoryLogORM

**Acceptance criteria**:
- Constructor takes AsyncSession
- `log_created(memory_id, content, source)` inserts MemoryLogORM with action='created'
- `log_updated(memory_id, old, new, reason)` inserts with action='updated', old_content, new_content
- `log_superseded(old_id, new_id, reason)` inserts with action='superseded', related_memory_ids
- `log_promoted(memory_id, old_tier, new_tier)` inserts with action='promoted', old_tier, new_tier
- `log_contradiction(memory_a, memory_b, resolution)` inserts with action='contradiction_detected'
- `reconstruct_at(timestamp, team_id)` queries logs up to timestamp, returns list[MemorySnapshot]
- No UPDATE or DELETE operations anywhere in this class
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T3.2 -- Implement TokenBudgetManager
**Description**: Create `src/memory/token_budget.py` with `TokenBudgetManager` class. Manages token allocation for memory prompt building. Methods: `estimate_tokens(text)` (len/3.5 heuristic), `allocate(memories, budget)` returns `BudgetAllocation` with reserved slots (identity: 200, pinned: 300, profile: 200, remaining: fill greedily by score). Identity memories NEVER trimmed. Warns in logs if budget too small for all pinned.

**Files to create**:
- `src/memory/token_budget.py`

**Dependencies**: T1.1 (needs ScoredMemory, BudgetAllocation types)

**Acceptance criteria**:
- `estimate_tokens("hello world")` returns int (len("hello world") / 3.5 rounded)
- `allocate()` respects priority: identity first, then pinned, then profile, then by score
- Identity memories always included even if budget is tiny (with WARNING log)
- Returns BudgetAllocation with accurate token counts per category
- Memories within budget are returned; over-budget trimmed by lowest score first
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T3.3 -- Implement ContradictionDetector
**Description**: Create `src/memory/contradiction.py` with `ContradictionDetector` class. Constructor takes AsyncSession + EmbeddingService. Methods: `check_on_store(new_memory, team_id, agent_id)` checks new memory against existing (same subject -> content differs = contradiction), `check_on_retrieve(memories)` flags contradictions within a retrieved set. Detection: same-subject check (subject field match), semantic opposition (cosine > 0.7 but content conflicts). Returns ContradictionResult with action: 'supersede' (explicit override), 'dispute' (ambiguous), 'coexist' (compatible).

**Files to create**:
- `src/memory/contradiction.py`

**Dependencies**: T1.1 (types), T2.1 (EmbeddingService), existing MemoryRepository

**Acceptance criteria**:
- `check_on_store()` finds existing memories with same subject, returns ContradictionResult
- If new memory is more recent and explicitly contradicts: action='supersede'
- If ambiguous contradiction: action='dispute', both memories flagged
- If same subject but compatible content: action='coexist'
- `check_on_retrieve()` returns list[Contradiction] for disputed pairs in retrieved set
- Uses MemoryRepository.find_similar() for semantic check
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 3

---

### T3.4 -- Implement TierManager
**Description**: Create `src/memory/tier_manager.py` with `TierManager` class. Constructor takes AsyncSession + MemoryAuditLog. Methods: `evaluate_promotion(memory)` (access_count > 10 in 7d -> hot; pinned -> hot; feedback positive -> boost importance), `evaluate_demotion(memory)` (superseded -> cold; importance<3 AND access<2 AND age>90d AND NOT pinned -> cold), `promote(memory_id, new_tier)`, `demote(memory_id, new_tier)`. Never demotes: identity, pinned, importance>=8.

**Files to create**:
- `src/memory/tier_manager.py`

**Dependencies**: T1.1, T3.1 (MemoryAuditLog)

**Acceptance criteria**:
- `evaluate_promotion()` returns Optional tier if promotion warranted, None otherwise
- `evaluate_demotion()` returns Optional tier if demotion warranted, None otherwise
- `promote()` updates memory tier in DB + logs via MemoryAuditLog
- `demote()` updates memory tier in DB + logs via MemoryAuditLog
- Identity memories NEVER demoted (returns None always)
- Pinned memories NEVER demoted
- importance >= 8 memories NEVER demoted
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 3

---

### T3.5 -- Implement MemoryRetriever (5-signal pipeline)
**Description**: Create `src/memory/retrieval.py` with `MemoryRetriever` class. This is the CRITICAL PATH component. Constructor takes AsyncSession, EmbeddingService, RetrievalWeights. Implements the full 7-step pipeline:
1. Generate query embedding
2. Check L1 hot cache (in-memory dict for Phase 2, Redis in Phase 3)
3. Parallel 5-signal search (semantic similarity, recency, importance/pinned, conversation continuity, relationship graph)
4. Merge + deduplicate + score (weighted sum per RetrievalWeights)
5. Token budget allocation via TokenBudgetManager
6. Format for prompt (grouped by type with delimiters)
7. Update access metadata (async, non-blocking)

Uses memory visibility rules: team-scoped, agent-scoped, status in (active, disputed).

**Files to create**:
- `src/memory/retrieval.py`

**Dependencies**: T1.1 (types), T2.1 (EmbeddingService), T3.2 (TokenBudgetManager), existing MemoryRepository

**Acceptance criteria**:
- `retrieve(query, team_id, agent_id, ...)` returns RetrievalResult
- Semantic signal: uses EmbeddingService + MemoryRepository.search_by_embedding()
- Recency signal: exponential decay score = exp(-0.01 * hours_since_access)
- Importance signal: pinned=1.0, identity=1.0, disputed *= 0.5, else normalized importance/10
- Continuity signal: memories from same conversation_id scored higher
- Relationship signal: memories linked via related_to get bonus
- Final score = weighted sum using RetrievalWeights
- Identity memories always score 1.0, pinned min 0.95
- Deduplication by memory ID (take highest score)
- Token budget respected via TokenBudgetManager.allocate()
- formatted_prompt groups memories by type with section headers
- Access metadata updated asynchronously (access_count++, last_accessed_at=now)
- Memory visibility rules enforced in query filters
- ruff check passes, mypy passes

**Complexity**: L
**Agent**: builder
**Parallel group**: Wave 4

---

### T3.6 -- Implement MemoryExtractor (double-pass storage)
**Description**: Create `src/memory/storage.py` with `MemoryExtractor` class. Constructor takes AsyncSession, EmbeddingService, ContradictionDetector, MemoryAuditLog. Implements double-pass extraction:
- Pass 1: LLM extracts facts/events/preferences using EXTRACTION_PROMPT
- Pass 2: Verification LLM reviews Pass 1 for missed items
- Merge: Union of both passes (deduplicated by cosine > 0.95)
- For each: generate embedding, check contradictions, check duplicates, persist
- Returns ExtractionResult with counts

Includes the EXTRACTION_PROMPT constant as specified in Phase 2 PRD.

**Files to create**:
- `src/memory/storage.py`

**Dependencies**: T1.1, T2.1, T3.1 (audit log), T3.3 (contradiction detector)

**Acceptance criteria**:
- `extract_from_conversation(messages, team_id, agent_id, user_id, conversation_id)` returns ExtractionResult
- Pass 1 uses EXTRACTION_PROMPT with importance scale
- Pass 2 uses verification prompt reviewing Pass 1 results
- Merge deduplicates by cosine > 0.95
- Each memory: embedding generated, contradiction checked, duplicate checked
- Duplicates (cosine > 0.95 vs existing) skipped with audit log entry
- Same subject different content -> version increment
- New memories inserted with full provenance (source_conversation_id, source_message_ids, extraction_model)
- Auto-classify tier: importance >= 9 or pinned -> hot, else warm
- Returns accurate ExtractionResult counts
- EXTRACTION_PROMPT constant matches Phase 2 spec (importance scale 1-10, rules, JSON output)
- ruff check passes, mypy passes

**Complexity**: L
**Agent**: builder
**Parallel group**: Wave 4

---

### T3.7 -- Implement CompactionShield
**Description**: Create `src/memory/compaction_shield.py` with `CompactionShield` class. Constructor takes MemoryExtractor. Implements `extract_before_compaction(messages_to_compact, team_id, agent_id, user_id, conversation_id)` which calls MemoryExtractor's double-pass then generates a conversation summary (stored as episodic memory). Returns CompactionResult. This MUST be called BEFORE any context trimming.

**Files to create**:
- `src/memory/compaction_shield.py`

**Dependencies**: T1.1, T3.6 (MemoryExtractor)

**Acceptance criteria**:
- `extract_before_compaction()` calls MemoryExtractor.extract_from_conversation()
- Generates conversation summary as additional episodic memory
- Returns CompactionResult with memories_extracted, summary, pass counts
- Feature flag: checks `settings.feature_flags.enable_compaction_shield`
- When disabled: returns empty CompactionResult (no extraction, no error)
- ruff check passes, mypy passes

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 5

---

## Track 4: Prompt Builder

### T4.1 -- Implement MemoryPromptBuilder (7-layer)
**Description**: Create `src/memory/prompt_builder.py` with `MemoryPromptBuilder` class and the personality prompt template constant. `build(agent_dna, skill_metadata, retrieval_result, conversation_summary)` constructs the 7-layer prompt:
1. Agent Identity + Personality (NEVER trimmed)
2. Identity Memories (NEVER trimmed)
3. Skill Metadata Level 1 (NEVER trimmed)
4. User Profile (trim reluctantly)
5. Retrieved Memories (trimmed by score)
6. Team Knowledge (trim before L5)
7. Conversation Summary (trimmed FIRST)

Trimming priority: L7 -> L6 -> L5 -> L4 -> L1+L2+L3 NEVER trimmed.

**Files to create**:
- `src/memory/prompt_builder.py`

**Dependencies**: T1.1 (types), T3.5 (RetrievalResult from retriever)

**Acceptance criteria**:
- `build()` returns complete prompt string
- Layer 1 populated from AgentDNA personality fields
- Layer 2 populated from identity memories in RetrievalResult
- Layer 3 populated from skill_metadata string
- Layer 4 populated from user_profile memories
- Layer 5 populated from remaining memories grouped by type
- Layer 6 populated from shared/team memories
- Layer 7 populated from conversation_summary
- Trimming: when total exceeds budget, L7 removed first, then L6, then L5, then L4
- Layers 1+2+3 NEVER trimmed under any budget
- Contradiction markers included: `[FACT DISPUTED]: ...`
- PERSONALITY_TEMPLATE constant matches Phase 2 spec
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 5

---

## Track 5: MoE (Model Router)

### T5.1 -- Implement QueryComplexityScorer
**Description**: Create `src/moe/complexity_scorer.py` with `QueryComplexityScorer` class. Uses a cheap classifier model (haiku) to score query complexity on 5 dimensions (0-10 each): reasoning_depth (0.30), domain_specificity (0.25), creativity (0.20), context_dependency (0.15), output_length (0.10). Includes `_heuristic_score()` fallback using keyword detection. Constructor takes httpx client + API config.

**Files to create**:
- `src/moe/complexity_scorer.py`

**Dependencies**: T1.2 (ComplexityScore model)

**Acceptance criteria**:
- `score(query, conversation_history, agent_dna)` returns ComplexityScore
- Uses classifier LLM call with structured output for 5 dimensions
- `_heuristic_score()` fallback works without any LLM call
- Heuristic detects: reasoning keywords ("why","how","compare","debug"), domain terms, creativity keywords ("write","create","design"), conversation length, expected output size
- Weights applied correctly in ComplexityScore.weighted_total
- On classifier error: falls back to heuristic with WARNING log
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T5.2 -- Implement ModelRouter
**Description**: Create `src/moe/model_router.py` with `ModelRouter` class. Constructor takes default ModelTier list. `route(score, agent_config, budget_remaining)` maps complexity score to tier: 0-3 -> fast (haiku), 3.1-6 -> balanced (sonnet), 6.1-10 -> powerful (opus). Respects: force_tier override, max_tier cap, budget constraints (downgrade when budget low), custom_tiers from AgentModelConfig.

**Files to create**:
- `src/moe/model_router.py`

**Dependencies**: T1.2 (ModelTier, ComplexityScore, BudgetCheck)

**Acceptance criteria**:
- DEFAULT_TIERS has 3 entries: fast (haiku), balanced (sonnet), powerful (opus)
- `route()` returns correct tier for score ranges (0-3, 3.1-6, 6.1-10)
- force_tier overrides all logic
- max_tier caps at specified tier
- When budget_remaining is low: downgrades to cheapest tier
- When budget_remaining is None: no budget constraint
- Custom tiers from agent_config used when provided
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T5.3 -- Implement CostGuard
**Description**: Create `src/moe/cost_guard.py` with `CostGuard` class. For Phase 2, uses in-memory counters (dict) instead of Redis. `check_budget(user_id, team_id, estimated_cost)` returns BudgetCheck. Tracks daily per-user and monthly per-team spending. Default limits from AgentModelConfig: daily_budget_usd=5.0, monthly_budget_usd=100.0.

**Files to create**:
- `src/moe/cost_guard.py`

**Dependencies**: T1.2 (BudgetCheck model)

**Acceptance criteria**:
- `check_budget()` returns BudgetCheck with allowed=True when within budget
- Daily counter resets at midnight UTC
- Monthly counter resets at month boundary
- When daily budget exceeded: allowed=False, suggested_tier='fast'
- When monthly budget exceeded: allowed=False
- Thread-safe counter updates (asyncio.Lock)
- In-memory dict for Phase 2 (no Redis dependency)
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 2

---

### T5.4 -- Test MoE components
**Description**: Create `tests/test_moe/test_complexity_scorer.py`, `tests/test_moe/test_model_router.py`, `tests/test_moe/test_cost_guard.py`. Test scoring, routing, and budget enforcement.

**Files to create**:
- `tests/test_moe/test_complexity_scorer.py`
- `tests/test_moe/test_model_router.py`
- `tests/test_moe/test_cost_guard.py`

**Dependencies**: T5.1, T5.2, T5.3, T1.5

**Acceptance criteria**:
- Complexity scorer: heuristic fallback correctly scores "why is the sky blue" (high reasoning), "hello" (low all), "write a poem about AI" (high creativity)
- Model router: score 2.0 -> fast, score 5.0 -> balanced, score 8.0 -> powerful
- Model router: force_tier='fast' overrides score 9.0
- Model router: max_tier='balanced' caps score 9.0
- Cost guard: budget exceeded -> allowed=False
- Cost guard: within budget -> allowed=True with correct remaining
- All tests pass

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 3

---

## Track 6: Integration (Existing File Modifications)

### T6.1 -- Update src/dependencies.py with memory and MoE services
**Description**: Add Optional fields to AgentDependencies for all Phase 2 services. Update `initialize()` to create memory services when `database_url` is set and `feature_flags.enable_memory` is True. All new fields are Optional with default None to preserve backward compatibility (CLI works without DB).

**Files to modify**:
- `src/dependencies.py`

**New fields**:
```python
# Memory services
agent_dna: Optional[AgentDNA] = None
memory_retriever: Optional[MemoryRetriever] = None
embedding_service: Optional[EmbeddingService] = None
contradiction_detector: Optional[ContradictionDetector] = None
compaction_shield: Optional[CompactionShield] = None
memory_audit_log: Optional[MemoryAuditLog] = None
tier_manager: Optional[TierManager] = None
db_session: Optional[AsyncSession] = None
user_id: Optional[UUID] = None
conversation_id: Optional[UUID] = None

# MoE services
model_router: Optional[ModelRouter] = None
cost_guard: Optional[CostGuard] = None
complexity_scorer: Optional[QueryComplexityScorer] = None
```

**Dependencies**: T2.1, T3.1, T3.3, T3.4, T3.5, T3.7, T4.1, T5.1, T5.2, T5.3, T1.3

**Acceptance criteria**:
- All new fields are Optional with default None
- `initialize()` creates memory services when database_url is set AND enable_memory flag is True
- `initialize()` creates MoE services when enable_model_routing flag is True (checked via agent config)
- Existing CLI behavior unchanged (no DB -> no memory services, no errors)
- `from src.dependencies import AgentDependencies` still works
- Existing tests still pass
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 6

---

### T6.2 -- Update src/prompts.py with 7-layer template
**Description**: Add `MEMORY_SYSTEM_PROMPT` template string to `src/prompts.py`. This is the template used by MemoryPromptBuilder. Keep existing `MAIN_SYSTEM_PROMPT` unchanged. Add the personality template (`PERSONALITY_TEMPLATE`) from the Phase 2 spec.

**Files to modify**:
- `src/prompts.py`

**Dependencies**: None (just string constants)

**Acceptance criteria**:
- `MAIN_SYSTEM_PROMPT` completely unchanged
- `MEMORY_SYSTEM_PROMPT` added with 7 placeholder sections
- `PERSONALITY_TEMPLATE` added matching Phase 2 spec
- `from src.prompts import MEMORY_SYSTEM_PROMPT, PERSONALITY_TEMPLATE` works
- No new imports needed (pure string constants)
- ruff check passes

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 1

---

### T6.3 -- Update src/agent.py with create_skill_agent factory
**Description**: Add `create_skill_agent(model_name, agent_dna)` factory function to `src/agent.py`. When called without args: returns existing singleton. When called with AgentDNA: creates new Agent instance with memory-aware system prompt (uses MemoryPromptBuilder), effective skills from DNA, model from DNA. Existing `skill_agent` singleton preserved. System prompt decorator branched: if agent_dna + memory_retriever exists -> use MemoryPromptBuilder, else -> existing behavior.

**Files to modify**:
- `src/agent.py`

**Dependencies**: T4.1 (MemoryPromptBuilder), T6.1 (updated dependencies), T6.2 (prompt templates)

**Acceptance criteria**:
- `create_skill_agent()` with no args returns existing singleton-style agent
- `create_skill_agent(agent_dna=dna)` creates new Agent with DNA-based config
- System prompt uses MemoryPromptBuilder when memory services available
- System prompt falls back to MAIN_SYSTEM_PROMPT when no memory
- Effective skills computed from DNA (shared + custom - disabled)
- Model selected from AgentDNA.model.model_name
- Existing `skill_agent` singleton still works exactly as before
- ruff check passes, mypy passes

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 7

---

## Track 7: Memory System Tests

### T7.1 -- Test MemoryAuditLog
**Description**: Create `tests/test_memory/test_audit_log.py`. Test all log methods and reconstruct_at.

**Files to create**:
- `tests/test_memory/test_audit_log.py`

**Dependencies**: T3.1, T1.4

**Acceptance criteria**:
- Test log_created inserts row with action='created'
- Test log_updated stores old and new content
- Test log_superseded links old and new memory IDs
- Test log_promoted records tier change
- Test log_contradiction records both memory IDs
- Test reconstruct_at returns correct state at given timestamp
- All tests use mock AsyncSession
- All tests pass

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 3

---

### T7.2 -- Test TokenBudgetManager
**Description**: Create `tests/test_memory/test_token_budget.py`. Test token estimation, allocation priority, budget limits, identity never trimmed.

**Files to create**:
- `tests/test_memory/test_token_budget.py`

**Dependencies**: T3.2, T1.4

**Acceptance criteria**:
- Test estimate_tokens accuracy (within 10% of len/3.5)
- Test identity memories always included even with tiny budget
- Test allocation priority: identity -> pinned -> profile -> score
- Test over-budget: lowest-score memories trimmed first
- Test warning log when budget too small for pinned
- All tests pass

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 3

---

### T7.3 -- Test ContradictionDetector
**Description**: Create `tests/test_memory/test_contradiction.py`. Test same-subject detection, supersede vs dispute logic, check_on_retrieve.

**Files to create**:
- `tests/test_memory/test_contradiction.py`

**Dependencies**: T3.3, T1.4

**Acceptance criteria**:
- Test same subject, different content -> contradiction detected
- Test explicit override (more recent) -> action='supersede'
- Test ambiguous contradiction -> action='dispute'
- Test compatible content -> action='coexist'
- Test check_on_retrieve flags disputed pairs
- Mock EmbeddingService and MemoryRepository
- All tests pass

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 4

---

### T7.4 -- Test MemoryRetriever (5-signal pipeline)
**Description**: Create `tests/test_memory/test_retrieval.py`. Test full retrieval pipeline with mocked DB and embeddings.

**Files to create**:
- `tests/test_memory/test_retrieval.py`

**Dependencies**: T3.5, T1.4

**Acceptance criteria**:
- Test semantic signal returns memories by embedding similarity
- Test recency signal decays correctly (recent > old)
- Test importance signal: pinned=1.0, identity=1.0, disputed*=0.5
- Test continuity signal boosts same-conversation memories
- Test relationship signal gives bonus to related memories
- Test final score is weighted sum
- Test deduplication (same memory from multiple signals)
- Test token budget respected
- Test formatted_prompt has correct section headers
- Test identity memories ALWAYS in result regardless of score
- Mock EmbeddingService, AsyncSession
- All tests pass

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 5

---

### T7.5 -- Test MemoryExtractor and CompactionShield
**Description**: Create `tests/test_memory/test_storage.py` and `tests/test_memory/test_compaction_shield.py`. Test double-pass extraction, dedup, versioning, and compaction shield.

**Files to create**:
- `tests/test_memory/test_storage.py`
- `tests/test_memory/test_compaction_shield.py`

**Dependencies**: T3.6, T3.7, T1.4

**Acceptance criteria**:
- test_storage: double-pass extraction produces merged results
- test_storage: duplicates (cosine > 0.95) skipped
- test_storage: same subject different content -> version increment
- test_storage: full provenance set on created memories
- test_storage: ExtractionResult counts are accurate
- test_compaction: calls MemoryExtractor + generates summary
- test_compaction: respects feature flag (disabled -> no extraction)
- test_compaction: CompactionResult has correct counts
- Mock LLM calls, EmbeddingService, AsyncSession
- All tests pass

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 6

---

### T7.6 -- Test MemoryPromptBuilder
**Description**: Create `tests/test_memory/test_prompt_builder.py`. Test 7-layer construction, trimming priority, identity preservation, contradiction markers.

**Files to create**:
- `tests/test_memory/test_prompt_builder.py`

**Dependencies**: T4.1, T1.4

**Acceptance criteria**:
- Test all 7 layers present in output
- Test Layer 1 (identity + personality) populated from AgentDNA
- Test Layer 2 (identity memories) always present
- Test Layer 3 (skill metadata) always present
- Test trimming order: L7 first, then L6, then L5, then L4
- Test Layers 1+2+3 NEVER trimmed even with tiny budget
- Test contradiction markers: `[FACT DISPUTED]: ...`
- Test memories grouped by type with correct headers
- All tests pass

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 6

---

## Track 8: Integration Testing & Verification

### T8.1 -- Integration test: end-to-end memory flow
**Description**: Create `tests/test_memory/test_integration.py`. Tests the full pipeline: embed -> store -> retrieve -> build prompt. Uses mock DB session and mock LLM calls. Verifies that a memory created via extraction appears in retrieval results and is correctly formatted in the prompt.

**Files to create**:
- `tests/test_memory/test_integration.py`

**Dependencies**: T6.1, T6.3, T7.4, T7.5, T7.6

**Acceptance criteria**:
- Test: create AgentDependencies with mock DB -> initialize() sets up all memory services
- Test: extract memories from mock conversation -> retrieve -> memories appear in prompt
- Test: identity memory always in prompt
- Test: CLI mode (no DB) -> initialize() works with no memory services
- Test: feature flag disable_memory -> no memory services created
- All tests pass with `.venv/bin/python -m pytest tests/test_memory/test_integration.py -v`

**Complexity**: M
**Agent**: builder
**Parallel group**: Wave 7

---

### T8.2 -- Full test suite verification and lint
**Description**: Run full test suite, ruff check, ruff format, mypy across entire codebase. Fix any issues. Verify ALL existing tests still pass (backward compatibility). Verify all new tests pass.

**Files to verify**:
- All files in `src/memory/`, `src/moe/`, `tests/test_memory/`, `tests/test_moe/`
- All modified files: `src/settings.py`, `src/dependencies.py`, `src/agent.py`, `src/prompts.py`

**Dependencies**: T8.1, T5.4 (all tests done)

**Acceptance criteria**:
- `.venv/bin/python -m pytest tests/ -v` -- ALL tests pass (old + new)
- `ruff check src/ tests/` -- no new errors
- `ruff format --check src/ tests/` -- all formatted
- `mypy src/` -- no new type errors
- CLI still works: `python -m src.cli` starts without crash (no DB mode)
- No modifications to `examples/` directory

**Complexity**: S
**Agent**: builder
**Parallel group**: Wave 7

---

## Dependency Graph

```
Wave 1 (parallel, no deps):
  T1.1  src/memory/types.py
  T1.2  src/moe/model_tier.py
  T1.3  FeatureFlags in settings.py
  T6.2  Prompt templates in prompts.py

Wave 2 (deps: Wave 1):
  T1.4  test_memory/ conftest + type tests         [blocked by T1.1]
  T1.5  test_moe/ conftest + model_tier tests       [blocked by T1.2]
  T2.1  EmbeddingService                            [blocked by T1.1]
  T3.1  MemoryAuditLog                              [blocked by T1.1]
  T3.2  TokenBudgetManager                          [blocked by T1.1]
  T5.1  QueryComplexityScorer                       [blocked by T1.2]
  T5.2  ModelRouter                                 [blocked by T1.2]
  T5.3  CostGuard                                   [blocked by T1.2]

Wave 3 (deps: Wave 2):
  T2.2  Test EmbeddingService                       [blocked by T2.1, T1.4]
  T3.3  ContradictionDetector                       [blocked by T2.1, T1.1]
  T3.4  TierManager                                 [blocked by T3.1, T1.1]
  T5.4  Test MoE components                         [blocked by T5.1, T5.2, T5.3, T1.5]
  T7.1  Test MemoryAuditLog                         [blocked by T3.1, T1.4]
  T7.2  Test TokenBudgetManager                     [blocked by T3.2, T1.4]

Wave 4 (deps: Wave 3):
  T3.5  MemoryRetriever (5-signal)                  [blocked by T2.1, T3.2, T1.1]
  T3.6  MemoryExtractor (double-pass)               [blocked by T2.1, T3.1, T3.3, T1.1]
  T7.3  Test ContradictionDetector                  [blocked by T3.3, T1.4]

Wave 5 (deps: Wave 4):
  T3.7  CompactionShield                            [blocked by T3.6]
  T4.1  MemoryPromptBuilder                         [blocked by T1.1, T3.5]
  T7.4  Test MemoryRetriever                        [blocked by T3.5, T1.4]

Wave 6 (deps: Wave 5):
  T6.1  Update dependencies.py                      [blocked by T2.1, T3.1, T3.3, T3.4, T3.5, T3.7, T4.1, T5.1, T5.2, T5.3, T1.3]
  T7.5  Test MemoryExtractor + CompactionShield     [blocked by T3.6, T3.7, T1.4]
  T7.6  Test MemoryPromptBuilder                    [blocked by T4.1, T1.4]

Wave 7 (deps: Wave 6):
  T6.3  Update agent.py (factory)                   [blocked by T4.1, T6.1, T6.2]
  T8.1  Integration test                            [blocked by T6.1, T6.3, T7.4, T7.5, T7.6]
  T8.2  Full verification                           [blocked by T8.1, T5.4]
```

## Critical Path

```
T1.1 -> T2.1 -> T3.3 -> T3.6 -> T3.7 -> T6.1 -> T6.3 -> T8.1 -> T8.2
(9 tasks deep, ~9 sequential units)
```

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 24 |
| Wave count | 7 |
| Critical path depth | 9 |
| New files created | ~30 (14 src + 16 test) |
| Existing files modified | 4 (settings, dependencies, agent, prompts) |
| Estimated effort | 3-5 days with parallelism |
| S tasks | 8 |
| M tasks | 13 |
| L tasks | 3 (T3.5 retriever, T3.6 extractor) |

## Risk Areas

1. **MemoryRetriever complexity (T3.5)**: Largest single component. 5 parallel signals + merge + dedup + score. May need to split further if implementation exceeds one session.
2. **MemoryExtractor LLM dependency (T3.6)**: Double-pass extraction requires LLM calls. Tests must fully mock these. If prompts need iteration, this could be the bottleneck.
3. **ContradictionDetector ambiguity (T3.3)**: "Same subject" detection relies on subject field matching, which may need fuzzy matching. Phase 2 should use exact match + embedding similarity; fuzzy matching deferred.
4. **Integration testing (T8.1)**: Pulling all services together in AgentDependencies.initialize() is complex. Mock setup will be verbose but necessary.
5. **Backward compatibility**: Every modification to existing files (T1.3, T6.1, T6.2, T6.3) must preserve CLI-only behavior. All new fields must be Optional.
