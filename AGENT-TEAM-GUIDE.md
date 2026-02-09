# Agent Team System -- Usage Guide

How to drive the car, not how to build it.

---

## Quick Start (30 seconds)

### Install the Lite Team (3 agents)

Tell Claude Code:

```
Build me the lite agent team system using agent-team-build-lite.md
```

Claude reads the blueprint and creates 3 agents, 1 skill, and all wiring.

### Install the Full Team (19 agents)

Tell Claude Code:

```
Build me the full agent team system using agent-team-build-greenfield.md
```

### Verify It Works

After install, type any of these into Claude Code:

```
"Build a hello world endpoint"     --> builder agent activates
"Run the tests"                    --> tester agent activates
"Review the auth module"           --> reviewer activates (full) or builder (lite)
```

If the agent name appears in the output header, it is working.

### Customize Your Rules

After install, personalize your rules:

1. Edit `.claude/rules/coding-principles.md` for your coding standards
2. Edit `.claude/rules/testing-patterns.md` for your test patterns
3. Create `CLAUDE.local.md` for personal preferences (auto-gitignored)

---

## How It Works (2-minute overview)

### The 3-Tier Architecture

```
YOU (type a request in Claude Code)
 |
 v
+------------------+
|   ORCHESTRATOR   |   Tier 1: Routes your request
|   (opus model)   |   Reads your words, picks the right agent/team
+------------------+
 |
 v
+------------------+     +------------------+     +------------------+
|    BUILDER       |     |    TESTER        |     |   REVIEWER       |
|    (sonnet)      |     |    (sonnet)      |     |   (sonnet)       |
|  writes code     |     |  runs tests      |     |  reviews code    |
+------------------+     +------------------+     +------------------+
 |                         |                         |
 v                         v                         v
+--------------------------------------------------------------+
|                    SKILLS (shared knowledge)                  |
|  coding-conventions | team-coordination | security-standards  |
+--------------------------------------------------------------+
 |
 v
+--------------------------------------------------------------+
|                    RULES (.claude/rules/)                     |
|  9 path-scoped files loaded contextually per task             |
+--------------------------------------------------------------+
 |
 v
+--------------------------------------------------------------+
|                    LEARNINGS.md (shared memory)               |
|  Mistakes | Patterns | Gotchas | Run Log                     |
+--------------------------------------------------------------+
```

### What Happens When You Type a Request

```
1. You type: "Add a login endpoint"
2. Orchestrator reads your request
3. Orchestrator checks LEARNINGS.md for context
4. Orchestrator routes to: builder (simple) or feature-team (complex)
5. Builder reads existing code patterns first (mandatory)
6. Builder searches GitHub for battle-tested examples (mandatory)
7. Builder writes code, runs formatter, runs linter
8. Builder checks for errors via LSP
9. Builder runs tests
10. Builder reports results back to orchestrator
11. Orchestrator reports to you
```

### The Routing Flow

```
Your Request
     |
     +-- "build/add/fix" ---------> builder
     |
     +-- "test/verify" -----------> tester
     |
     +-- "review/audit" ----------> review-team-coordinator
     |
     +-- "research/find" ---------> research-swarm-coordinator
     |
     +-- "plan/design/PRD" -------> prd-team-coordinator
     |
     +-- "document/explain" ------> documenter
     |
     +-- "debug complex issue" ---> hypothesis-team-coordinator
     |
     +-- "refactor/migrate" ------> plan-execute-coordinator
     |
     +-- "create agent/skill" ----> system-architect
     |
     +-- "assess risk" -----------> risk-assessor
     |
     +-- unclear/complex ---------> orchestrator asks YOU
```

---

## Modern Memory Architecture

### The Rules System

Instead of one massive instruction file, the system uses modular rules that load contextually:

