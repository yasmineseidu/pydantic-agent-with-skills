# Agent Team Learnings

**FORMAT: 1 line per item. No paragraphs. `CATEGORY: what → fix/reuse`**

## Mistakes (do NOT repeat)

- MISTAKE: `uv run pytest` uses system Python → use `.venv/bin/python -m pytest tests/ -v`
- MISTAKE: `uv sync` skips optional dev deps → use `uv add --dev pytest ruff mypy`
- MISTAKE: 14 pre-existing ruff warnings (F541, F401) → these are NOT from agent team setup

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

## Architecture

- DECISION: `@dataclass AgentDependencies` (not BaseModel) → mutable state + async init
- DECISION: `BaseModel SkillMetadata` → validation
- DECISION: `BaseSettings Settings` → env var loading
- DECISION: skills are filesystem-based → no DB for MVP
- DECISION: Phase 1 DB → 9 tables, src/db/ + src/models/ packages, 19 tasks in 9 waves

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
