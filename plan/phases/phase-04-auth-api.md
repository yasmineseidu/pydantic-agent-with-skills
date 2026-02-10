# Phase 4: Auth + API Foundation

> **Timeline**: Week 3 | **Prerequisites**: Phase 1 (DB), Phase 2 (Memory), Phase 3 (Redis) | **Status**: Not Started

## Goal

Build the FastAPI application with JWT + API key authentication, agent CRUD, and non-streaming chat endpoint. This phase delivers the full REST API layer enabling programmatic access to named agents, memories, conversations, and teams.

## Dependencies (Install)

```toml
[project]
dependencies = [
    # ... existing from Phases 1-3 ...
    "fastapi~=0.115.0",
    "uvicorn[standard]~=0.32.0",
    "python-jose[cryptography]~=3.3.0",
    "bcrypt~=4.2.0",
    "python-multipart~=0.0.17",       # Form data parsing
    "langfuse~=2.0.0",                # LLM observability (Section 7)
]
```

## Settings Extensions

```python
# No new settings fields in Phase 4 specifically.
# Phase 4 uses database_url (Phase 1), redis_url (Phase 3),
# and embedding fields (Phase 1) already in settings.
# JWT secret and API key config come from .env:

# Add to .env.example:
# JWT_SECRET_KEY=your-secret-key-here
# JWT_ALGORITHM=HS256
# JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
# JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
# ADMIN_EMAIL=admin@example.com
# ADMIN_PASSWORD=changeme

# These are consumed directly in src/auth/ modules via Settings,
# or as standalone env vars in the auth module configuration.
```

## New Directories & Files

```
src/auth/
    __init__.py
    password.py           # bcrypt hash/verify (min 12 rounds)
    jwt.py                # Access token (30min) + refresh token (7d)
    api_keys.py           # API key generation (prefix: ska_), validation
    permissions.py        # Team-scoped RBAC checks
    dependencies.py       # FastAPI Depends: get_current_user, require_role

api/
    __init__.py
    app.py                # FastAPI app factory + lifespan (startup/shutdown)
    dependencies.py       # DI: get_db, get_redis, get_current_user, get_agent_deps
    middleware/
        __init__.py
        error_handler.py  # Global exception -> JSON error response
        request_id.py     # X-Request-ID header for tracing
        cors.py           # CORS configuration
    routers/
        __init__.py
        health.py         # GET /health, GET /ready (DB + Redis checks)
        auth.py           # POST /v1/auth/register, /login, /refresh, /api-keys
        agents.py         # CRUD /v1/agents
        chat.py           # POST /v1/agents/{slug}/chat (non-streaming first)
        memories.py       # GET/POST /v1/memories, POST /v1/memories/search
        conversations.py  # GET /v1/conversations, GET /v1/conversations/{id}/messages
        teams.py          # CRUD /v1/teams, /v1/teams/{slug}/members
    schemas/
        __init__.py
        common.py         # PaginatedResponse[T], ErrorResponse, RequestID
        auth.py           # RegisterRequest, LoginResponse, TokenPair
        agents.py         # AgentCreate, AgentUpdate, AgentResponse
        chat.py           # ChatRequest, ChatResponse
        memories.py       # MemorySearchRequest, MemoryResponse
        conversations.py  # ConversationResponse, MessageResponse
        teams.py          # TeamCreate, TeamResponse
```

> Note: All routes prefixed with `/v1/` for API versioning from day 1.

## Database Tables Introduced

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `api_key` | id (UUID), team_id (FK), user_id (FK), name, key_hash (SHA-256), key_prefix (ska_ + first 8 chars), scopes (TEXT[]), last_used_at, expires_at, is_active | Long-lived API keys for programmatic/webhook/CI/CD access. Plaintext NEVER stored. |
| `refresh_token` | id (UUID), user_id (FK), token_hash (SHA-256), device_info, expires_at, revoked_at | Stored for revocation support. Access tokens are stateless JWT (not stored). |
| `usage_log` | id (UUID), team_id (FK), agent_id (FK), user_id (FK), conversation_id (FK), request_id, model, input_tokens, output_tokens, embedding_tokens, estimated_cost_usd (DECIMAL(10,6)), operation, metadata (JSONB) | Token usage and cost tracking per API call. Operations: 'chat', 'embedding', 'extraction', 'consolidation', 'compaction_shield', 'title_generation', 'summarization'. |
| `audit_log` | id (UUID), team_id (FK), user_id (FK), action, resource_type, resource_id, changes (JSONB), ip_address (INET), user_agent | General system audit trail for compliance. Actions: 'user.created', 'user.deleted', 'agent.created', 'agent.updated', 'agent.archived', 'team.settings_changed', 'api_key.created', 'api_key.revoked', 'data_export.requested', 'data_deletion.completed'. |

