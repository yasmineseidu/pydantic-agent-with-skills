# Cross-Layer Feature Team

## Purpose
Coordinate cross-module feature development with strict file ownership and interface management.

## When to Use
- Feature spans multiple modules (src/ + skills/ + tests/)
- Multiple agents need to write different files
- Interface contracts needed between modules
- Integration verification required after parallel work

## Mode
Single mode: phased execution with parallel steps where safe.

## Members

| Member | Agent File | Model | Role | Output Location |
|--------|-----------|-------|------|----------------|
| Coordinator | feature-team-coordinator.md | sonnet | Decomposes, spawns, manages interfaces | reports/feature-{name}.md |
| Builder | builder.md | sonnet | Core src/ implementation | (modifies src/ files) |
| Skill Builder | skill-builder.md | sonnet | Skills changes | (modifies skills/ files) |
| Tester | tester.md | sonnet | Test writing and verification | (reports on tests/) |
| Reviewer | reviewer.md | sonnet | Reviews completed work | reports/feature-{name}-review.md |

## Execution Pattern

```
Phase 1: Core changes (builder)     -> settings, dependencies, core modules
Phase 2: Implementation (builder)   -> agent, tools, skill_loader
Phase 3: Skills (skill-builder)     -> SKILL.md, references (can parallel with Phase 2 if no deps)
Phase 4: Tests (tester)             -> test files (after Phase 2+3)
Phase 5: Review (reviewer)          -> full review of all changes
```

**Parallel where safe**: Phase 2 + Phase 3 if no shared interfaces.
**Always sequential**: Phase 4 after 2+3. Phase 5 after 4.

## File Ownership

| Directory/Pattern | Owner | Notes |
|------------------|-------|-------|
| `src/agent.py` | builder | Core agent definition |
| `src/cli.py` | builder | CLI implementation |
| `src/dependencies.py` | builder | DI container |
| `src/http_tools.py` | builder | HTTP tooling |
| `src/prompts.py` | builder | System prompts |
| `src/providers.py` | builder | LLM providers |
| `src/settings.py` | builder | Configuration |
| `src/skill_loader.py` | builder | Skill discovery |
| `src/skill_tools.py` | builder | Skill tool impls |
| `src/skill_toolset.py` | builder | Toolset wrapper |
| `skills/*/SKILL.md` | skill-builder | Skill definitions |
| `skills/*/references/*` | skill-builder | Reference docs |
| `tests/test_*.py` | tester | Test files (read-only) |
| `src/__init__.py` | coordinator | Minimal changes only |

## Communication Protocol

| Layer | Active | Notes |
|-------|--------|-------|
| Structured Outputs | Yes | Each agent writes designated output |
| Shared Message Log | All three files | Full protocol for cross-module work |
| Coordinator Routing | Interface changes, blockers | Updates interfaces.md BEFORE re-spawning |

### Interface Management
- Coordinator writes `.claude/team-comms/interfaces.md`
- Builder implements core interface first
- Other agents implement against that interface
- INTERFACE-CHANGE messages trigger interfaces.md update + dependent re-spawns

## Done Conditions
- [ ] All phases complete
- [ ] `pytest tests/ -v` passes
- [ ] `ruff check src/ tests/` passes
- [ ] `mypy src/` passes
- [ ] No file ownership conflicts
- [ ] CROSS-DOMAIN tags addressed
- [ ] Review APPROVE issued

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
