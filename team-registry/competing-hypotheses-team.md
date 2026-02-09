# Competing Hypotheses Team

## Purpose
Investigate complex problems by testing multiple hypotheses in parallel.

## When to Use
- Bug with unclear root cause (multiple possible causes)
- Architecture decision with multiple valid approaches
- Performance issue with several optimization candidates
- Feature that could be implemented multiple ways

## Mode
Single mode: parallel investigation with converging diagnosis.

## Members

| Member | Agent File | Model | Role | Output Location |
|--------|-----------|-------|------|----------------|
| Coordinator | hypothesis-team-coordinator.md | sonnet | Formulates hypotheses, spawns investigators, compares | reports/hypothesis-{name}.md |
| Investigator A | researcher.md (or builder.md) | sonnet | Investigates Hypothesis A | reports/hypothesis-{name}-a.md |
| Investigator B | researcher.md (or builder.md) | sonnet | Investigates Hypothesis B | reports/hypothesis-{name}-b.md |
| Investigator C | researcher.md (or builder.md) | sonnet | Investigates Hypothesis C (optional) | reports/hypothesis-{name}-c.md |

**Note**: Uses the same `researcher.md` or `builder.md` agent file, reused per hypothesis
via different task descriptions. Not separate agent definitions.

## Execution Pattern

```
1. Coordinator defines problem + 2-3 hypotheses
2. Spawns investigators in PARALLEL (one per hypothesis)
3. Each investigator writes structured verdict:
   - SUPPORTED / REFUTED / INCONCLUSIVE
   - Evidence for/against with file:line references
4. Coordinator collects all reports
5. Compares evidence strength, effort, risk, pattern compliance
6. Recommends winner with reasoning
```

## File Ownership

| File Pattern | Owner |
|-------------|-------|
| Source files under investigation | READ-ONLY (investigators don't modify) |
| reports/hypothesis-{name}-{letter}.md | respective investigator |
| reports/hypothesis-{name}.md | coordinator (synthesis) |

## Communication Protocol

| Layer | Active | Notes |
|-------|--------|-------|
| Structured Outputs | Primary | Each investigator writes exclusive report |
| Shared Message Log | Optional | Only for complex cross-module debugging |
| Coordinator Routing | Converging diagnosis | Synthesizes evidence from all investigators |

## Investigation Report Format (per investigator)

```markdown
# Hypothesis Investigation Report
Status: COMPLETE | IN-PROGRESS | BLOCKED | FAILED
## Hypothesis: [name]
## Verdict: SUPPORTED | REFUTED | INCONCLUSIVE
## Evidence For
- [file:line] [evidence]
## Evidence Against
- [file:line] [evidence]
## CROSS-DOMAIN:{TARGET}: [message if relevant]
```

## Done Conditions
- [ ] All investigators have returned verdicts
- [ ] Comparison matrix completed
- [ ] Winner selected with reasoning
- [ ] Action items defined for winning hypothesis
- [ ] CROSS-DOMAIN tags addressed

## Constraints
- Max 3 hypotheses (diminishing returns)
- Max 2 research attempts per hypothesis
- Prefer researcher for investigation, builder for prototyping

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