```
+---------------------------------------------------------------+
|                    .claude/rules/ (9 files)                    |
|                                                                |
|  mandatory-practices.md  -- Always loaded (all files)          |
|  coding-principles.md    -- Loaded when editing src/ or tests/ |
|  common-pitfalls.md      -- Loaded when editing source code    |
|  testing-patterns.md     -- Loaded when editing tests          |
|  agent-system.md         -- Loaded when editing agents/teams   |
|  skill-system.md         -- Loaded when editing skills         |
|  configuration.md        -- Loaded when editing config files   |
|  documentation-style.md  -- Loaded when editing .py or .md     |
|  security.md             -- Loaded when editing source code    |
+---------------------------------------------------------------+
```

**Why this matters**: Agents only see rules relevant to what they're working on. An agent editing tests sees testing-patterns.md but not configuration.md. This keeps context focused and reduces noise.

### How It Connects

```
CLAUDE.md (compact, ~300 lines)
  |
  +-- @.claude/rules/coding-principles.md    (loaded via @import)
  +-- @.claude/rules/mandatory-practices.md  (loaded via @import)
  +-- @.claude/rules/agent-system.md         (loaded via @import)
  +-- @.claude/rules/security.md             (loaded via @import)
  +-- ... (5 more @imports)
  |
  +-- .claude/skills/ (deep-dive reference, loaded on demand)
```

### CLAUDE.local.md (Personal Preferences)

Create `CLAUDE.local.md` in the project root for personal preferences that don't belong in version control:

```markdown
# Local Preferences
- Preferred model: opus for planning, sonnet for execution
- Always show file:line references in responses
```

This file is automatically gitignored by the setup script.

---

## Talking to Your Team

### What to Say --> What Happens

| You type this | Agent that handles it | What it does |
|--------------|----------------------|--------------|
| "Add a user profile page" | builder | Writes the code, tests it, formats it |
| "Fix the login bug" | builder | Reads error, greps for pattern, fixes it |
| "Run the tests" | tester | Runs test suite, reports pass/fail with line numbers |
| "Review src/agent.py" | review-team-coordinator | Parallel review: patterns + security + tests |
| "Research the best ORM for this project" | research-swarm-coordinator | Multiple researchers compare options |
| "Plan out a notification system" | prd-team-coordinator | Produces requirements, architecture, task tree |
| "Explain how the skill loader works" | documenter | Reads code, writes clear documentation |
| "Why is the API returning 500 errors?" | hypothesis-team-coordinator | Parallel investigators test competing theories |
| "Refactor the database module" | plan-execute-coordinator | Plans steps, executes in order, verifies each |
| "Create an agent for deployment" | system-architect | Creates new agent definition file |
| "What could go wrong with this migration?" | risk-assessor | Read-only risk analysis with mitigations |

### Good vs Bad Requests

| Good (specific, actionable) | Bad (vague, ambiguous) |
|----------------------------|----------------------|
| "Add a /health endpoint that returns 200" | "Make the API better" |
| "Fix the TypeError in skill_loader.py line 42" | "Fix the bugs" |
| "Review src/agent.py for security issues" | "Check the code" |
| "Research Python async HTTP clients, compare aiohttp vs httpx" | "Find a library" |
| "Plan a caching layer for the skill loader" | "Speed things up" |

Tip: The more specific your request, the better the routing and the better the result.

### The Lite Team (3 agents)

Best for: Solo developers, small projects, getting started.

```
+-------------------------------------------+
|              LITE TEAM (3)                |
|                                           |
|  +-------------+                          |
|  | orchestrator | --+-- routes to -+      |
|  +-------------+   |              |      |
|                     v              v      |
|              +---------+    +--------+   |
|              | builder |    | tester |   |
|              +---------+    +--------+   |
|                                           |
|  1 skill: coding-conventions              |
+-------------------------------------------+
```

What you can say to the lite team:

```
"Build X"          --> builder handles it
"Fix X"            --> builder handles it
"Test X"           --> tester handles it
"Review X"         --> builder reviews + fixes (no separate reviewer)
"Research X"       --> orchestrator handles directly via WebSearch
```

### The Full Team (19 agents)

Best for: Large projects, teams, complex multi-module work.

