---
name: team-coordination
description: Protocol for multi-agent team coordination. Covers output format, messaging, file ownership, status tracking, and done checklists.
version: 1.0.0
author: Agent Team System
---

# Team Coordination Protocol

Language-agnostic protocol for coordinating multi-agent teams in Claude Code.

## Output Format (Structured Output Files)

Every agent MUST structure output as:

```markdown
# [Role] Report
Status: COMPLETE | IN-PROGRESS | BLOCKED | FAILED

## [Agent Name] - [Action Summary]

**Files touched**: [list of files modified]
**Tests affected**: [list of test files]

### Findings / Changes Made
### [Title]
- File: path/to/file:line
- Severity: CRITICAL|HIGH|MEDIUM|LOW
- [bullet list of changes or findings]

### Cross-Domain Tags
- CROSS-DOMAIN:{TARGET}: {message}
- BLOCKER:{TARGET}: {what you need}

### Verification
- [ ] Code compiles/runs
- [ ] Tests pass
- [ ] No lint errors
- [ ] Matches existing patterns

### Knowledge Base Additions
[Patterns worth adding to LEARNINGS.md]
```

## CROSS-DOMAIN and BLOCKER Protocol

Agents use tags in their output reports to signal cross-boundary issues.
Coordinators MUST grep ALL agent outputs for these tags before synthesis.

### CROSS-DOMAIN:{TARGET}
Used when an agent finds something that affects another agent's domain.

```
CROSS-DOMAIN:builder: The API response shape changed, update src/http_tools.py:42
CROSS-DOMAIN:tester: New function load_advanced_skill() needs test coverage
CROSS-DOMAIN:reviewer: Security concern in new file path handling at src/skill_tools.py:87
```

**Coordinator action**: Create follow-up task for TARGET agent with the actual finding
(not "check the report" -- include the specific content).

### BLOCKER:{TARGET}
Used when an agent is blocked by another agent's work.

```
BLOCKER:builder: Cannot test API integration until http_tools.py timeout handling is implemented
BLOCKER:coordinator: Interface contract undefined for new skill_loader method
```

**Coordinator action**: Check blocker status. If resolved, re-spawn blocked agent with context.
If blocked >1 cycle, investigate and escalate.

### Message Types (for shared message log)
- **INFO**: General status update
- **INTERFACE-CHANGE**: Contract changed (coordinator documents in task descriptions)
- **BLOCKER**: Agent is blocked (coordinator investigates)
- **QUESTION**: Agent needs clarification
- **RESOLVED**: Previously blocked issue resolved

### Coordinator Routing Rules
1. CROSS-DOMAIN tag found -> create follow-up task for target with actual finding
2. BLOCKER found -> check blocker status, re-spawn when resolved
3. INTERFACE-CHANGE -> document in task descriptions BEFORE re-spawning dependents
4. FAILED -> retry or escalate
5. BLOCKED >1 cycle -> investigate root cause
6. Always include actual findings in routed messages (not "check the report")

## Context Loading Tiers

Task-aware context loading. Not static -- varies by agent and current task.

### ALWAYS Load (every agent, every session)
- `LEARNINGS.md` - Patterns and mistakes
- Conventions skill (coding-conventions)
- Team-coordination skill (this file)

### LOAD When Relevant (per task)
- Files directly related to current task
- Interface contracts for cross-module work
- Status.md for team state
- Prior agent reports relevant to current task

### NEVER Load
- Other stages' intermediate outputs (unless directly needed)
- Superseded versions of documents
- Consumed intermediates from completed phases
- Full raw dumps (coordinator passes focused summaries instead)

### Coordinator Context Passing
Coordinators pass focused summaries to agents, NOT raw file dumps:
```
GOOD: "The architecture.md defines a REST API with 3 endpoints: GET /skills, POST /skills/{name}/load, GET /skills/{name}/files/{path}"
BAD: "Read the full architecture.md file for context"
```

