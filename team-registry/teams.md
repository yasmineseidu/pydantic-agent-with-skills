# Team Registry

## Team 1: Core Agents (Standalone)

| Agent | Role | Model | File Ownership |
|-------|------|-------|---------------|
| orchestrator | Routes tasks, manages workflow | opus | CLAUDE.md, LEARNINGS.md, pyproject.toml |
| builder | Writes code | sonnet | src/*.py, skills/*/SKILL.md |
| reviewer | Code review | sonnet | (read-only review) |
| tester | Tests | sonnet | tests/*.py, tests/evals/* |
| researcher | Research | sonnet | (read-only research) |
| documenter | Documentation | sonnet | README.md, skills/*/references/* |

## Team 2: Parallel Review Team

| Agent | Role | Model | Hooks |
|-------|------|-------|-------|
| review-team-coordinator | Coordinates reviews | sonnet | SubagentStart/Stop, Stop |
| reviewer | Pattern + security review + fix | sonnet | PreToolUse (audit), PostToolUse (format), Stop |
| tester | Test coverage check | sonnet | Stop |

**Trigger**: "review", "check code", "audit"
**Team Definition**: team-registry/parallel-review-team.md

## Team 3: Cross-Layer Feature Team

| Agent | Role | Model | File Ownership | Hooks |
|-------|------|-------|---------------|-------|
| feature-team-coordinator | Coordinates feature dev | sonnet | .claude/team-comms/* | SubagentStart/Stop, Stop |
| builder | Core src/ changes | sonnet | src/*.py | PostToolUse (format), Stop |
| skill-builder | Skills changes | sonnet | skills/*/* | PostToolUse (format), Stop |
| tester | Test coverage | sonnet | tests/*.py (read-only) | Stop |
| reviewer | Reviews completed work | sonnet | (reports) | PreToolUse, PostToolUse, Stop |

**Trigger**: "build feature", "add feature", "implement"
**Team Definition**: team-registry/cross-layer-feature-team.md

## Team 4: Competing Hypotheses Team

| Agent | Role | Model | Hooks |
|-------|------|-------|-------|
| hypothesis-team-coordinator | Manages parallel investigations | sonnet | SubagentStart/Stop, Stop |
| researcher (x2-3) | Investigates hypotheses | sonnet | Stop |

**Trigger**: "debug complex", "compare approaches", "investigate"
**Team Definition**: team-registry/competing-hypotheses-team.md

## Team 5: Research Swarm Team

| Agent | Role | Model | Hooks |
|-------|------|-------|-------|
| research-swarm-coordinator | Coordinates research | sonnet | SubagentStart/Stop, Stop |
| researcher (x2-4) | Parallel research | sonnet | Stop |

**Trigger**: "research", "find library", "evaluate options"
**Team Definition**: team-registry/research-swarm-team.md

## Team 6: Plan-Then-Execute Team

| Agent | Role | Model | Hooks |
|-------|------|-------|-------|
| plan-execute-coordinator | Plans then coordinates | sonnet | SubagentStart/Stop, Stop |
| builder | Executes code changes | sonnet | PostToolUse (format), Stop |
| tester | Verifies each step | sonnet | Stop |
| reviewer | Final review (optional) | sonnet | PreToolUse, PostToolUse, Stop |

**Trigger**: "refactor", "migrate", "multi-step change"
**Team Definition**: team-registry/plan-then-execute-team.md

## Team 7: PRD Decomposition Team

| Agent | Role | Model | File Ownership |
|-------|------|-------|---------------|
| prd-team-coordinator | Coordinates PRD decomposition | opus | reports/prd/, reports/prd/final-prd.md |
| requirements-extractor | Extracts structured requirements | sonnet (opus on high complexity) | reports/prd/requirements.md |
| technical-researcher | Codebase + tech research | sonnet | reports/prd/technical-research.md |
| architecture-designer | Architecture design | opus | reports/prd/architecture.md |
| task-decomposer | Task breakdown | sonnet (opus on high complexity) | reports/prd/task-tree.md |

**Trigger**: "plan feature", "decompose PRD", "plan project", "break down", "spec", "design"
**Team Definition**: team-registry/prd-decomposition-team.md

## Standalone: System Architect

| Agent | Role | Model |
|-------|------|-------|
| system-architect | Creates agents/teams/skills | opus |

**Trigger**: "create agent", "new team", "new skill", "I need an agent for"

## Standalone: Risk Assessor

| Agent | Role | Model |
|-------|------|-------|
| risk-assessor | Risk identification and mitigation | sonnet |

**Trigger**: "assess risk", "risk analysis", "what could go wrong"

## File Ownership Summary

| Directory | Primary Owner | Secondary |
|-----------|--------------|-----------|
| `src/` | builder | - |
| `skills/*/SKILL.md` | skill-builder | builder |
| `skills/*/references/` | documenter | skill-builder |
| `tests/` | tester | - |
| `.claude/agents/` | system-architect | - |
| `.claude/skills/` | system-architect | - |
| `.claude/team-comms/` | coordinators (any) | - |
| `team-registry/` | orchestrator | coordinators |
| `reports/prd/requirements.md` | requirements-extractor | - |
| `reports/prd/technical-research.md` | technical-researcher | - |
| `reports/prd/architecture.md` | architecture-designer | - |
| `reports/prd/task-tree.md` | task-decomposer | - |
| `reports/prd/final-prd.md` | prd-team-coordinator | - |
| `reports/` (other) | coordinators (any) | - |
| `CLAUDE.md` | orchestrator | - |
| `LEARNINGS.md` | orchestrator | any agent (append-only) |
| `README.md` | documenter | - |
| `pyproject.toml` | orchestrator | - |

## Protected Paths (ALL AGENTS)

- `examples/` - Reference only, DO NOT MODIFY
- `.env` - Contains secrets, DO NOT COMMIT
- `.claude/PRD.md` - Product requirements, read-only