```
+---------------------------------------------------------------+
|                     FULL TEAM (19)                             |
|                                                               |
|  CORE (6)              COORDINATORS (6)     SPECIALISTS (7)   |
|  +--------------+      +--------------+     +--------------+  |
|  | orchestrator |      | review-team  |     | skill-builder|  |
|  | builder      |      | feature-team |     | system-arch  |  |
|  | reviewer     |      | hypothesis   |     | req-extract  |  |
|  | tester       |      | research-swm |     | tech-research|  |
|  | researcher   |      | plan-execute |     | arch-designer|  |
|  | documenter   |      | prd-team     |     | task-decomp  |  |
|  +--------------+      +--------------+     | risk-assessor|  |
|                                             +--------------+  |
|                                                               |
|  4 skills: coding-conventions, team-coordination,             |
|            security-standards, research-patterns              |
+---------------------------------------------------------------+
```

Additional capabilities over lite:

| Capability | What it enables |
|-----------|----------------|
| Parallel code review | Reviewer + tester run simultaneously |
| Research swarms | 2-4 researchers investigate in parallel |
| PRD decomposition | Turn ideas into build-ready task trees |
| Competing hypotheses | Debug complex issues with parallel theories |
| Plan-then-execute | Safe refactoring with step-by-step verification |
| Risk assessment | Read-only risk analysis before big changes |

---

## Common Workflows

### Build a Feature

**Simple feature (single agent):**

```
You:   "Add a /health endpoint that returns {status: ok}"
```

Behind the scenes:

```
1. orchestrator routes to builder
2. builder reads LEARNINGS.md (check for gotchas)
3. builder greps local codebase (find existing endpoint patterns)
4. builder searches GitHub (find battle-tested health check patterns)
5. builder writes the code, matching existing style
6. builder runs formatter + linter + tests
7. builder checks LSP diagnostics (no type errors)
8. builder reports back
```

**Complex feature (team):**

```
You:   "Build a notification system with email and webhook support"
```

Behind the scenes:

```
1. orchestrator routes to feature-team-coordinator
2. coordinator spawns:
   - builder (writes core src/ code)
   - skill-builder (writes skill definitions if needed)
   - tester (verifies coverage)
   - reviewer (reviews completed work)
3. Each agent works on their owned files
4. Coordinator collects CROSS-DOMAIN tags
5. Coordinator routes follow-ups
6. Final report delivered to you
```

### Fix a Bug

**Simple bug:**

```
You:   "Fix the TypeError on line 42 of skill_loader.py"
```

Flow: orchestrator --> builder --> reads file --> fixes --> tests --> done.

**Complex bug (unknown cause):**

```
You:   "The API returns 500 errors intermittently, can't figure out why"
```

Flow:

```
1. orchestrator routes to hypothesis-team-coordinator
2. coordinator spawns 2-3 researchers, each testing a hypothesis:
   - Researcher A: "Race condition in async handlers"
   - Researcher B: "Database connection pool exhaustion"
   - Researcher C: "Memory leak in skill loader"
3. Each researcher investigates independently
4. Coordinator synthesizes: "Researcher B found the root cause"
5. Coordinator routes fix to builder with specific findings
```

### Review Code

**Quick review:**

```
You:   "Review src/agent.py"
```

**Full review with fixes:**

```
You:   "Do a thorough review of the entire src/ directory"
```

Flow:

```
1. review-team-coordinator determines scope
2. Spawns in parallel:
   - reviewer: Pattern compliance + security (can fix issues)
   - tester: Test coverage analysis
   - researcher: Architecture context (thorough mode only)
3. Reviewer fixes issues it finds (up to 5 fix cycles)
4. Coordinator synthesizes report: APPROVE or REQUEST_CHANGES
```

### Plan a Project

```
You:   "Plan out a caching layer for the skill loader"
```

Flow:

```
1. prd-team-coordinator receives request
2. Phase 1 - Requirements:
   - requirements-extractor interviews you, produces requirements.md
3. Phase 2 - Research:
   - technical-researcher scans codebase + searches GitHub
4. Phase 3 - Architecture:
   - architecture-designer creates architecture.md
5. Phase 4 - Task breakdown:
   - task-decomposer creates atomic task tree
6. Coordinator produces final-prd.md
7. You approve or request changes
```