## File Ownership Rules

### Exclusive Ownership
Each file has ONE owner agent. Only the owner may modify it.

### Ownership Map (This Project)

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
| `skills/*/references/*` | documenter | Reference docs |
| `tests/test_*.py` | tester | Test files |
| `tests/evals/*` | tester | Evaluation configs |
| `.claude/agents/*` | system-architect | Agent definitions |
| `.claude/skills/*` | system-architect | Agent skills |
| `CLAUDE.md` | orchestrator | Project instructions |
| `LEARNINGS.md` | orchestrator | Shared learnings |
| `pyproject.toml` | orchestrator | Dependencies |
| `README.md` | documenter | Project docs |
| `reports/prd/requirements.md` | requirements-extractor | PRD requirements |
| `reports/prd/technical-research.md` | technical-researcher | PRD research |
| `reports/prd/architecture.md` | architecture-designer | PRD architecture |
| `reports/prd/task-tree.md` | task-decomposer | PRD task tree |
| `reports/prd/final-prd.md` | prd-team-coordinator | PRD synthesis |
| `reports/*` (other) | coordinator (any) | Team reports |

### Coordinator-Managed Files
These files may be touched by coordinators when resolving cross-agent conflicts:
- `team-registry/*` - All coordinators (team defs, run logs)
- `team-registry/run-logs/*` - All coordinators (write after each run)
- `src/__init__.py` - Any builder (minimal changes only)
- `reports/*` - Coordinators and their team members (exclusive per report)

### Protected Files (NEVER TOUCH)
- `examples/` - Reference only, DO NOT MODIFY
- `.env` - Contains secrets, DO NOT COMMIT
- `.claude/PRD.md` - Product requirements, read-only

## Done Checklist

Before marking ANY task as complete, verify:

### Code Quality
- [ ] ruff format passes: `ruff format --check src/ tests/`
- [ ] ruff lint passes: `ruff check src/ tests/`
- [ ] mypy passes: `mypy src/`
- [ ] No new warnings introduced

### Testing
- [ ] Existing tests still pass: `pytest tests/ -v`
- [ ] New code has tests (if applicable)
- [ ] Integration tests pass

### Patterns
- [ ] Follows existing import ordering
- [ ] Uses existing error handling pattern
- [ ] Has Google-style docstrings
- [ ] Type annotations on all functions
- [ ] Structured logging format used

### Documentation
- [ ] LEARNINGS.md updated (if new pattern discovered)
- [ ] README.md updated (if user-facing change)

### Handoff
- [ ] Blocking agents notified via messages
- [ ] Files touched listed in output

## Task Decomposition (MANDATORY - ALL COORDINATORS)

**Every piece of work MUST be decomposed into tracked tasks.** No untracked work.
No spawning agents without a task. No "just do it quick" bypasses.

### Before Spawning ANY Agent
```
1. TaskCreate for each unit of work
   - Clear title (imperative: "Implement X", "Review Y")
   - Description with acceptance criteria
   - File ownership boundaries
   - addBlockedBy for dependencies
2. Only THEN spawn the agent with the task ID
```

### Task Granularity Rules
- Each task = one agent, one session, clear done criteria
- If a task needs more than ~30 turns, it's too big -- split it
- If two tasks write the same file, merge them or sequence them
- Every task must have testable acceptance criteria

### Tracking During Execution
```
Agent starts → TaskUpdate status = "in_progress"
Agent done → TaskUpdate status = "completed" (only if verified)
Agent blocked → Keep in_progress, log BLOCKER
Agent failed → Keep in_progress, create fix task
```

### After ALL Tasks Complete
```
1. TaskList to verify all tasks completed
2. Run full verification (pytest, ruff, mypy)
3. Write run log to team-registry/run-logs/
4. Update LEARNINGS.md with session notes
```

### Anti-Patterns (NEVER DO)
- Spawn an agent without creating a task first
- Let agents do work that isn't tracked by a task
- Mark tasks complete without running verification
- Create vague tasks ("fix stuff", "make it work")

