# Parallel Review Team

## Purpose
Coordinate parallel code reviews across pattern compliance, security, and test coverage.

## When to Use
- Code review requested for any feature or PR
- Security audit needed
- Quality check before merge
- Post-implementation verification

## Mode
Single mode: review scope determines agent involvement (quick/standard/thorough).

## Members

| Member | Agent File | Model | Role | Output Location |
|--------|-----------|-------|------|----------------|
| Coordinator | review-team-coordinator.md | sonnet | Spawns reviewers, synthesizes reports | reports/review-{name}.md |
| Reviewer | reviewer.md | sonnet | Pattern + security review, can fix | reports/review-{name}-patterns.md |
| Tester | tester.md | sonnet | Test coverage, run tests | reports/review-{name}-tests.md |
| Researcher | researcher.md | sonnet | Architecture context (thorough only) | reports/review-{name}-research.md |

## Execution Pattern

```
1. Coordinator receives review request
2. Determines scope: quick (1 agent), standard (2), thorough (3)
3. Spawns agents in PARALLEL (read-only on source, exclusive reports)
4. Collects all reports
5. Greps for CROSS-DOMAIN and BLOCKER tags
6. Synthesizes unified review report
7. Determines outcome: APPROVE / REQUEST_CHANGES
```

**Variant**: Reviewer has Edit capability for fix-verify loop. If issues found:
```
Reviewer finds issue -> fixes it -> getDiagnostics -> ruff check -> pytest
Max 5 fix cycles before escalating
```

## File Ownership

| File Pattern | Owner |
|-------------|-------|
| Source files under review | READ-ONLY (reviewer can fix) |
| reports/review-*-patterns.md | reviewer |
| reports/review-*-tests.md | tester |
| reports/review-*-research.md | researcher |
| reports/review-{name}.md | coordinator (synthesis) |

## Communication Protocol

| Layer | Active | Notes |
|-------|--------|-------|
| Structured Outputs | Primary | Each agent writes exclusive report |
| Shared Message Log | Optional | Only if review finds cross-module issues |
| Coordinator Routing | CROSS-DOMAIN synthesis | Routes findings to correct builder |

## Done Conditions
- [ ] All spawned agents have completed
- [ ] CROSS-DOMAIN tags addressed (follow-up tasks created)
- [ ] BLOCKER tags resolved or escalated
- [ ] Unified report written
- [ ] Decision issued (APPROVE / REQUEST_CHANGES)

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