What you get at the end:

```
reports/prd/
  requirements.md        <-- What needs to be built
  technical-research.md  <-- How others have solved it
  architecture.md        <-- Technical design
  task-tree.md           <-- Build-ready task list
  final-prd.md           <-- Complete PRD document
```

### Research Something

**Single topic:**

```
You:   "Research Python async HTTP client libraries"
```

**Comparative research (swarm):**

```
You:   "Compare FastAPI vs Litestar vs Starlette for our use case"
```

Flow:

```
1. research-swarm-coordinator spawns 2-4 researchers
2. Each researcher investigates one option
3. Coordinator synthesizes comparative report
4. Report includes: pros, cons, recommendation, evidence
```

---

## Understanding the Output

### Agent Reports

Every agent produces structured output:

```
## Builder - Added /health endpoint

Status: COMPLETE
Files touched: src/api.py, tests/test_api.py
Tests affected: tests/test_api.py

### Changes Made
- Added health_check() handler at src/api.py:45
- Added test_health_endpoint() at tests/test_api.py:30

### Verification
- [x] Code compiles
- [x] Tests pass (71/71)
- [x] No lint errors
- [x] Matches existing patterns

### Learnings
- PATTERN: health endpoints -> return dict, no DB check needed
```

### CROSS-DOMAIN Tags

When an agent finds something that affects another agent's area:

```
CROSS-DOMAIN:builder: The API response shape changed, update src/http_tools.py:42
CROSS-DOMAIN:tester: New function needs test coverage
```

These are automatically routed by the coordinator. You do not need to act on them
unless the coordinator escalates.

### BLOCKER Tags

When an agent is stuck waiting on something:

```
BLOCKER:builder: Cannot test API until timeout handling is implemented
```

The coordinator investigates and resolves blockers automatically. If unresolvable,
it escalates to you.

### What LEARNINGS.md Does for You

LEARNINGS.md is the team's shared memory. It persists across sessions.

```
+-------------------+     +-------------------+     +-------------------+
| Session 1         |     | Session 2         |     | Session 3         |
| Agent makes       | --> | Agent reads       | --> | Agent avoids      |
| mistake, logs it  |     | learnings first   |     | the same mistake  |
+-------------------+     +-------------------+     +-------------------+
```

Every agent reads LEARNINGS.md at startup and writes to it at shutdown. Format:

```
MISTAKE: uv run pytest uses system Python -> use .venv/bin/python -m pytest
PATTERN: progressive disclosure -> metadata first, instructions on demand
GOTCHA: YAML frontmatter -> must strip --- delimiters before returning body
```

---

## The 6 Practices (What Your Agents Do Automatically)

You do not need to tell agents to do these things. They are enforced at 3 layers:
skill files, agent definitions, and CLAUDE.md.

### 1. Grep Local First

Before writing any code, agents search YOUR codebase for existing patterns.
They never assume -- they verify.

```
Agent thinks: "I need to add a function"
Agent does:   Grep "def " src/  --> finds existing function style
              Read src/agent.py --> reads the actual file first
```

### 2. Grep GitHub

After local search, agents search millions of GitHub repos for battle-tested code.
Uses the grep-mcp tool (`grep_query`).

```
Agent thinks: "I need an async HTTP client pattern"
Agent does:   grep_query: query="async http client", language="python"
              --> finds proven patterns, adapts to your style
```

### 3. LSP Checks

After every edit, agents run language server diagnostics. Before modifying a
function, they check its definition and all references.

```
After edit:    getDiagnostics -> catches type errors immediately
Before modify: goToDefinition -> understands current implementation
Before rename: findReferences -> finds every usage across codebase
```

### 4. Plan First

Before non-trivial changes, agents write a plan listing files to read, changes
to make, and how to verify.

