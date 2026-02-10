# Agent Team Learnings

**FORMAT: 1 line per item. No paragraphs. `CATEGORY: what → fix/reuse`**

## Mistakes (do NOT repeat)

- MISTAKE: `uv run pytest` uses system Python → use `.venv/bin/python -m pytest tests/ -v`
- MISTAKE: `uv sync` skips optional dev deps → use `uv add --dev pytest ruff mypy`
- MISTAKE: 14 pre-existing ruff warnings (F541, F401) → these are NOT from agent team setup
- MISTAKE: ruff F541 f-strings without placeholders → remove `f` prefix from static error return strings
- MISTAKE: mock `session.add()` (sync method) creates coroutine warning → harmless but noisy in tests

## Patterns That Work

- PATTERN: progressive disclosure → metadata first (~100 tokens), instructions on demand, resources on reference
- PATTERN: structured logging → `f"action_name: key={value}"` format
- PATTERN: Pydantic Settings → `.env` → `Settings(BaseSettings)` → type-safe
- PATTERN: FunctionToolset → group tools in `src/skill_toolset.py` for reuse
- PATTERN: MockContext → `@dataclass MockContext(deps=MockDependencies)` for testing
- PATTERN: ruff format+check → single tool, line-length=100
- PATTERN: Google docstrings → Args/Returns/Raises on all public functions
- PATTERN: ORM suffix convention → `UserORM` avoids collision with Pydantic `UserCreate`
- PATTERN: SA metadata column → map `metadata` as `metadata_json` in Python (SA reserved word)
- PATTERN: Settings Optional fields → all new DB fields Optional so CLI works without DB
- PATTERN: TYPE_CHECKING → forward refs in dependencies.py avoid circular imports at runtime
- PATTERN: factory function → `create_skill_agent(dna=None)` returns singleton or new Agent
- PATTERN: 7-layer prompt → protected L1-L3 never trimmed, trim order L7→L6→L5→L4
- PATTERN: double-pass extraction → Pass1 high-confidence, Pass2 gap-filling, cosine >0.95 dedup
- PATTERN: 5-signal retrieval → semantic + recency(exp decay) + importance + continuity + relationship
- PATTERN: orthogonal embeddings → `[1]*768+[0]*768` vs `[0]*768+[1]*768` for low-similarity tests
- PATTERN: wave-based parallel build → group tasks by deps, deploy 3-4 agents per wave, max parallel
- PATTERN: token estimation → `math.ceil(len(text)/3.5)` heuristic, good enough for budget trimming
- PATTERN: FeatureFlags nested model → `settings.feature_flags.enable_memory` for runtime toggles

- PATTERN: graceful degradation → check `redis_manager.available` before ops, return None on failure
- PATTERN: Redis key namespacing → `{prefix}{type}:{scope_ids}` (e.g. `ska:hot:{agent_id}:{user_id}`)
- PATTERN: fakeredis for testing → `fakeredis[lua]~=2.26.0` with FakeAsyncRedis, no real Redis needed
- PATTERN: L0/L1/L2 cache hierarchy → in-memory dict (L0) → Redis (L1) → PostgreSQL (L2)
- PATTERN: Redis pipeline transactions → DEL + ZADD + EXPIRE atomic in hot_cache warm_cache()
- PATTERN: token-bucket rate limiter → INCR + EXPIRE atomic, degrades to allow-all when Redis down

## Gotchas

- GOTCHA: YAML frontmatter → must strip `---` delimiters before returning skill body
- GOTCHA: path security → always `resolve()` + `is_relative_to()` before reading skill files
- GOTCHA: AgentDependencies → `initialize()` must be called before skill_loader is used
- GOTCHA: asyncio_mode=auto → tests don't need `@pytest.mark.asyncio` but use it for clarity
- GOTCHA: imports → `from src.module import Class` (not relative imports)
- GOTCHA: .env.example → contains real credentials (flagged, not fixed)
- GOTCHA: memory_log.memory_id → NO FK intentionally (ADR-8: survives memory deletes)
- GOTCHA: pgvector IVFFlat → needs `CREATE EXTENSION vector` before index creation
- GOTCHA: SA JSONB defaults → use `server_default=text("'{...}'::jsonb")` not `default={}`
- GOTCHA: FunctionToolset[None] mypy error → pre-existing pydantic-ai type issue, ignore
- GOTCHA: cosine similarity dedup threshold → 0.95 for extraction, 0.92 for DB duplicate check
- GOTCHA: Redis ZSET scores are floats → ScoredMemory.final_score maps directly to ZADD score
- GOTCHA: Redis unavailable → return safe defaults (None, True, []), NEVER raise
- GOTCHA: fakeredis TTL timing → `assert 86399 <= ttl <= 86400` not exact equality (1s drift)
- GOTCHA: httpx code fence parsing → LLMs wrap JSON in ```json...```, must strip before json.loads
- GOTCHA: tier_manager demotion → never demote identity type, pinned, or importance >= 8

## Architecture

- DECISION: `@dataclass AgentDependencies` (not BaseModel) → mutable state + async init
- DECISION: `BaseModel SkillMetadata` → validation
- DECISION: `BaseSettings Settings` → env var loading
- DECISION: skills are filesystem-based → no DB for MVP
- DECISION: Phase 1 DB → 9 tables, src/db/ + src/models/ packages, 19 tasks in 9 waves
- DECISION: Phase 2 Memory → 10 modules in src/memory/, 4 in src/moe/, 14 test files, 273 new tests
- DECISION: compaction shield feature-flagged → `enable_compaction_shield` controls extraction before trim
- DECISION: CostGuard uses asyncio.Lock → in-memory daily/monthly budget tracking, no DB needed
- DECISION: Phase 3 Redis → feature-flagged `enable_redis_cache`, 4 cache modules, 86 new tests
- DECISION: Redis integration opt-in → `hot_cache` and `redis_cache` params default to None

## Useful Grep Patterns

- `Grep "from src." src/` → import graph
- `Grep "try:|except " src/` → error handling
- `Glob "skills/*/SKILL.md"` → all skills
- `Grep "async def" src/` → async entry points
- `Glob "tests/test_*.py"` → test coverage map

## Run Log

- 2026-02-09 setup: 19 agents, 4 skills, 6 team defs, 71 tests pass, zero regressions
- 2026-02-09 specs: full YAML frontmatter on all 19 agents, complexity-based model selection
- 2026-02-09 blueprint: CROSS-DOMAIN/BLOCKER protocol, context tiers, 5 team def files
- 2026-02-09 grep-mcp: WebSearch+WebFetch on 5 coding agents, 3-layer enforcement
- 2026-02-09 4-enforce: LSP + Plan + Learning + TaskMgmt mandatory across all agents
- 2026-02-09 settings: MCP settings in .claude/settings.json + ~/.claude/settings.json, grep-local-first mandatory, non-verbose learnings
- 2026-02-09 prd-phase1: 19 tasks created (#6-#24), 9 waves, 7 tracks, critical path 8 deep
- 2026-02-09 phase2-build: 24 tasks, 7 waves, 21 agents deployed, 445 tests (273 new), 0 failures
- 2026-02-09 phase2-commit: 106df03 pushed to main, 49 files changed, 11232 lines added
- 2026-02-09 phase3-build: 18 tasks, 6 waves, ~12 agents deployed, 531 tests (86 new), 0 failures
