# Plan-Then-Execute Team

## Purpose
Plan implementation strategies then coordinate execution for refactoring, migrations, and multi-step changes.

## When to Use
- Refactoring that touches multiple files
- Adding a new module that integrates with existing code
- Migrating from one pattern to another
- Any change where getting the order wrong causes breakage
- Multi-step changes with dependencies between steps

## Mode
Two-phase: Plan (cheap, single session) then Execute (team).

## Members

| Member | Agent File | Model | Role | Output Location |
|--------|-----------|-------|------|----------------|
| Coordinator | plan-execute-coordinator.md | sonnet | Plans, then spawns executors | reports/execution-{name}.md |
| Builder | builder.md | sonnet | Executes code changes | (modifies src/ files) |
| Tester | tester.md | sonnet | Verifies each step | reports/execution-{name}-tests.md |
| Reviewer | reviewer.md | sonnet | Final review (optional) | reports/execution-{name}-review.md |

## Execution Pattern

### Phase 1: Plan (Cheap)
```
1. Coordinator scans current state (Read, Grep, Glob)
2. Maps dependencies between files
3. Creates execution plan with:
   - Prerequisites
   - Ordered steps with agent assignments
   - Parallel step identification
   - Verification criteria per step
   - Rollback instructions
4. Plan saved to reports/plan-{name}.md
```

### Phase 2: Execute (Team)
```
1. Sequential steps: spawn one agent at a time, verify before next
2. Parallel steps: spawn multiple agents (non-overlapping writes only)
3. Checkpoint after each step: pytest + ruff check
4. If step fails: retry (max 3), then rollback, then re-evaluate
5. Final verification: full test suite + lint + type check
```

## File Ownership

| File Pattern | Owner |
|-------------|-------|
| src/ files being modified | builder |
| tests/ verification | tester (read-only) |
| reports/plan-{name}.md | coordinator |
| reports/execution-{name}.md | coordinator |
| reports/execution-{name}-tests.md | tester |

## Communication Protocol

| Layer | Active | Notes |
|-------|--------|-------|
| Structured Outputs | Yes | Each agent writes step results |
| Shared Message Log | If tracks interact | Cross-track dependencies |
| Coordinator Routing | Cross-track deps | Routes between parallel tracks |

### Rollback Protocol
```
Step fails -> Document failure
  -> Retry (max 3)
    -> Fix succeeds -> Continue
    -> Fix fails -> Rollback step
      -> Re-evaluate plan
        -> Plan viable -> Continue from last good step
        -> Plan not viable -> Escalate to orchestrator
```

## Done Conditions
- [ ] All plan steps completed (or plan re-evaluated)
- [ ] `pytest tests/ -v` passes
- [ ] `ruff check src/ tests/` passes
- [ ] `mypy src/` passes
- [ ] No regressions in existing functionality
- [ ] Execution report written

## Constraints
- Plan phase should be cheap (single coordinator session, no subagents)
- Execute phase spawns agents per step
- Max 3 retries per step before rollback
- Always verify between steps

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
