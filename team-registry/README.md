# Team Registry

Team definitions and run logs for the persistent agent teams system.

## Structure

```
team-registry/
  README.md                          # This file
  teams.md                           # Master registry of all teams
  prd-decomposition-team.md          # PRD decomposition team definition
  parallel-review-team.md            # Parallel review team definition
  cross-layer-feature-team.md        # Cross-layer feature team definition
  competing-hypotheses-team.md       # Competing hypotheses team definition
  research-swarm-team.md             # Research swarm team definition
  plan-then-execute-team.md          # Plan-then-execute team definition
  run-logs/                          # Run logs from team executions
```

## Team Definition Format

Each team definition file contains:
- **Purpose**: What the team does
- **When to Use**: Trigger conditions
- **Members**: Agent files, models, roles, output locations
- **Execution Pattern**: How the team operates
- **File Ownership**: Who writes what
- **Communication Protocol**: Which layers are active
- **Done Conditions**: When the team's work is complete
- **What Worked / What Didn't Work**: Updated after each run

## Run Logs

After each team execution, the coordinator writes a run log to:
```
team-registry/run-logs/YYYY-MM-DD-{team}-{feature-name}.md
```

Run logs include: feature name, mode, phases completed, what worked, what didn't, total tasks, dependency depth.

## Adding a New Team

1. Create team definition file in `team-registry/`
2. Add team to `teams.md` master registry
3. Create coordinator agent in `.claude/agents/`
4. Add routing entry to `CLAUDE.md`
5. Update orchestrator routing table