Reference: `plan/sql/schema.sql` (Phase 4 section, tables 10-13)

### Full SQL for Phase 4 Tables

```sql
-- 10. api_key
CREATE TABLE api_key (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,       -- "My CI/CD Key"
    key_hash            TEXT NOT NULL,       -- SHA-256 hash (never store plaintext)
    key_prefix          TEXT NOT NULL,       -- "ska_" + first 8 chars (for display)
    scopes              TEXT[] NOT NULL DEFAULT '{}',  -- Future: fine-grained perms
    last_used_at        TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,         -- NULL = never expires
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_api_key_hash UNIQUE (key_hash)
);

-- 11. refresh_token
CREATE TABLE refresh_token (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    token_hash          TEXT NOT NULL,       -- SHA-256 hash
    device_info         TEXT,                -- "Chrome/Mac", "API Client"
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,         -- NULL = active
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_refresh_token_hash UNIQUE (token_hash)
);

-- 12. usage_log
CREATE TABLE usage_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID REFERENCES agent(id),
    user_id             UUID REFERENCES "user"(id),
    conversation_id     UUID REFERENCES conversation(id),
    request_id          TEXT,                -- X-Request-ID for tracing
    model               TEXT NOT NULL,
    input_tokens        INT NOT NULL DEFAULT 0,
    output_tokens       INT NOT NULL DEFAULT 0,
    embedding_tokens    INT NOT NULL DEFAULT 0,
    estimated_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0,
    operation           TEXT NOT NULL DEFAULT 'chat',
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 13. audit_log
CREATE TABLE audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID REFERENCES team(id),
    user_id             UUID REFERENCES "user"(id),
    action              TEXT NOT NULL,
    resource_type       TEXT NOT NULL,       -- 'user', 'agent', 'team', 'api_key'
    resource_id         UUID,
    changes             JSONB,               -- {old: {...}, new: {...}}
    ip_address          INET,
    user_agent          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for Phase 4 tables
CREATE INDEX idx_api_key_hash ON api_key (key_hash)
    WHERE is_active = TRUE;
CREATE INDEX idx_api_key_team ON api_key (team_id);

CREATE INDEX idx_refresh_token_user ON refresh_token (user_id)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_token_expiry ON refresh_token (expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_usage_team_time ON usage_log (team_id, created_at DESC);
CREATE INDEX idx_usage_agent ON usage_log (agent_id, created_at DESC)
    WHERE agent_id IS NOT NULL;
CREATE INDEX idx_usage_conversation ON usage_log (conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE INDEX idx_audit_team ON audit_log (team_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log (resource_type, resource_id);
```

## Implementation Details

### Auth Module (`src/auth/`)

#### Password Hashing (`src/auth/password.py`)

```python
# bcrypt hash/verify (min 12 rounds)
# Security requirements:
# - Passwords: bcrypt, min 12 rounds, min 8 chars
```

#### JWT Tokens (`src/auth/jwt.py`)

```python
# Access token (30min) + refresh token (7d)
# Security requirements:
# - JWT: RS256 or HS256, short-lived access (30min), refresh (7d)
```

#### API Keys (`src/auth/api_keys.py`)

```python
# API key generation, validation
# Security requirements:
# - API keys: `ska_` prefix + 32-byte random hex, stored as SHA-256 hash
```

#### Permissions (`src/auth/permissions.py`)

```python
# Team-scoped RBAC checks
# - All endpoints team-scoped (user must be team member with sufficient role)
# - Prompt injection defense: user input is NEVER injected into system prompt directly.
#   Memory content is sanitized.
```

#### FastAPI Dependencies (`src/auth/dependencies.py`)

```python
# FastAPI Depends: get_current_user, require_role
# Used by all routers to enforce authentication and authorization
```