```
### Plan: Add health endpoint
1. Read: src/api.py, tests/test_api.py
2. Search: "health endpoint fastapi" on GitHub
3. Changes: Add handler in src/api.py, add test in tests/test_api.py
4. Verify: pytest tests/ -v, ruff check src/
```

### 5. Learn

Agents read LEARNINGS.md at the start of every session. They write concise
learnings at the end. One line each, max 120 characters.

### 6. Track Progress

Every piece of work is tracked via TaskUpdate. Status goes from `in_progress`
to `completed` only after all verification passes. Agents never mark tasks
complete if tests are failing.

---

## Customization

### Changing Your Stack

Edit these files with your language, tools, and conventions:

| What to change | Where to change it |
|---------------|-------------------|
| Language, formatter, linter, test runner | `.claude/skills/coding-conventions/SKILL.md` |
| Project-specific commands | `.claude/agents/orchestrator.md` (Detected Commands) |
| Protected paths | `.claude/agents/orchestrator.md` + `CLAUDE.md` |
| Naming conventions | `.claude/skills/coding-conventions/SKILL.md` |
| Error handling patterns | `.claude/skills/coding-conventions/SKILL.md` |
| Mandatory practices | `.claude/rules/mandatory-practices.md` |
| Coding principles | `.claude/rules/coding-principles.md` |
| Security rules | `.claude/rules/security.md` |
| Test patterns | `.claude/rules/testing-patterns.md` |
| Personal preferences | `CLAUDE.local.md` (gitignored) |

### Adding a New Agent

Tell Claude Code:

```
"Create a new agent for database migrations"
```

The `system-architect` agent handles this. It creates:
- Agent definition at `.claude/agents/your-agent.md`
- Routing entry in CLAUDE.md
- Appropriate tools, hooks, and skill references

Or manually: copy an existing agent file in `.claude/agents/`, modify the YAML
frontmatter and body, and add a routing entry to CLAUDE.md.

### Adding a New Skill

Tell Claude Code:

```
"Create a new skill for API design conventions"
```

The `skill-builder` agent handles this. It creates:
- Skill directory at `.claude/skills/your-skill/`
- SKILL.md with YAML frontmatter and instructions
- References the skill from relevant agent definitions

### Switching Lite to Full

The lite system is designed to grow. Four stages:

```
Stage 0: Lite (3 agents)        <-- you start here
  |
  v  add reviewer + review-team-coordinator + security-standards skill
Stage 1: +Review (5 agents)
  |
  v  add researcher + documenter + research-patterns skill
Stage 2: +Research (7 agents)
  |
  v  add 6 coordinators + skill-builder + team-coordination skill
Stage 3: +Coordinators (13 agents)
  |
  v  add 6 specialists (system-architect, req-extractor, etc.)
Stage 4: Full (19 agents)
```

At each stage: add new agent files, update CLAUDE.md routing table, add new
skills. Never modify existing agents -- only add new ones.

Full templates for every stage are in `agent-team-build-greenfield.md`.

---

## Troubleshooting

### Agent Not Routing Correctly

**Symptom**: You say "build X" but the wrong agent handles it.

**Fix**: Check the orchestrator's routing table in `.claude/agents/orchestrator.md`.
The `description` field in each agent's YAML frontmatter contains trigger words.
Make sure your request matches the trigger words.

```
Good triggers in description:
  "build, implement, add, create, code, write, fix, modify, update, change"

If routing fails, be more explicit:
  Instead of "handle the auth" say "build the auth endpoint"
```

### Agent Ignoring Instructions

**Symptom**: Agent writes code that does not follow your conventions.

**Fix**: Check `.claude/skills/coding-conventions/SKILL.md`. This is the single
source of truth for code style. Make sure it contains your actual patterns, not
placeholder values.

Common cause: Placeholders like `{LANGUAGE}` or `{FORMATTER}` were never replaced
with real values.

### Tests Failing After Agent Changes

**Symptom**: Agent reports "done" but tests fail when you run them.

**Fix**: Check if the agent marked the task as `completed`. Agents should never
mark complete with failing tests. If this happens:

