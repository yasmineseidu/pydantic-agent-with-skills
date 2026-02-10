# Implementation Phases

## Overview

9 phases transforming the single-process CLI skill agent into a production multi-agent platform with bulletproof memory. Each phase is additive — nothing breaks.

```
Phase 1 (DB) ──────► Phase 2 (Memory) ──────► Phase 7 (Collaboration)
    │                    │                          │
    │                    ├──► Phase 3 (Redis) ──► Phase 5 (SSE/WS)
    │                    │                          │
    └────────────────────┴──► Phase 4 (API) ──► Phase 6 (Background)
                                  │                    │
                                  └────────────────────┴──► Phase 8 (Docker)
                                                                │
                                                                └──► Phase 9 (Integrations)
```

## Phase Summary

| Phase | Name | Week | Prerequisites | Tables | Key Deliverable |
|-------|------|------|---------------|--------|-----------------|
| **1** | [Database Foundation](phase-01-database-foundation.md) | 1 | — | 9 | ORM models, migrations, repositories |
| **2** | [Bulletproof Memory](phase-02-bulletproof-memory.md) | 2 | Phase 1 | 0 (uses P1) | 5-signal retrieval, 7 memory types, compaction shield |
| **3** | [Redis Caching](phase-03-redis-caching.md) | 2-3 | Phase 2 | 0 | Hot cache, working memory, rate limiter |
| **4** | [Auth + API](phase-04-auth-api.md) | 3 | Phase 1, 2 | 4 | FastAPI, JWT/API keys, agent CRUD, chat |
| **5** | [SSE Streaming](phase-05-sse-streaming.md) | 3-4 | Phase 4 | 0 | Pydantic AI UIAdapter SSE, WebSocket |
| **6** | [Background Processing](phase-06-background-processing.md) | 4 | Phase 4 | 1 | Celery workers, consolidation, scheduling |
| **7** | [Agent Collaboration + MoE](phase-07-agent-collaboration.md) | 5 | Phase 4 | 7 | Expert Gate, task delegation, reports, collaboration sessions |
| **8** | [Docker + Deployment](phase-08-docker-deployment.md) | 5-6 | Phase 6 | 0 | Dockerfiles, compose, CI/CD, Railway/Render |
| **9** | [Platform Integrations](phase-09-platform-integrations.md) | 6 | Phase 8 | 2 | Telegram, Slack, webhook adapters |
| | | | **Total** | **23** | |

## Table Count by Phase

```
Phase 1:  user, team, team_membership, agent, conversation,
          message, memory, memory_log, memory_tag              = 9
Phase 4:  api_key, refresh_token, usage_log, audit_log         = 4
Phase 6:  scheduled_job                                         = 1
Phase 7:  conversation_participant, agent_handoff,
          routing_decision_log, agent_task, agent_message,
          collaboration_session, collaboration_participant       = 7
Phase 9:  platform_connection, webhook_delivery_log             = 2
                                                         Total = 23
```

Complete SQL: [`plan/sql/schema.sql`](../sql/schema.sql)

## Parallel Execution Opportunities

These phases can overlap (developed simultaneously):

| Pair | Why |
|------|-----|
| Phase 2 + Phase 3 | Memory core + Redis cache are complementary |
| Phase 5 + Phase 6 | SSE streaming + background workers are independent |
| Phase 7 + Phase 8 | Agent collaboration + Docker are independent |

## Critical Constraint (Every Phase)

After EVERY phase, these MUST pass:

```bash
python -m src.cli                        # CLI still works
.venv/bin/python -m pytest tests/ -v     # All tests pass
ruff check src/ tests/                   # Lint clean
mypy src/                                # Types pass
```

## New Directories by Phase

```
Phase 1:  src/db/          src/models/
Phase 2:  src/memory/
Phase 3:  src/cache/
Phase 4:  src/auth/        api/
Phase 6:  workers/
Phase 7:  (extends api/routers/ and src/memory/)
Phase 8:  docker/          deploy/         .github/workflows/
Phase 9:  integrations/
```

## Risk Cutoff

If timeline slips, phases can be cut in this order (least to most critical):

1. Phase 9 (Integrations) — cut first, add later
2. Phase 7 (Collaboration) — nice-to-have, agents work fine solo
3. Phase 5 WebSocket (keep SSE, cut WS)
4. Phase 8 partial (keep Docker, cut Railway/Render configs)

**Never cut**: Phases 1, 2, 4 (core platform), Phase 8 Docker (needed for deployment)