### API Application (`api/`)

#### App Factory + Lifespan (`api/app.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    engine = create_async_engine(settings.database_url, ...)
    redis = await create_redis_pool(settings.redis_url)
    app.state.engine = engine
    app.state.redis = redis

    yield

    # Shutdown
    await engine.dispose()
    if redis:
        await redis.close()
```

#### API Dependencies (`api/dependencies.py`)

```python
# DI: get_db, get_redis, get_current_user, get_agent_deps
# Provides dependency injection for all routers
```

### Middleware

#### Global Error Handler (`api/middleware/error_handler.py`)

```python
# Global exception -> JSON error response
# Maps internal exceptions to standard ErrorResponse format
```

#### Request ID (`api/middleware/request_id.py`)

```python
# X-Request-ID header for tracing
# Generates unique request ID if not provided by client
# Attaches to all log messages for request correlation
```

#### CORS (`api/middleware/cors.py`)

```python
# CORS configuration
# Configurable origins, methods, headers
```

### Routers

#### Health Check (`api/routers/health.py`)

```python
# GET /health -- simple liveness
# GET /ready -- DB + Redis connectivity checks
```

#### Auth Router (`api/routers/auth.py`)

```python
# POST /v1/auth/register
# POST /v1/auth/login
# POST /v1/auth/refresh
# POST /v1/auth/api-keys  (create)
# GET  /v1/auth/api-keys  (list)
# DELETE /v1/auth/api-keys/{id} (revoke)
```

#### Agents Router (`api/routers/agents.py`)

```python
# GET    /v1/agents          -- List agents for team
# POST   /v1/agents          -- Create agent
# GET    /v1/agents/{slug}   -- Get agent by slug
# PATCH  /v1/agents/{slug}   -- Update agent
# DELETE /v1/agents/{slug}   -- Archive agent (soft delete)
```

#### Chat Router (`api/routers/chat.py`)

```python
@router.post("/v1/agents/{agent_slug}/chat")
async def chat(
    agent_slug: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message to a named agent.

    Flow:
    1. Resolve agent by slug + team
    2. Load/create conversation
    3. Retrieve relevant memories
    4. Build memory-aware prompt
    5. Run agent with Pydantic AI
    6. Persist messages
    7. Trigger async memory extraction
    8. Return response
    """
```

#### Memories Router (`api/routers/memories.py`)

```python
# GET  /v1/memories                -- List memories (with filters)
# POST /v1/memories                -- Create explicit memory
# POST /v1/memories/search         -- Semantic search
# DELETE /v1/memories/{id}         -- Soft delete (moves to cold, never hard-deleted)
# POST /v1/memories/{id}/pin       -- Pin/unpin
# POST /v1/memories/{id}/correct   -- Submit correction (creates new version)
```

#### Conversations Router (`api/routers/conversations.py`)

```python
# GET /v1/conversations                    -- List conversations
# GET /v1/conversations/{id}               -- Get conversation
# GET /v1/conversations/{id}/messages      -- Get messages for conversation
# DELETE /v1/conversations/{id}            -- Close conversation
```

#### Teams Router (`api/routers/teams.py`)

```python
# GET    /v1/teams                     -- List teams for user
# POST   /v1/teams                     -- Create team
# GET    /v1/teams/{slug}              -- Get team
# PATCH  /v1/teams/{slug}              -- Update team
# GET    /v1/teams/{slug}/members      -- List members
# POST   /v1/teams/{slug}/members      -- Add member
# DELETE /v1/teams/{slug}/members/{id} -- Remove member
# GET    /v1/teams/{slug}/usage        -- Usage/cost dashboard (period param)
```

### API Schemas (`api/schemas/`)

#### Common Schemas (`api/schemas/common.py`)

```python
from pydantic import BaseModel, Generic
from typing import TypeVar, Optional

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based pagination response."""
    items: list[T]
    cursor: Optional[str] = None  # Opaque cursor for next page
    has_more: bool
    total: Optional[int] = None   # Only included if cheap to compute

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str           # Machine-readable code: "agent_not_found", "rate_limited"
    message: str         # Human-readable description
    details: Optional[dict] = None  # Additional context
    request_id: str      # For support/debugging
```

HTTP status codes:
- 400 - Validation error (bad input)
- 401 - Not authenticated
- 403 - Not authorized (wrong team/role)
- 404 - Resource not found
- 409 - Conflict (duplicate slug, etc.)
- 422 - Unprocessable (valid JSON but business logic error)
- 429 - Rate limited
- 500 - Internal error (never expose stack traces)

#### Auth Schemas (`api/schemas/auth.py`)

```python
# RegisterRequest, LoginResponse, TokenPair
```

#### Agent Schemas (`api/schemas/agents.py`)

```python
# AgentCreate, AgentUpdate, AgentResponse
```

#### Chat Schemas (`api/schemas/chat.py`)

```python
# ChatRequest, ChatResponse
```

#### Memory Schemas (`api/schemas/memories.py`)

```python
# MemorySearchRequest, MemoryResponse
```

#### Conversation Schemas (`api/schemas/conversations.py`)

```python
# ConversationResponse, MessageResponse
```

#### Team Schemas (`api/schemas/teams.py`)

```python
# TeamCreate, TeamResponse
```

### Rate Limits

| Resource | Limit | Window | Scope |
|----------|-------|--------|-------|
| Chat messages | 60 | 1 min | Per user |
| API requests (general) | 300 | 1 min | Per team |
| Memory search | 30 | 1 min | Per user |
| Auth (login/register) | 10 | 1 min | Per IP |
| Embedding generation | 100 | 1 min | Per team |

Rate limit headers on every response:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1707523200
```

### Observability (`api/middleware/observability.py`)

#### Request/Response Logging Middleware

```python
class RequestLoggingMiddleware:
    """Log every request with: method, path, status, duration_ms, request_id."""
```

#### Cost Tracker

```python
class CostTracker:
    """Track LLM token usage and estimated costs per request."""
    async def log_usage(
        self, request_id: str, model: str,
        input_tokens: int, output_tokens: int,
        embedding_tokens: int = 0,
    ) -> None:
        """Log to structured logger + accumulate in DB."""
```

#### Langfuse Integration

```python
from langfuse import Langfuse

langfuse = Langfuse()

# Per-request tracing
trace = langfuse.trace(
    name="agent_chat",
    user_id=str(current_user.id),
    metadata={"agent": agent_slug, "team": team_slug},
)

generation = trace.generation(
    name="llm_call",
    model=agent.model_name,
    usage={
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    },
)
```

### Conversation Lifecycle

```
POST /v1/agents/{slug}/chat  (conversation_id = null)
  -> Create new conversation (auto-generate title from first message via LLM)
  -> Return conversation_id in response

POST /v1/agents/{slug}/chat  (conversation_id = "abc-123")
  -> Continue existing conversation
  -> Append to message history
```

When a conversation ends:

| Trigger | Action |
|---------|--------|
| User sends no message for 30 min | Mark `status=idle`, trigger memory extraction |
| User explicitly closes (`DELETE /v1/conversations/{id}`) | Mark `status=closed`, trigger extraction |
| Message count exceeds 100 | Auto-summarize, continue with summary as context |
| API session ends (client disconnect) | Mark `status=idle` after TTL |

### Pagination Convention

All list endpoints use cursor-based pagination:

```python
# Usage:
# GET /v1/conversations?limit=20
# GET /v1/conversations?limit=20&cursor=eyJpZCI6Ii4uLiJ9
```

Default `limit=20`, max `limit=100`.

### Security Requirements (Phase 4 Specific)

- **Passwords**: bcrypt, min 12 rounds, min 8 chars
- **JWT**: RS256 or HS256, short-lived access (30min), refresh (7d)
- **API keys**: `ska_` prefix + 32-byte random hex, stored as SHA-256 hash
- **All endpoints team-scoped** (user must be team member with sufficient role)
- **Prompt injection defense**: user input is NEVER injected into system prompt directly. Memory content is sanitized.
- **Multi-tenant isolation**: Every database query includes `WHERE team_id = $current_team`. No exceptions. No admin backdoor.

### Dual Auth (ADR-4)

- **JWT**: Short-lived, stateless, good for browser/mobile clients
- **API keys**: Long-lived, good for CI/CD, webhooks, integrations
- Both are team-scoped (multi-tenant isolation)

## Tests

```
tests/test_api/
    conftest.py              # AsyncClient fixtures, test DB, test user
    test_health.py           # Health/ready endpoint tests
    test_auth.py             # Register, login, refresh, API keys
    test_agents.py           # CRUD operations
    test_chat.py             # Non-streaming chat, memory integration
    test_memories.py         # Search, create, semantic retrieval
    test_teams.py            # Team CRUD, membership, permissions
    test_conversations.py    # Conversation list, messages, close

tests/test_auth/
    test_password.py         # bcrypt hashing, verification, min rounds
    test_jwt.py              # Token generation, validation, expiry, refresh
    test_api_keys.py         # Key generation, prefix, hash storage, validation
    test_permissions.py      # RBAC: owner/admin/member/viewer permissions
```

### Key Test Scenarios

- Auth flow: register -> login -> get token -> use token on protected endpoint
- JWT access token expires after 30 min, refresh token valid for 7 days
- Refresh token can be revoked (stored token_hash checked)
- API key with `ska_` prefix validates correctly against SHA-256 hash
- Invalid/expired tokens return 401
- Wrong team role returns 403
- Agent CRUD: create, read, update, delete (archive) with team scoping
- Agent slug uniqueness enforced within team
- Chat endpoint: resolves agent, retrieves memories, builds prompt, runs agent, persists messages
- Chat with new conversation (no conversation_id) creates conversation and returns ID
- Chat with existing conversation_id appends to history
- Memory search via POST /v1/memories/search returns ranked results
- Explicit memory creation via POST /v1/memories stores with high importance
- Memory soft delete moves to cold tier (never hard-deleted)
- Team isolation: user A cannot see team B's agents/memories/conversations
- Users can only access teams they are members of
- Rate limiting returns 429 with correct headers
- Error responses follow ErrorResponse schema with request_id
- Health endpoint returns 200 with DB + Redis status
- Request ID middleware adds X-Request-ID header
- Cost tracking logs token usage to usage_log table
- CLI still works unchanged (`python -m src.cli`)
- All existing tests pass

## Acceptance Criteria

- [ ] `uvicorn api.app:create_app --factory` starts without errors
- [ ] `/health` returns 200 with DB + Redis status
- [ ] Auth flow: register -> login -> get token -> use token
- [ ] Agent CRUD: create/read/update/delete with team scoping
- [ ] Chat endpoint returns agent response with memories injected
- [ ] Memories searchable via POST /v1/memories/search
- [ ] Team isolation: users only see their team's data
- [ ] API docs accessible at /docs (OpenAPI auto-generated)
- [ ] CLI still works unchanged (`python -m src.cli`)
- [ ] All existing tests pass
- [ ] Rate limit headers present on responses
- [ ] Request ID header present on all responses
- [ ] Cost tracking logs to usage_log table

## Rollback Strategy

**Rollback Method**: Delete `api/` directory and `src/auth/` directory. No existing code is touched by Phase 4 -- all additions are in new directories.

**Database rollback**: Run `alembic downgrade` to remove the 4 Phase 4 tables (api_key, refresh_token, usage_log, audit_log). The Phase 1-3 tables remain intact.

**Detailed steps**:
1. Stop uvicorn process
2. `alembic downgrade` to the Phase 3 migration revision
3. Delete `api/` directory
4. Delete `src/auth/` directory
5. Remove Phase 4 dependencies from `pyproject.toml`
6. Verify: `python -m src.cli` still works
7. Verify: `.venv/bin/python -m pytest tests/ -v` passes

## Links to Main Plan

- Section 4 (Phase 4: Auth + API Foundation) -- primary spec
- Section 3A (Agent Identity System) -- AgentDNA model used by agent CRUD
- Section 3B (Memory Architecture) -- memory API endpoints
- Section 5 (Files Modified) -- existing files changed
- Section 7 (Observability Strategy) -- Langfuse integration, cost tracking
- Section 8 (Security Deep-Dive) -- prompt injection, multi-tenant isolation
- Section 15 (Conversation Lifecycle) -- conversation start/end/context management
- Section 16 (API Design Conventions) -- pagination, error responses, rate limits
- Section 23 (Rollback Strategy) -- Phase 4 rollback method
- ADR-3 (FastAPI over Litestar/Django) -- framework choice rationale
- ADR-4 (JWT + API Keys dual auth) -- auth architecture rationale
