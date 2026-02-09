---
paths: [".claude/agents/**", "team-registry/**"]
---

# Agent Team System

This is an existing codebase. Agents build AROUND existing code. Never modify existing patterns without explicit instruction.

## Task Routing

| Request Pattern | Route To | Type |
|----------------|----------|------|
| "build/implement/add [simple feature]" | `builder` | Agent |
| "build/implement [complex feature]" | `feature-team-coordinator` | Team |
| "review/check/audit [code]" | `review-team-coordinator` | Team |
| "test/verify [functionality]" | `tester` | Agent |
| "research/find/explore [topic]" | `research-swarm-coordinator` | Team |
| "plan/design/break down/decompose/PRD/spec/architect" | `prd-team-coordinator` | Team |
| "document/explain [module]" | `documenter` | Agent |
| "debug/fix [simple error]" | `builder` | Agent |
| "debug/investigate [complex issue]" | `hypothesis-team-coordinator` | Team |
| "refactor/migrate [module]" | `plan-execute-coordinator` | Team |
| "create agent/add team/new skill/extend team" | `system-architect` | Agent |
| "create new skill" | `skill-builder` | Agent |
| "assess risk/risk analysis" | `risk-assessor` | Agent |

## Core Agents (6)

| Agent | Purpose | Model | Key Tools | Hooks |
|-------|---------|-------|-----------|-------|
| orchestrator | Routes tasks, manages workflow | opus | Task*, Read, Glob, Grep, Bash | SubagentStart/Stop, Stop |
| builder | Writes code following existing patterns | sonnet | Read, Write, Edit, MultiEdit, Bash, LSP, Glob, Grep, WebSearch, WebFetch | PostToolUse (format), Stop |
| reviewer | Code review + fix capability | sonnet | Read, Write, Edit, MultiEdit, Bash, LSP, Glob, Grep, WebSearch, WebFetch | PreToolUse (audit), PostToolUse (format), Stop |
| tester | Runs tests, reports failures | sonnet | Read, Bash, LSP, Glob, Grep, TaskUpdate | Stop |
| researcher | Researches solutions and packages | sonnet | Read, Glob, Grep, Bash, WebSearch, WebFetch | Stop |
| documenter | Documentation and reference files | sonnet | Read, Write, Edit, Glob, Grep | PostToolUse, Stop |

## Team Coordinators (6)

All share: disallowedTools [Edit, MultiEdit, Write], hooks [SubagentStart/Stop, Stop], skills [team-coordination, coding-conventions]

| Coordinator | Team | Purpose | Team Def |
|-------------|------|---------|----------|
| review-team-coordinator | Parallel Review | Coordinates parallel code reviews | team-registry/parallel-review-team.md |
| feature-team-coordinator | Cross-Layer Feature | Coordinates cross-module feature dev | team-registry/cross-layer-feature-team.md |
| hypothesis-team-coordinator | Competing Hypotheses | Manages parallel investigation | team-registry/competing-hypotheses-team.md |
| research-swarm-coordinator | Research Swarm | Coordinates parallel research | team-registry/research-swarm-team.md |
| plan-execute-coordinator | Plan-Then-Execute | Plans then coordinates execution | team-registry/plan-then-execute-team.md |
| prd-team-coordinator | PRD Decomposition | Decomposes PRDs into tasks | team-registry/prd-decomposition-team.md |

## Specialist Agents (7)

| Agent | Team | Purpose | Model | Hooks |
|-------|------|---------|-------|-------|
| skill-builder | Feature Team | Creates/modifies skills | sonnet | PostToolUse (format), Stop |
| requirements-extractor | PRD Team | Extracts structured requirements | sonnet* | Stop |
| technical-researcher | PRD Team | Codebase + tech research | sonnet | Stop |
| architecture-designer | PRD Team | Architecture design | opus | Stop |
| task-decomposer | PRD Team | Task breakdown | sonnet* | Stop |
| risk-assessor | Standalone | Risk identification (read-only) | sonnet | Stop |
| system-architect | Standalone | Creates new agents/teams/skills | opus | PostToolUse, Stop |

*sonnet\* = default sonnet, coordinator upgrades to opus on high complexity*

## Agent Skills (Progressive Disclosure for Agents)

| Skill | Location | Used By |
|-------|----------|---------|
| coding-conventions | `.claude/skills/coding-conventions/` | builder, reviewer, all code agents |
| team-coordination | `.claude/skills/team-coordination/` | all coordinators |
| security-standards | `.claude/skills/security-standards/` | reviewer, risk-assessor |
| research-patterns | `.claude/skills/research-patterns/` | researcher, technical-researcher |

## Protected Paths

- `examples/` - Reference implementation, read-only
- `.env` - Contains secrets, never commit
- `.claude/PRD.md` - Product requirements, read-only

## Retry Limits

| Operation | Max Retries | On Failure |
|-----------|-------------|------------|
| Build + Test | 3 | Escalate to orchestrator |
| Review + Fix | 5 | Escalate to orchestrator |
| Research | 2 | Report partial findings |
| Deploy check | 1 | Block and report |