## Learning Protocol (MANDATORY - ALL AGENTS)

**Every session starts with learning. Every session ends with teaching.**

### Coordinator Startup (FIRST FOUR THINGS)
```
1. Read LEARNINGS.md
2. Grep for keywords related to current work
3. TaskList for prior in-progress work
4. Read relevant team definition
```

### Coordinator Shutdown (ALWAYS)
Write substantive session summary to LEARNINGS.md:
```markdown
### [Team] Run - [Date]
**What worked:**
- [specific pattern/approach that succeeded]

**What didn't work:**
- [specific mistake with context]

**Gotchas:**
- [unexpected issue + workaround]

**Tasks:** X created, Y completed, Z remaining
```

### Worker Agent Learning
- Workers read LEARNINGS.md at startup (enforced via coding-conventions skill)
- Workers include "### Learnings" section in their output
- Coordinator routes substantive learnings to LEARNINGS.md

### Anti-Patterns (NEVER DO)
- Skip reading LEARNINGS.md ("I already know this project")
- Write timestamps-only to LEARNINGS.md (the Stop hook does this -- YOU write substance)
- Repeat a documented mistake
- Lose context between sessions by not writing learnings

## Retry Limits

| Operation | Max Retries | Action on Failure |
|-----------|-------------|-------------------|
| Build + Test | 3 | Escalate to orchestrator |
| Review + Fix | 5 | Escalate to orchestrator |
| Research | 2 | Report findings, move on |
| Deploy check | 1 | Block and report |

## Model Selection (Complexity-Based)

Coordinators MUST assess complexity before spawning subagents. Default models in
agent frontmatter are for typical cases. Override with the `model` parameter on
the Task tool when complexity warrants it.

### Complexity Score

Score each dimension 0-2, sum for total:

| Dimension | 0 (Low) | 1 (Medium) | 2 (High) |
|-----------|---------|------------|----------|
| **Ambiguity** | Clear requirements, few gaps | Some undefined areas | Vague, many unknowns |
| **Integration** | 0-2 touchpoints | 3-5 touchpoints | 6+ touchpoints, cross-cutting |
| **Novelty** | Extends existing patterns | Mix of existing + new patterns | Entirely new architecture |
| **Risk** | Low-impact, easily reversible | Moderate impact, some risk | Security-critical, data migration |
| **Scale** | < 5 files affected | 5-15 files | 15+ files or multi-service |

### Model Decision

| Score | Model | Rationale |
|-------|-------|-----------|
| 0-1 | **haiku** | Trivial work, single-pattern, no judgment needed |
| 2-3 | **sonnet** | Straightforward work, clear patterns to follow |
| 4-6 | **sonnet** (default), **opus** if ambiguity or risk >= 2 | Moderate complexity, upgrade on judgment calls |
| 7-10 | **opus** | Complex work requiring deep reasoning |

### When to Use Haiku (score 0-1)
- Extracting requirements from a clear, structured spec (no gaps to identify)
- Decomposing a small feature with < 5 obvious tasks
- Researching a single well-known library (just fetch + summarize docs)
- Any task that is purely mechanical with zero judgment calls

### When to Use Sonnet (score 2-6)
- Extracting requirements from conversational/informal input
- Researching libraries/patterns (compare options, evaluate tradeoffs)
- Decomposing well-defined architecture into tasks
- Following established patterns to new files

### When to ALWAYS Use Opus (regardless of score)
- Novel architecture decisions with no existing pattern to follow
- Security-critical design (auth, encryption, access control)
- Ambiguous requirements needing interpretation (not just extraction)
- Cross-service integration design

### Coordinator Spawn Pattern

```
Before spawning, assess complexity:
1. Score the 5 dimensions (0-2 each)
2. Sum the score
3. Check model overrides (always-opus / haiku-eligible)
4. Pass model parameter: Task(model="haiku|sonnet|opus", ...)
5. Log: "[coordinator] Spawning {agent} with {model} (score: {N})"
```