1. Check LEARNINGS.md for what the agent tried
2. Ask the builder to fix it: "Fix the failing tests in test_agent.py"
3. The build-test-fix loop allows up to 3 retries before escalating to you

### How to Check What Happened

**Pipeline log** (what agents did, in order):

```bash
cat reports/.pipeline-log
```

Output looks like:

```
[orchestrator] 14:32:01 spawned agent
[builder] 14:32:01 EDIT: src/agent.py
[builder] 14:32:15 EDIT: tests/test_agent.py
[orchestrator] 14:32:30 agent completed
```

**Learnings** (what agents learned):

```bash
cat LEARNINGS.md
```

Check the "Run Log" section at the bottom for session summaries.

---

## File Reference

```
your-project/
|
+-- .claude/
|   +-- agents/                      <-- Agent definitions (1 file per agent)
|   |   +-- orchestrator.md          <-- Routes tasks, never edits code
|   |   +-- builder.md               <-- Writes and fixes code
|   |   +-- reviewer.md              <-- Reviews code, can fix issues
|   |   +-- tester.md                <-- Runs tests, reports failures
|   |   +-- researcher.md            <-- Researches solutions (read-only)
|   |   +-- documenter.md            <-- Writes documentation
|   |   +-- review-team-coordinator.md
|   |   +-- feature-team-coordinator.md
|   |   +-- hypothesis-team-coordinator.md
|   |   +-- research-swarm-coordinator.md
|   |   +-- plan-execute-coordinator.md
|   |   +-- prd-team-coordinator.md
|   |   +-- skill-builder.md         <-- Creates/modifies skills
|   |   +-- system-architect.md      <-- Creates agents/teams/skills
|   |   +-- requirements-extractor.md
|   |   +-- technical-researcher.md
|   |   +-- architecture-designer.md
|   |   +-- task-decomposer.md
|   |   +-- risk-assessor.md
|   |
|   +-- skills/                      <-- Shared knowledge (progressive disclosure)
|   |   +-- coding-conventions/      <-- Code style, naming, imports
|   |   +-- team-coordination/       <-- Multi-agent protocols
|   |   +-- security-standards/      <-- OWASP-adapted security checks
|   |   +-- research-patterns/       <-- Research methodology
|   |
|   +-- rules/                         <-- Modular path-scoped rules (9 files)
|   |   +-- mandatory-practices.md     <-- 6 NON-NEGOTIABLE practices
|   |   +-- coding-principles.md       <-- Type safety, KISS, YAGNI
|   |   +-- common-pitfalls.md         <-- Critical mistakes to avoid
|   |   +-- testing-patterns.md        <-- Test runner patterns, mocks
|   |   +-- agent-system.md            <-- Routing, agent table, teams
|   |   +-- skill-system.md            <-- Progressive disclosure, SKILL.md format
|   |   +-- configuration.md           <-- Environment vars, settings
|   |   +-- documentation-style.md     <-- Docstring format
|   |   +-- security.md               <-- Path traversal, secrets, validation
|   |
|   +-- settings.json                <-- MCP servers + custom instructions
|
+-- team-registry/                   <-- Team definitions
|   +-- teams.md                     <-- Master registry of all teams
|   +-- parallel-review-team.md
|   +-- cross-layer-feature-team.md
|   +-- competing-hypotheses-team.md
|   +-- research-swarm-team.md
|   +-- plan-then-execute-team.md
|   +-- prd-decomposition-team.md
|   +-- run-logs/                    <-- Coordinator session logs
|
+-- reports/                         <-- Agent output
|   +-- .pipeline-log                <-- Hook output (what happened when)
|   +-- prd/                         <-- PRD decomposition output
|   +-- review-*.md                  <-- Code review reports
|
+-- LEARNINGS.md                     <-- Shared memory across sessions
+-- CLAUDE.md                        <-- Project instructions + agent routing
+-- CLAUDE.local.md                  <-- Personal preferences (gitignored)
```

### What Each Directory Does

