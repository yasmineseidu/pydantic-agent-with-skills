# Research Swarm Team

## Purpose
Coordinate parallel research across multiple sources, topics, and domains.

## When to Use
- Evaluating multiple packages/libraries for a need
- Researching a topic across different sources
- Comparing different approaches with documentation
- Gathering information for architecture decisions
- Broad technology survey

## Mode
Single mode: parallel research with synthesis.

## Members

| Member | Agent File | Model | Role | Output Location |
|--------|-----------|-------|------|----------------|
| Coordinator | research-swarm-coordinator.md | sonnet | Decomposes query, spawns researchers, synthesizes | reports/research-{topic}.md |
| Researcher 1 | researcher.md | sonnet | Sub-query 1 (e.g., API docs) | reports/research-{topic}-1.md |
| Researcher 2 | researcher.md | sonnet | Sub-query 2 (e.g., GitHub patterns) | reports/research-{topic}-2.md |
| Researcher 3 | researcher.md | sonnet | Sub-query 3 (e.g., alternatives) | reports/research-{topic}-3.md |
| Researcher 4 | researcher.md | sonnet | Sub-query 4 (optional) | reports/research-{topic}-4.md |

**Note**: All researchers use the same `researcher.md` agent file with different task descriptions.
All researchers are denied Edit tools.

## Execution Pattern

```
1. Coordinator decomposes research question into 2-4 sub-queries
2. Assigns each sub-query to a researcher (different focus/sources)
3. Spawns researchers in PARALLEL
4. Collects all reports
5. Cross-references findings between researchers
6. Flags contradictions
7. Synthesizes unified report with recommendations
```

## File Ownership

| File Pattern | Owner |
|-------------|-------|
| All source files | READ-ONLY (researchers never modify) |
| reports/research-{topic}-{N}.md | respective researcher |
| reports/research-{topic}.md | coordinator (synthesis) |

## Communication Protocol

| Layer | Active | Notes |
|-------|--------|-------|
| Structured Outputs | Primary | Each researcher writes exclusive report |
| Shared Message Log | No | Researchers work independently |
| Coordinator Routing | Synthesis only | Combines findings, resolves contradictions |

## Research Priorities for This Project

1. **Pydantic AI patterns** (ai.pydantic.dev)
2. **Python async patterns** (docs.python.org)
3. **Package evaluation** (pypi.org, GitHub)
4. **Security best practices** (OWASP, security advisories)

## Done Conditions
- [ ] All researchers have completed
- [ ] Contradictions identified and documented
- [ ] Unified synthesis report written
- [ ] Actionable recommendations provided
- [ ] Codebase context included in findings

## Constraints
- Max 4 parallel researcher agents (linear cost scaling)
- Max 2 attempts per sub-query
- Prefer official docs over blog posts
- Always include codebase context in findings

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