## Context Window Budget (MANDATORY)

Pre-loaded context per agent session is approximately 25-30K tokens:
- CLAUDE.md (~12K tokens)
- MEMORY.md (~3K tokens)
- Agent instructions (~3-5K tokens)
- Loaded skills (~4-8K tokens)

### Budget Guidelines

| Session Length | Context Strategy |
|---------------|-----------------|
| Short (< 10 turns) | Load everything: LEARNINGS.md, team definition, full codebase scan |
| Medium (10-30 turns) | Load LEARNINGS.md (first 50 lines), skip team definition if familiar |
| Long (> 30 turns) | Skip LEARNINGS.md reload, skip skill files, rely on cached knowledge |

### LEARNINGS.md Reading Budget
- Read first 50 lines maximum at startup
- Grep for keywords related to current task instead of reading all
- If LEARNINGS.md exceeds 100 lines, coordinator should prune it

### Reducing Agent Instruction Redundancy
- When an instruction exists in a loaded skill, reference the skill instead of repeating:
  ```
  GOOD: "Follow MANDATORY STARTUP from coding-conventions skill"
  BAD:  (repeating the full 15-line startup protocol in agent instructions)
  ```
- Coordinators: pass focused summaries, not raw file dumps (see Context Loading Tiers)

### Anti-Patterns (NEVER DO)
- Load full LEARNINGS.md when it exceeds 100 lines
- Read all team definitions when working on a single team
- Include raw file content in agent task descriptions when a summary suffices
- Skip LEARNINGS.md entirely ("I already know this project")

## Cost Awareness

Approximate token costs per agent session (2025 pricing, varies by session length):

| Model | Cost per Session | Typical Use |
|-------|-----------------|-------------|
| haiku | $0.05 - $0.10 | Mechanical tasks, simple extraction |
| sonnet | $0.50 - $2.00 | Standard development, research, reviews |
| opus | $2.00 - $10.00 | Architecture, security, complex judgment |

### Team Run Estimates

| Team | Typical Cost | Agents Involved |
|------|-------------|-----------------|
| Parallel Review | $2 - $5 | sonnet coordinator + sonnet reviewer + sonnet tester |
| Cross-Layer Feature | $5 - $15 | sonnet coordinator + 2-4 sonnet workers |
| Research Swarm | $3 - $8 | sonnet coordinator + 2-4 sonnet researchers |
| Competing Hypotheses | $3 - $10 | sonnet coordinator + 2-3 sonnet/opus investigators |
| PRD Decomposition | $15 - $30 | opus coordinator + 4 sonnet/opus specialists |
| Plan-Then-Execute | $5 - $20 | sonnet coordinator + variable execution agents |

### Cost Optimization Rules
1. **Default to sonnet** -- only upgrade to opus when complexity score >= 7 or ambiguity/risk >= 2
2. **Use haiku for mechanical work** -- requirement extraction from structured specs, simple task decomposition
3. **Log model selection** -- coordinators MUST log: `"[coordinator] Spawning {agent} with {model} (score: {N}, cost: ~${estimate})"`
4. **Avoid unnecessary re-spawns** -- check if prior agent output is usable before re-running
5. **Budget alerts** -- if a team run exceeds 5 agent spawns, pause and assess if more are needed

### Anti-Patterns (NEVER DO)
- Use opus for mechanical tasks (formatting, simple extraction, file listing)
- Spawn 4 researchers when 2 would cover the topic
- Re-spawn an agent because output "could be better" without specific gaps
- Skip complexity scoring ("just use sonnet for everything")

## Escalation Protocol

1. Agent hits retry limit → Reports to coordinator
2. Coordinator can't resolve → Reports to orchestrator
3. Orchestrator can't resolve → Reports to user
4. Never silently swallow failures