| Directory | Purpose | Who writes to it |
|-----------|---------|-----------------|
| `.claude/agents/` | Agent behavior definitions | system-architect |
| `.claude/skills/` | Shared knowledge loaded on demand | skill-builder, system-architect |
| `.claude/rules/` | Path-scoped rules loaded contextually | system-architect, setup script |
| `team-registry/` | Team composition and execution patterns | orchestrator, coordinators |
| `reports/` | Agent output: reviews, PRDs, pipeline logs | all agents |
| `LEARNINGS.md` | Persistent memory across sessions | all agents (append-only) |

---

## Cheat Sheet

```
+====================================================================+
|              AGENT TEAM SYSTEM -- QUICK REFERENCE                  |
+====================================================================+
|                                                                    |
|  INSTALL                                                           |
|  --------                                                          |
|  Lite (3 agents):  "Build the lite agent team from                 |
|                     agent-team-build-lite.md"                      |
|  Full (19 agents): "Build the full agent team from                 |
|                     agent-team-build-greenfield.md"                |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  WHAT TO SAY             -->  WHO HANDLES IT                       |
|  ------------------          -----------------                     |
|  "build/add/create X"    -->  builder                              |
|  "fix/debug X"           -->  builder (simple) or hypothesis team  |
|  "test/verify X"         -->  tester                               |
|  "review/audit X"        -->  review team                          |
|  "research/compare X"    -->  research swarm                       |
|  "plan/design/PRD X"     -->  PRD team                             |
|  "document/explain X"    -->  documenter                           |
|  "refactor/migrate X"    -->  plan-execute team                    |
|  "create agent/skill"    -->  system-architect                     |
|  "assess risk of X"      -->  risk-assessor                        |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  AGENT MODELS                                                      |
|  ------------                                                      |
|  opus   = orchestrator, system-architect, architecture-designer    |
|  sonnet = everyone else (builder, tester, reviewer, etc.)          |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  WHAT AGENTS DO AUTOMATICALLY (you do not ask for these)           |
|  -------------------------------------------------------           |
|  1. Read your codebase before writing (grep local first)           |
|  2. Search GitHub for proven patterns (grep-mcp)                   |
|  3. Check for errors after every edit (LSP diagnostics)            |
|  4. Plan before making changes                                     |
|  5. Read and write to LEARNINGS.md                                 |
|  6. Track all work via task status                                 |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  CHECK WHAT HAPPENED                                               |
|  -------------------                                               |
|  Pipeline log:   cat reports/.pipeline-log                         |
|  Learnings:      cat LEARNINGS.md                                  |
|  Team registry:  cat team-registry/teams.md                        |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  KEY FILES                                                         |
|  ---------                                                         |
|  Agent definitions:   .claude/agents/*.md                          |
|  Skills:              .claude/skills/*/SKILL.md                    |
|  Rules (modular):     .claude/rules/*.md                           |
|  Personal prefs:      CLAUDE.local.md                              |
|  Team definitions:    team-registry/*.md                           |
|  Shared memory:       LEARNINGS.md                                 |
|  Agent routing:       CLAUDE.md (Agent Team System section)        |
|  MCP config:          .claude/settings.json                        |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  UPGRADE PATH                                                      |
|  ------------                                                      |
|  Lite (3) --> +Review (5) --> +Research (7) --> +Coord (13) --> 19 |
|  Never modify existing agents. Only add new ones.                  |
|                                                                    |
+--------------------------------------------------------------------+
|                                                                    |
|  TROUBLESHOOTING                                                   |
|  ---------------                                                   |
|  Wrong agent?     Check trigger words in agent description YAML    |
|  Bad code style?  Check .claude/skills/coding-conventions/SKILL.md |
|  Tests failing?   "Fix the failing tests in [file]"               |
|  What happened?   cat reports/.pipeline-log                        |
|                                                                    |
+====================================================================+
```

---

*For build instructions, see `agent-team-build-lite.md` (3 agents) or `agent-team-build-greenfield.md` (19 agents). Rules architecture in `.claude/rules/`.*
