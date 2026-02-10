# Phase 4: Auth + API Foundation -- Task Decomposition

> **Mode**: EXISTING | **Complexity Score**: 7 (Ambiguity=0, Integration=2, Novelty=1, Risk=2, Scale=2)
> **Tasks**: 35 atomic tasks | **Waves**: 9 | **Critical Path**: P4-01 -> P4-04 -> P4-08 -> P4-15 -> P4-21 -> P4-26 -> P4-30 -> P4-33 -> P4-35 (depth 9)
> **Estimated Test Count**: ~150-180 new tests | **New Files**: ~40 | **Modified Files**: 5
> **Security Note**: Auth is security-critical. All auth tasks use sonnet minimum. Architecture/permission tasks use opus.

## Integration Points (Verified via Code Read)

| Existing File | Line(s) | What Changes |
|---|---|---|
| `src/settings.py:33-107` | Settings class | Add JWT fields (jwt_secret_key, jwt_algorithm, jwt_access_token_expire_minutes, jwt_refresh_token_expire_days), admin_email, admin_password; add `enable_api` to FeatureFlags |
| `src/dependencies.py:42-77` | AgentDependencies | No changes needed -- Phase 4 creates its own `api/dependencies.py` that bridges to AgentDependencies |
| `src/db/base.py:10-42` | Base, UUIDMixin, TimestampMixin | Imported by new ORM models (no modifications) |
| `src/db/models/__init__.py:1-39` | Model exports | Add ApiKeyORM, RefreshTokenORM, UsageLogORM, AuditLogORM exports |
| `src/db/engine.py:13-48` | get_engine, get_session | Reused by api/dependencies.py (no modifications) |
| `src/db/repositories/base.py:14-103` | BaseRepository | Extended by new repositories (no modifications) |
| `src/cache/client.py` | RedisManager | Reused by FastAPI lifespan in api/app.py |
| `src/cache/rate_limiter.py:30-40` | RateLimiter | Wrapped by api/middleware rate limit middleware |
| `src/memory/retrieval.py:1-30` | MemoryRetriever | Called by chat router for memory retrieval |
| `src/memory/prompt_builder.py:14-36` | MemoryPromptBuilder | Called by chat router to build memory-aware prompt |
| `src/memory/storage.py:1-30` | MemoryExtractor | Called async after chat response for memory extraction |
| `src/agent.py:141-262` | create_skill_agent() | Called by chat router to create agent instance |
| `src/models/agent_models.py` | AgentDNA | Used by agent CRUD schemas + chat router |
| `src/models/memory_models.py` | MemoryCreate, MemoryRecord | Used by memories router |
| `src/db/models/user.py:29-38` | UserRole enum | Used by permissions.py for RBAC checks |
| `src/db/models/user.py:41-61` | UserORM.password_hash | Used by auth password module |
| `src/db/models/user.py:97-117` | TeamMembershipORM | Queried by permissions.py for team RBAC |
| `pyproject.toml:7-20` | dependencies | Add fastapi, uvicorn, python-jose, bcrypt, python-multipart, langfuse |
| `.env.example` | bottom | Add JWT_SECRET_KEY, JWT_ALGORITHM, ADMIN_EMAIL, ADMIN_PASSWORD |

## Wave Plan

```
Wave 1 (4 tasks, parallel): P4-01, P4-02, P4-03, P4-04       -- Foundation: deps, settings, ORM models, migration
Wave 2 (5 tasks, parallel): P4-05, P4-06, P4-07, P4-08, P4-09 -- Auth module: password, JWT, API keys, permissions, auth deps
Wave 3 (4 tasks, parallel): P4-10, P4-11, P4-12, P4-13        -- Auth tests
Wave 4 (4 tasks, parallel): P4-14, P4-15, P4-16, P4-17        -- API foundation: schemas, app factory, middleware, API deps
Wave 5 (4 tasks, parallel): P4-18, P4-19, P4-20, P4-21        -- Simple routers: health, auth, agents, teams
Wave 6 (3 tasks, parallel): P4-22, P4-23, P4-24               -- Complex routers: chat, memories, conversations
Wave 7 (4 tasks, parallel): P4-25, P4-26, P4-27, P4-28        -- API tests (simple routers + schemas)
Wave 8 (4 tasks, parallel): P4-29, P4-30, P4-31, P4-32        -- API tests (complex routers + integration)
Wave 9 (3 tasks, sequential): P4-33, P4-34, P4-35             -- Verification, model exports, LEARNINGS
```

## Dependency Graph

```
P4-01 (pyproject.toml) ─────────────────┐
P4-02 (settings + .env) ────────────────┤
P4-03 (ORM models) ─────────────────────┤
P4-04 (Alembic migration) ──────────────┤
                                         │
  ┌──────────────────────────────────────┘
  │
  ├─> P4-05 (password.py)      ─┐
  ├─> P4-06 (jwt.py)            ├─> P4-08 (permissions.py)
  ├─> P4-07 (api_keys.py)       │   P4-09 (auth/dependencies.py)
  │                              │
  │   P4-10 (test_password) ────┤
  │   P4-11 (test_jwt)         ├─ [Wave 3: auth tests]
  │   P4-12 (test_api_keys)    │
  │   P4-13 (test_permissions) ─┘
  │
  ├─> P4-14 (api/schemas/common.py + auth.py + agents.py + chat.py + memories.py + conversations.py + teams.py)
  ├─> P4-15 (api/app.py factory + lifespan)
  ├─> P4-16 (api/middleware/ error_handler + request_id + cors + observability)
  ├─> P4-17 (api/dependencies.py)
  │
  ├─> P4-18 (routers/health.py) ──────────┐
  ├─> P4-19 (routers/auth.py)             │
  ├─> P4-20 (routers/agents.py)           ├─> [Wave 6-8: complex routers + tests]
  ├─> P4-21 (routers/teams.py)            │
  │                                         │
  ├─> P4-22 (routers/chat.py) ────────────┤
  ├─> P4-23 (routers/memories.py)         │
  ├─> P4-24 (routers/conversations.py) ───┘
  │
  ├─> P4-25 (test_health.py)
  ├─> P4-26 (test_auth_router.py)
  ├─> P4-27 (test_agents.py)
  ├─> P4-28 (test_teams.py)
  ├─> P4-29 (test_chat.py)
  ├─> P4-30 (test_memories.py)
  ├─> P4-31 (test_conversations.py)
  ├─> P4-32 (test_api/conftest.py)  [actually Wave 4, needed by all API tests]
  │
  └─> P4-33 (full verification) ─> P4-34 (model __init__ exports) ─> P4-35 (LEARNINGS)
```

---

## Wave 1: Foundation (4 parallel tasks)

### P4-01: Add Phase 4 Dependencies to pyproject.toml

**Description**: Add FastAPI, uvicorn, python-jose, bcrypt, python-multipart, and langfuse to project dependencies. Install all packages.

**Files to modify**:
- `pyproject.toml` -- Add to `[project].dependencies`:
  - `"fastapi~=0.115.0"`
  - `"uvicorn[standard]~=0.32.0"`
  - `"python-jose[cryptography]~=3.3.0"`
  - `"bcrypt~=4.2.0"`
  - `"python-multipart~=0.0.17"`
  - `"langfuse~=2.0.0"`
- Add `"httpx>=0.27.0"` to dev dependencies for TestClient/AsyncClient.

**Commands to run**:
```bash
uv add "fastapi~=0.115.0" "uvicorn[standard]~=0.32.0" "python-jose[cryptography]~=3.3.0" "bcrypt~=4.2.0" "python-multipart~=0.0.17" "langfuse~=2.0.0"
uv add --dev "httpx>=0.27.0"
```

**Dependencies**: None (leaf task)
**Wave**: 1
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- `python -c "import fastapi; import uvicorn; import jose; import bcrypt; import langfuse"` succeeds
- `pyproject.toml` lists all 6 new packages
- Existing 531 tests still pass
- No import conflicts

---

### P4-02: Update Settings + FeatureFlags + .env.example

**Description**: Add JWT authentication fields and admin bootstrap fields to `Settings` in `src/settings.py`. Add `enable_api` flag to `FeatureFlags`. Update `.env.example` with new variables.

**Files to modify**:
- `src/settings.py` -- Add to Settings class:
  - `jwt_secret_key: Optional[str] = Field(default=None, description="Secret key for JWT signing")`
  - `jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")`
  - `jwt_access_token_expire_minutes: int = Field(default=30, ge=1, description="Access token expiry")`
  - `jwt_refresh_token_expire_days: int = Field(default=7, ge=1, description="Refresh token expiry")`
  - `admin_email: Optional[str] = Field(default=None, description="Bootstrap admin email")`
  - `admin_password: Optional[str] = Field(default=None, description="Bootstrap admin password")`
  - `cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"], description="CORS allowed origins")`
  - `langfuse_public_key: Optional[str] = Field(default=None, description="Langfuse public key")`
  - `langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret key")`
  - `langfuse_host: Optional[str] = Field(default=None, description="Langfuse host URL")`
- `src/settings.py` -- Add to FeatureFlags:
  - `enable_api: bool = Field(default=False, description="Phase 4: FastAPI REST API")`
- `.env.example` -- Add Phase 4 section with placeholder values.

**Dependencies**: None (leaf task)
**Wave**: 1
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- `Settings()` loads without JWT env vars set (all Optional/defaulted)
- `FeatureFlags` has `enable_api` defaulting to False
- `python -m src.cli` still launches (no import errors)
- `mypy src/settings.py` passes
- `ruff check src/settings.py` clean
- Existing 531 tests pass (no regressions)

---

### P4-03: Create Phase 4 ORM Models (ApiKeyORM, RefreshTokenORM, UsageLogORM, AuditLogORM)

**Description**: Create 4 new ORM models in `src/db/models/` for the Phase 4 tables. Each model inherits from `Base` and uses `UUIDMixin`. Follow existing patterns from `user.py`, `agent.py`, `conversation.py`.

**Files to create**:
- `src/db/models/auth.py` -- Contains `ApiKeyORM` and `RefreshTokenORM`.
- `src/db/models/tracking.py` -- Contains `UsageLogORM` and `AuditLogORM`.

**Model details**:

`ApiKeyORM`:
- `__tablename__ = "api_key"`
- Columns: id (UUID PK), team_id (FK team.id CASCADE), user_id (FK user.id CASCADE), name (Text), key_hash (Text, unique), key_prefix (Text), scopes (ARRAY(Text)), last_used_at (DateTime nullable), expires_at (DateTime nullable), is_active (Boolean default True), created_at (DateTime server_default now())
- Relationships: team (TeamORM), user (UserORM)

`RefreshTokenORM`:
- `__tablename__ = "refresh_token"`
- Columns: id (UUID PK), user_id (FK user.id CASCADE), token_hash (Text, unique), device_info (Text nullable), expires_at (DateTime not null), revoked_at (DateTime nullable), created_at (DateTime server_default now())
- Relationships: user (UserORM)

`UsageLogORM`:
- `__tablename__ = "usage_log"`
- Columns: id (UUID PK), team_id (FK team.id CASCADE), agent_id (FK agent.id nullable), user_id (FK user.id nullable), conversation_id (FK conversation.id nullable), request_id (Text nullable), model (Text), input_tokens (Integer default 0), output_tokens (Integer default 0), embedding_tokens (Integer default 0), estimated_cost_usd (Numeric(10,6) default 0), operation (Text default 'chat'), metadata_json (JSONB default '{}'), created_at (DateTime server_default now())
- Note: `metadata` column mapped as `metadata_json` in Python (SA reserved word pattern from Phase 1)

`AuditLogORM`:
- `__tablename__ = "audit_log"`
- Columns: id (UUID PK), team_id (FK team.id nullable), user_id (FK user.id nullable), action (Text), resource_type (Text), resource_id (UUID nullable), changes (JSONB nullable), ip_address (Text nullable -- use Text not INET for simpler mapping), user_agent (Text nullable), created_at (DateTime server_default now())

**Dependencies**: None (leaf task -- uses existing Base, UUIDMixin from src/db/base.py)
**Wave**: 1
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All 4 ORM models import cleanly: `from src.db.models.auth import ApiKeyORM, RefreshTokenORM`
- All 4 ORM models inherit from Base (for Alembic autogenerate)
- ForeignKey references match existing table names exactly
- `metadata` column mapped as `metadata_json` (SA reserved word)
- `mypy src/db/models/auth.py src/db/models/tracking.py` passes
- `ruff check src/db/models/auth.py src/db/models/tracking.py` clean
- Google-style docstrings on all classes and columns

---

### P4-04: Create Alembic Migration for Phase 4 Tables

**Description**: Create Alembic migration `002_phase4_auth_api.py` that creates the 4 new tables (api_key, refresh_token, usage_log, audit_log) with all indexes from the SQL schema.

**Files to create**:
- `src/db/migrations/versions/002_phase4_auth_api.py`

**Migration must create**:
1. `api_key` table with all columns + unique constraint on key_hash + indexes (idx_api_key_hash partial, idx_api_key_team)
2. `refresh_token` table with all columns + unique constraint on token_hash + indexes (idx_refresh_token_user partial, idx_refresh_token_expiry partial)
3. `usage_log` table with all columns + indexes (idx_usage_team_time, idx_usage_agent partial, idx_usage_conversation partial)
4. `audit_log` table with all columns + indexes (idx_audit_team, idx_audit_user, idx_audit_resource)

**Dependencies**: P4-03 (ORM models must exist for table definitions reference)
**Wave**: 1 (can start in parallel but finish after P4-03)
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- Migration file follows same pattern as `001_initial_phase1.py`
- `revision` and `down_revision` are correctly chained
- `upgrade()` creates all 4 tables with correct columns, constraints, indexes
- `downgrade()` drops all 4 tables
- All partial indexes use correct WHERE clauses
- `ruff check src/db/migrations/versions/002_phase4_auth_api.py` clean

---

## Wave 2: Auth Module (5 parallel tasks)

### P4-05: Implement Password Hashing (`src/auth/password.py`)

**Description**: Create `src/auth/` package and `password.py` with bcrypt password hashing and verification. Minimum 12 rounds, minimum 8 character passwords.

**Files to create**:
- `src/auth/__init__.py` -- Package init with exports.
- `src/auth/password.py` -- Password hashing module.

**Functions**:
```python
def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt with minimum 12 rounds.

    Args:
        plain_password: The plaintext password (min 8 chars).

    Returns:
        The bcrypt hash string.

    Raises:
        ValueError: If password is less than 8 characters.
    """

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The bcrypt hash to check against.

    Returns:
        True if the password matches, False otherwise.
    """

def validate_password_strength(password: str) -> list[str]:
    """Validate password meets minimum requirements.

    Requirements: min 8 chars.

    Args:
        password: The password to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
```

**Security requirements**:
- bcrypt rounds: 12 (use `bcrypt.gensalt(rounds=12)`)
- Minimum password length: 8 characters
- Never log plaintext passwords
- Never raise on verify (return False on any error)

**Dependencies**: P4-01 (bcrypt installed)
**Wave**: 2
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- `hash_password("testtest")` returns a bcrypt hash string starting with `$2b$12$`
- `verify_password("testtest", hash)` returns True
- `verify_password("wrong", hash)` returns False
- `hash_password("short")` raises ValueError (< 8 chars)
- `validate_password_strength("short")` returns error list
- `mypy src/auth/password.py` passes
- `ruff check src/auth/password.py` clean

---

### P4-06: Implement JWT Token Management (`src/auth/jwt.py`)

**Description**: JWT access token (30min) and refresh token (7d) generation and validation using python-jose. Reads config from Settings.

**Files to create**:
- `src/auth/jwt.py`

**Functions/Classes**:
```python
@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT token payload."""
    sub: str           # user_id as string
    team_id: str       # current team_id as string
    role: str          # UserRole value
    exp: datetime
    type: str          # "access" or "refresh"

def create_access_token(
    user_id: UUID,
    team_id: UUID,
    role: str,
    secret_key: str,
    algorithm: str = "HS256",
    expire_minutes: int = 30,
) -> str:
    """Create a short-lived JWT access token."""

def create_refresh_token(
    user_id: UUID,
    secret_key: str,
    algorithm: str = "HS256",
    expire_days: int = 7,
) -> str:
    """Create a long-lived JWT refresh token."""

def decode_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> TokenPayload:
    """Decode and validate a JWT token.

    Raises:
        ValueError: If token is invalid, expired, or malformed.
    """
```

**Dependencies**: P4-01 (python-jose installed), P4-02 (Settings with JWT fields)
**Wave**: 2
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- `create_access_token()` returns a valid JWT string
- `decode_token()` returns correct TokenPayload with all fields
- Expired token raises ValueError
- Tampered token (wrong secret) raises ValueError
- Access token has `type: "access"`, refresh token has `type: "refresh"`
- Access token expires in 30 min, refresh in 7 days
- `mypy src/auth/jwt.py` passes
- `ruff check src/auth/jwt.py` clean

---

### P4-07: Implement API Key Management (`src/auth/api_keys.py`)

**Description**: API key generation with `ska_` prefix, SHA-256 hash storage, and validation. Plaintext is NEVER stored -- only the hash.

**Files to create**:
- `src/auth/api_keys.py`

**Functions**:
```python
def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (full_key, key_prefix, key_hash):
        - full_key: "ska_" + 32-byte random hex (displayed ONCE to user)
        - key_prefix: "ska_" + first 8 chars (stored for display)
        - key_hash: SHA-256 hash of full_key (stored in DB)
    """

def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256.

    Args:
        key: The full API key string.

    Returns:
        SHA-256 hex digest.
    """

def validate_api_key_format(key: str) -> bool:
    """Check if a string looks like a valid API key format.

    Args:
        key: The key string to validate.

    Returns:
        True if key starts with 'ska_' and has correct length.
    """
```

**Security requirements**:
- Use `secrets.token_hex(32)` for random part (32 bytes = 64 hex chars)
- Full key: `ska_` + 64 hex chars = 68 chars total
- Prefix: `ska_` + first 8 hex chars = `ska_XXXXXXXX` (12 chars)
- Hash: `hashlib.sha256(key.encode()).hexdigest()`
- Never log full key values

**Dependencies**: P4-01 (stdlib only, but needs package init from P4-05)
**Wave**: 2
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- `generate_api_key()` returns tuple of (full_key, prefix, hash)
- `full_key` starts with `ska_` and is 68 chars
- `key_prefix` is first 12 chars of full_key (`ska_` + 8 hex)
- `hash_api_key(full_key) == key_hash` (deterministic)
- `validate_api_key_format("ska_" + "a"*64)` returns True
- `validate_api_key_format("bad_key")` returns False
- `mypy src/auth/api_keys.py` passes
- `ruff check src/auth/api_keys.py` clean

---

### P4-08: Implement Permissions (`src/auth/permissions.py`)

**Description**: Team-scoped RBAC permission checks. Verifies user has required role within a specific team. Uses existing `UserRole` enum (OWNER > ADMIN > MEMBER > VIEWER) and `TeamMembershipORM`.

**Files to create**:
- `src/auth/permissions.py`

**Functions/Classes**:
```python
# Role hierarchy: OWNER > ADMIN > MEMBER > VIEWER
ROLE_HIERARCHY: dict[str, int] = {
    "owner": 4,
    "admin": 3,
    "member": 2,
    "viewer": 1,
}

async def check_team_permission(
    session: AsyncSession,
    user_id: UUID,
    team_id: UUID,
    required_role: str,
) -> bool:
    """Check if user has required role (or higher) in the team.

    Args:
        session: Database session.
        user_id: The user's UUID.
        team_id: The team's UUID.
        required_role: Minimum role required (e.g. "member").

    Returns:
        True if user has sufficient permission.
    """

async def get_user_team_role(
    session: AsyncSession,
    user_id: UUID,
    team_id: UUID,
) -> Optional[str]:
    """Get the user's role in a specific team.

    Returns:
        Role string or None if not a member.
    """

async def get_user_teams(
    session: AsyncSession,
    user_id: UUID,
) -> list[tuple[UUID, str]]:
    """Get all teams and roles for a user.

    Returns:
        List of (team_id, role) tuples.
    """
```

**Dependencies**: P4-03 (ORM models), P4-05 (auth package init)
**Wave**: 2
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- `check_team_permission(session, user_id, team_id, "member")` returns True for owner/admin/member, False for viewer
- `check_team_permission(session, user_id, team_id, "admin")` returns True for owner/admin, False for member/viewer
- Non-member returns False for any role check
- `get_user_team_role()` returns correct role string
- `get_user_teams()` returns list of all team memberships
- Multi-tenant isolation: queries always include team_id filter
- `mypy src/auth/permissions.py` passes
- `ruff check src/auth/permissions.py` clean

---

### P4-09: Implement Auth Dependencies (`src/auth/dependencies.py`)

**Description**: FastAPI dependency functions for authentication. Extracts user from JWT Bearer token or API key in Authorization header. Provides `get_current_user` and `require_role` dependencies.

**Files to create**:
- `src/auth/dependencies.py`

**Functions**:
```python
async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> tuple[UserORM, UUID]:
    """Extract and validate current user from auth header.

    Supports both:
    - Bearer <jwt_token> (JWT auth)
    - ApiKey <ska_...> (API key auth)

    Returns:
        Tuple of (user, team_id) -- team_id from JWT claim or API key's team.

    Raises:
        HTTPException(401): If auth missing or invalid.
    """

def require_role(required_role: str) -> Callable:
    """Factory for role-checking dependency.

    Usage: `Depends(require_role("admin"))`

    Args:
        required_role: Minimum role required.

    Returns:
        Dependency function that raises 403 if insufficient role.
    """
```

**Note**: This module imports from `api/dependencies.py` (get_db, get_settings). It must be created after the API dependencies module but is logically part of the auth package. In practice, both can be built in Wave 2 since we can define the interfaces first and wire later in Wave 4.

**Dependencies**: P4-05 (password), P4-06 (JWT), P4-07 (API keys), P4-08 (permissions)
**Wave**: 2 (finalized in Wave 4 when api/dependencies.py exists)
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- `get_current_user` extracts user from valid JWT Bearer token
- `get_current_user` extracts user from valid ApiKey header
- Missing Authorization header raises 401
- Invalid/expired token raises 401
- Invalid API key raises 401
- `require_role("admin")` raises 403 for member/viewer
- `require_role("member")` allows member, admin, owner
- `mypy src/auth/dependencies.py` passes
- `ruff check src/auth/dependencies.py` clean

---

## Wave 3: Auth Unit Tests (4 parallel tasks)

### P4-10: Unit Tests for Password Hashing

**Description**: Comprehensive unit tests for `src/auth/password.py`.

**Files to create**:
- `tests/test_auth/__init__.py`
- `tests/test_auth/test_password.py`

**Test Scenarios** (~12-15 tests):
1. `hash_password` returns bcrypt hash starting with `$2b$12$`
2. `hash_password` with 12+ rounds (verify cost factor in hash string)
3. `verify_password` returns True for correct password
4. `verify_password` returns False for incorrect password
5. `verify_password` returns False for empty password
6. `verify_password` returns False for malformed hash (never raises)
7. `hash_password` raises ValueError for password < 8 chars
8. `hash_password` accepts exactly 8 character password
9. `hash_password` accepts very long password (72 char bcrypt limit noted)
10. `validate_password_strength` returns empty list for valid password
11. `validate_password_strength` returns errors for short password
12. Different passwords produce different hashes
13. Same password produces different hashes (salt uniqueness)

**Dependencies**: P4-05 (password module)
**Wave**: 3
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_auth/test_password.py -v`
- No real database needed
- `ruff check tests/test_auth/test_password.py` clean

---

### P4-11: Unit Tests for JWT Token Management

**Description**: Comprehensive unit tests for `src/auth/jwt.py`.

**Files to create**:
- `tests/test_auth/test_jwt.py`

**Test Scenarios** (~15-18 tests):
1. `create_access_token` returns a string with 3 dot-separated parts (JWT format)
2. `decode_token` on access token returns correct user_id in sub
3. `decode_token` on access token returns correct team_id
4. `decode_token` on access token returns correct role
5. `decode_token` on access token returns `type: "access"`
6. Access token expires after configured minutes
7. `create_refresh_token` returns valid JWT
8. `decode_token` on refresh token returns `type: "refresh"`
9. Refresh token expires after configured days
10. Expired access token raises ValueError on decode
11. Expired refresh token raises ValueError on decode
12. Token with wrong secret raises ValueError on decode
13. Malformed token string raises ValueError
14. Empty string raises ValueError
15. Token payload contains `exp` claim in the future
16. Access token with custom expire_minutes works correctly
17. Refresh token with custom expire_days works correctly

**Dependencies**: P4-06 (JWT module)
**Wave**: 3
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_auth/test_jwt.py -v`
- No real database needed
- Uses fixed secret keys for deterministic testing
- `ruff check tests/test_auth/test_jwt.py` clean

---

### P4-12: Unit Tests for API Key Management

**Description**: Comprehensive unit tests for `src/auth/api_keys.py`.

**Files to create**:
- `tests/test_auth/test_api_keys.py`

**Test Scenarios** (~10-12 tests):
1. `generate_api_key` returns tuple of 3 strings
2. Full key starts with `ska_`
3. Full key is exactly 68 characters (4 prefix + 64 hex)
4. Key prefix is first 12 characters of full key
5. Key hash is SHA-256 hex digest (64 chars)
6. `hash_api_key(full_key)` matches generated hash
7. Two consecutive `generate_api_key()` calls produce different keys
8. `validate_api_key_format` returns True for valid format
9. `validate_api_key_format` returns False for missing prefix
10. `validate_api_key_format` returns False for wrong length
11. `validate_api_key_format` returns False for empty string
12. Key hash is deterministic for same input

**Dependencies**: P4-07 (API keys module)
**Wave**: 3
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_auth/test_api_keys.py -v`
- No real database needed
- `ruff check tests/test_auth/test_api_keys.py` clean

---

### P4-13: Unit Tests for Permissions

**Description**: Comprehensive unit tests for `src/auth/permissions.py`. Uses mock database sessions.

**Files to create**:
- `tests/test_auth/test_permissions.py`
- `tests/test_auth/conftest.py` -- Shared fixtures for auth tests (mock sessions, test users).

**Test Scenarios** (~12-15 tests):
1. Owner has permission for any role requirement
2. Admin has permission for admin, member, viewer requirements
3. Admin does NOT have permission for owner requirement
4. Member has permission for member, viewer requirements
5. Member does NOT have permission for admin, owner requirements
6. Viewer has permission for viewer requirement only
7. Non-member returns False for any permission check
8. `get_user_team_role` returns correct role for team member
9. `get_user_team_role` returns None for non-member
10. `get_user_teams` returns all team memberships
11. `get_user_teams` returns empty list for user with no teams
12. Role hierarchy comparison works correctly for all combinations
13. ROLE_HIERARCHY dict has all 4 roles

**Dependencies**: P4-08 (permissions module)
**Wave**: 3
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_auth/test_permissions.py -v`
- Uses mock AsyncSession (no real database)
- `ruff check tests/test_auth/test_permissions.py` clean

---

## Wave 4: API Foundation (4 parallel tasks)

### P4-14: Create API Schemas (`api/schemas/`)

**Description**: Create all Pydantic schemas for request/response validation across all API endpoints. These are the data contracts for the REST API.

**Files to create**:
- `api/__init__.py`
- `api/schemas/__init__.py`
- `api/schemas/common.py` -- `PaginatedResponse[T]`, `ErrorResponse`, `SuccessResponse`
- `api/schemas/auth.py` -- `RegisterRequest`, `LoginRequest`, `LoginResponse`, `TokenPair`, `RefreshRequest`, `ApiKeyCreate`, `ApiKeyResponse`
- `api/schemas/agents.py` -- `AgentCreate`, `AgentUpdate`, `AgentResponse`, `AgentListResponse`
- `api/schemas/chat.py` -- `ChatRequest`, `ChatResponse`, `ChatMessage`
- `api/schemas/memories.py` -- `MemoryCreateRequest`, `MemoryResponse`, `MemorySearchRequest`, `MemorySearchResponse`
- `api/schemas/conversations.py` -- `ConversationResponse`, `MessageResponse`, `ConversationListResponse`
- `api/schemas/teams.py` -- `TeamCreate`, `TeamUpdate`, `TeamResponse`, `MemberAdd`, `MemberResponse`, `UsageSummary`

**Key design**:
- All response schemas include `id: UUID`, `created_at: datetime`
- `PaginatedResponse` is generic: `PaginatedResponse[AgentResponse]`
- `ErrorResponse` includes `error` (code), `message` (human), `details` (optional dict), `request_id` (str)
- Chat schemas: `ChatRequest` has `message: str`, `conversation_id: Optional[UUID]`, `context: Optional[dict]`
- `ChatResponse` has `response: str`, `conversation_id: UUID`, `usage: dict`, `request_id: str`
- Agent schemas map from/to `AgentDNA` Pydantic model (use existing fields)

**Dependencies**: P4-01 (fastapi installed)
**Wave**: 4
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All schema classes import cleanly
- `PaginatedResponse[AgentResponse]` is valid generic usage
- `ErrorResponse` has all required fields
- Schema validation works (instantiation with valid data succeeds, invalid data raises ValidationError)
- `mypy api/schemas/` passes
- `ruff check api/schemas/` clean
- Google-style docstrings on all classes

---

### P4-15: Create FastAPI App Factory + Lifespan (`api/app.py`)

**Description**: Create the FastAPI application factory with async lifespan for startup/shutdown. Connects to database engine, Redis, and registers all routers and middleware.

**Files to create**:
- `api/app.py`

**Key components**:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup
    settings = load_settings()
    engine = await get_engine(settings.database_url, ...)
    app.state.engine = engine
    app.state.settings = settings

    # Redis (optional)
    if settings.redis_url:
        from src.cache.client import RedisManager
        redis_manager = RedisManager(settings.redis_url, settings.redis_key_prefix)
        app.state.redis_manager = redis_manager
    else:
        app.state.redis_manager = None

    yield

    # Shutdown
    await engine.dispose()
    if app.state.redis_manager:
        await app.state.redis_manager.close()

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Skill Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add middleware (in order)
    # Register routers
    # Return app
```

**Dependencies**: P4-01 (fastapi installed), P4-02 (settings), P4-14 (schemas for error responses)
**Wave**: 4
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- `from api.app import create_app` succeeds
- `create_app()` returns a FastAPI instance
- Lifespan creates engine on startup, disposes on shutdown
- Redis connection is optional (works without REDIS_URL)
- OpenAPI docs accessible at `/docs` when running
- `mypy api/app.py` passes
- `ruff check api/app.py` clean

---

### P4-16: Create Middleware Stack (`api/middleware/`)

**Description**: Create all middleware modules: error handler, request ID, CORS config, and request logging/observability.

**Files to create**:
- `api/middleware/__init__.py`
- `api/middleware/error_handler.py` -- Global exception handler mapping exceptions to `ErrorResponse` JSON.
- `api/middleware/request_id.py` -- Generates X-Request-ID UUID4 if not provided by client, attaches to response.
- `api/middleware/cors.py` -- CORS configuration function (reads allowed origins from Settings).
- `api/middleware/observability.py` -- Request logging middleware (method, path, status, duration_ms, request_id) + `CostTracker` class for token usage logging.

**Error handler mappings**:
- `ValueError` -> 400
- `HTTPException` -> pass through
- `sqlalchemy.exc.IntegrityError` -> 409
- `Exception` -> 500 (generic, never expose stack trace)
- All errors wrapped in `ErrorResponse(error=code, message=msg, request_id=req_id)`

**CostTracker**:
```python
class CostTracker:
    """Track LLM token usage and estimated costs per request."""

    def __init__(self, session: AsyncSession) -> None: ...

    async def log_usage(
        self,
        team_id: UUID,
        agent_id: Optional[UUID],
        user_id: Optional[UUID],
        conversation_id: Optional[UUID],
        request_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        embedding_tokens: int = 0,
        operation: str = "chat",
    ) -> None:
        """Log usage to usage_log table and structured logger."""
```

**Dependencies**: P4-01 (fastapi installed), P4-03 (UsageLogORM for CostTracker)
**Wave**: 4
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- Error handler converts exceptions to JSON ErrorResponse
- Request ID middleware adds X-Request-ID header to all responses
- Request ID is UUID4 format
- CORS middleware configurable via settings
- Request logging middleware logs method, path, status, duration_ms
- CostTracker writes to usage_log table
- `mypy api/middleware/` passes
- `ruff check api/middleware/` clean

---

### P4-17: Create API Dependencies (`api/dependencies.py`)

**Description**: FastAPI dependency injection functions that bridge to existing `src/` modules. Provides database sessions, Redis, settings, and agent dependencies to routers.

**Files to create**:
- `api/dependencies.py`

**Functions**:
```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session from the app's engine.

    Uses the engine stored in app.state during lifespan startup.
    """

def get_settings(request: Request) -> Settings:
    """Get application settings from app state."""

def get_redis_manager(request: Request) -> Optional[RedisManager]:
    """Get Redis manager from app state (may be None)."""

def get_rate_limiter(request: Request) -> Optional[RateLimiter]:
    """Get rate limiter (creates from redis_manager if available)."""

async def get_agent_deps(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis_manager: Optional[RedisManager] = Depends(get_redis_manager),
) -> AgentDependencies:
    """Create fully-initialized AgentDependencies for a request.

    Bridges FastAPI DI to the existing AgentDependencies dataclass.
    Initializes memory services, embedding service, caches, etc.
    """
```

**Dependencies**: P4-02 (settings), P4-15 (app.py with app.state)
**Wave**: 4
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- `get_db` yields AsyncSession from app.state.engine
- `get_settings` returns Settings from app.state
- `get_redis_manager` returns None when Redis not configured
- `get_agent_deps` returns initialized AgentDependencies with memory services
- Session is properly closed after request (async generator pattern)
- `mypy api/dependencies.py` passes
- `ruff check api/dependencies.py` clean

---

## Wave 5: Simple Routers (4 parallel tasks)

### P4-18: Implement Health Router (`api/routers/health.py`)

**Description**: Health check and readiness endpoints. No authentication required.

**Files to create**:
- `api/routers/__init__.py`
- `api/routers/health.py`

**Endpoints**:
- `GET /health` -- Simple liveness: `{"status": "ok"}`
- `GET /ready` -- Readiness: checks DB connectivity (`SELECT 1`) and Redis ping. Returns `{"status": "ok", "database": "connected", "redis": "connected"|"unavailable"}`

**Dependencies**: P4-15 (app factory), P4-17 (API deps for get_db, get_redis)
**Wave**: 5
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- `GET /health` returns 200 `{"status": "ok"}`
- `GET /ready` returns 200 with DB and Redis status
- `GET /ready` returns 503 if DB is down
- Redis being down does NOT fail readiness (degraded mode)
- No authentication required for health endpoints
- `ruff check api/routers/health.py` clean

---

### P4-19: Implement Auth Router (`api/routers/auth.py`)

**Description**: Authentication endpoints: register, login, refresh tokens, and API key management.

**Files to create**:
- `api/routers/auth.py`

**Endpoints**:
- `POST /v1/auth/register` -- Create new user + default team. Returns TokenPair.
- `POST /v1/auth/login` -- Email + password login. Returns TokenPair.
- `POST /v1/auth/refresh` -- Refresh access token using refresh token. Returns new TokenPair.
- `POST /v1/auth/api-keys` -- Create API key (authenticated). Returns full key ONCE.
- `GET /v1/auth/api-keys` -- List API keys (authenticated). Shows prefix only.
- `DELETE /v1/auth/api-keys/{key_id}` -- Revoke API key (authenticated).

**Business logic**:
- Register: hash password, create UserORM, create default TeamORM, create TeamMembershipORM (role=owner), create RefreshTokenORM, return tokens
- Login: find user by email, verify password, create RefreshTokenORM, return tokens
- Refresh: decode refresh token, check not revoked in DB, create new token pair, revoke old refresh token
- API key create: generate key, hash, store ApiKeyORM, return full key (displayed once)
- Rate limit: 10/min per IP on register and login

**Dependencies**: P4-05-P4-09 (full auth module), P4-14 (schemas), P4-17 (API deps)
**Wave**: 5
**Agent**: builder
**Complexity**: 7/10

**Acceptance Criteria**:
- Register creates user + team + membership + returns tokens
- Login with correct credentials returns tokens
- Login with wrong password returns 401
- Login with non-existent email returns 401 (same error, no user enumeration)
- Refresh with valid refresh token returns new token pair
- Refresh with revoked token returns 401
- API key creation returns full key once
- API key list shows prefixes only (never full key)
- API key revoke sets is_active=False
- Duplicate email on register returns 409
- `ruff check api/routers/auth.py` clean

---

### P4-20: Implement Agents Router (`api/routers/agents.py`)

**Description**: CRUD operations for agents within a team. Team-scoped (multi-tenant isolation).

**Files to create**:
- `api/routers/agents.py`

**Endpoints**:
- `GET /v1/agents` -- List agents for current team. Paginated.
- `POST /v1/agents` -- Create agent (admin+ role). Validates slug uniqueness within team.
- `GET /v1/agents/{slug}` -- Get agent by slug within team.
- `PATCH /v1/agents/{slug}` -- Update agent (admin+ role). Partial update.
- `DELETE /v1/agents/{slug}` -- Archive agent (admin+ role). Soft delete (status=archived).

**Business logic**:
- All queries include `WHERE team_id = current_team_id` (multi-tenant isolation)
- Slug uniqueness enforced within team (not globally)
- Create maps AgentCreate schema -> AgentORM with team_id
- Delete sets `status = 'archived'`, does NOT hard delete
- Agent personality, model_config, memory_config stored as JSONB

**Dependencies**: P4-09 (auth deps for get_current_user), P4-14 (agent schemas), P4-17 (API deps)
**Wave**: 5
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- List agents returns only agents for current team
- Create agent with valid data returns 201 with AgentResponse
- Create agent with duplicate slug within team returns 409
- Get agent by slug returns correct agent
- Get agent from wrong team returns 404
- Update agent partially updates only provided fields
- Delete agent sets status to archived
- Viewer role cannot create/update/delete agents
- Member role can list and read, cannot create/update/delete
- Admin+ can perform all operations
- `ruff check api/routers/agents.py` clean

---

### P4-21: Implement Teams Router (`api/routers/teams.py`)

**Description**: Team CRUD, membership management, and usage dashboard.

**Files to create**:
- `api/routers/teams.py`

**Endpoints**:
- `GET /v1/teams` -- List teams for current user.
- `POST /v1/teams` -- Create team (current user becomes owner).
- `GET /v1/teams/{slug}` -- Get team details.
- `PATCH /v1/teams/{slug}` -- Update team (owner only).
- `GET /v1/teams/{slug}/members` -- List team members.
- `POST /v1/teams/{slug}/members` -- Add member (admin+ role).
- `DELETE /v1/teams/{slug}/members/{user_id}` -- Remove member (admin+ role, cannot remove owner).
- `GET /v1/teams/{slug}/usage` -- Usage/cost dashboard (aggregates from usage_log).

**Business logic**:
- Create team: new TeamORM + TeamMembershipORM (role=owner) for current user
- Slug uniqueness enforced globally
- Only owner can update team settings
- Admin+ can manage members
- Cannot remove the team owner
- Usage dashboard aggregates token counts and costs from usage_log table

**Dependencies**: P4-09 (auth deps), P4-14 (team schemas), P4-17 (API deps)
**Wave**: 5
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- List teams returns only teams the user belongs to
- Create team makes user the owner
- Team slug uniqueness enforced (409 on duplicate)
- Update team only allowed for owner
- Add member with valid user and role succeeds
- Cannot remove team owner (400 error)
- Usage dashboard returns aggregated token counts
- All queries team-scoped (multi-tenant isolation)
- `ruff check api/routers/teams.py` clean

---

## Wave 6: Complex Routers (3 parallel tasks)

### P4-22: Implement Chat Router (`api/routers/chat.py`)

**Description**: The core chat endpoint. Resolves agent, loads/creates conversation, retrieves memories, builds prompt, runs Pydantic AI agent, persists messages, triggers async memory extraction.

**Files to create**:
- `api/routers/chat.py`

**Endpoint**:
- `POST /v1/agents/{agent_slug}/chat` -- Send message to agent.

**Chat flow (8 steps)**:
1. Resolve agent by slug + team_id -> AgentORM
2. Load or create conversation (if conversation_id=null, create new ConversationORM, auto-generate title)
3. Retrieve relevant memories: `MemoryRetriever.retrieve(query=message, team_id=..., agent_id=...)`
4. Build memory-aware prompt: `MemoryPromptBuilder.build(agent_dna=..., skill_metadata=..., retrieval_result=..., conversation_summary=...)`
5. Create agent: `create_skill_agent(agent_dna=agent_dna)`
6. Run agent: `agent.run(message, deps=agent_deps)`
7. Persist messages: Create MessageORM for user input + assistant response. Update conversation (message_count, total_tokens, last_message_at).
8. Trigger async memory extraction (background): `MemoryExtractor.extract(...)` (use `asyncio.create_task`)

**Response**: `ChatResponse(response=..., conversation_id=..., usage={input_tokens, output_tokens}, request_id=...)`

**Rate limit**: 60/min per user on chat endpoint.

**Integration points** (all from existing code):
- `src/agent.py:create_skill_agent(agent_dna)` -- creates agent
- `src/memory/retrieval.py:MemoryRetriever` -- retrieves memories
- `src/memory/prompt_builder.py:MemoryPromptBuilder` -- builds prompt
- `src/memory/storage.py:MemoryExtractor` -- extracts memories async
- `src/models/agent_models.py:AgentDNA` -- agent configuration
- `api/dependencies.py:get_agent_deps` -- fully initialized deps

**Dependencies**: P4-09 (auth deps), P4-14 (chat schemas), P4-17 (API deps), P4-20 (agent router for slug resolution patterns)
**Wave**: 6
**Agent**: builder
**Complexity**: 9/10

**Acceptance Criteria**:
- Chat with valid agent slug returns response
- Chat with non-existent agent returns 404
- Chat without conversation_id creates new conversation
- Chat with conversation_id appends to existing conversation
- Messages persisted in database (user + assistant)
- Memory retrieval integrated (retriever called with correct params)
- Memory extraction triggered async after response
- Usage tracked (input/output tokens in response)
- Rate limited at 60/min per user
- Multi-tenant: cannot chat with another team's agent
- `ruff check api/routers/chat.py` clean

---

### P4-23: Implement Memories Router (`api/routers/memories.py`)

**Description**: Memory CRUD and semantic search endpoints.

**Files to create**:
- `api/routers/memories.py`

**Endpoints**:
- `GET /v1/memories` -- List memories for team (paginated, filterable by type/agent/status).
- `POST /v1/memories` -- Create explicit memory (high importance).
- `POST /v1/memories/search` -- Semantic search across memories.
- `DELETE /v1/memories/{id}` -- Soft delete (move to cold tier, never hard delete).
- `POST /v1/memories/{id}/pin` -- Pin/unpin a memory.
- `POST /v1/memories/{id}/correct` -- Submit correction (creates new version).

**Business logic**:
- All queries include `WHERE team_id = current_team_id`
- Create memory: store as MemoryORM with source='explicit', importance=8.0
- Semantic search: uses EmbeddingService + MemoryRepository.search_by_embedding()
- Soft delete: set status='archived', tier='cold'
- Pin: set is_pinned=True on MemoryORM (note: may need to add this field or use tier logic)
- Correct: create new memory version with corrected content, link to original

**Rate limits**: Memory search 30/min per user.

**Dependencies**: P4-09 (auth deps), P4-14 (memory schemas), P4-17 (API deps)
**Wave**: 6
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- List memories returns team-scoped results with pagination
- Create memory stores with explicit source and high importance
- Search returns semantically ranked results
- Soft delete moves to cold tier (never hard deletes)
- Pin/unpin toggles memory importance
- Correction creates new version linked to original
- Rate limited at 30/min per user for search
- `ruff check api/routers/memories.py` clean

---

### P4-24: Implement Conversations Router (`api/routers/conversations.py`)

**Description**: Conversation listing, retrieval, message history, and close operations.

**Files to create**:
- `api/routers/conversations.py`

**Endpoints**:
- `GET /v1/conversations` -- List conversations for team (paginated, filterable by agent/status).
- `GET /v1/conversations/{id}` -- Get conversation details.
- `GET /v1/conversations/{id}/messages` -- Get messages for conversation (paginated).
- `DELETE /v1/conversations/{id}` -- Close conversation (mark status=closed, trigger memory extraction).

**Business logic**:
- All queries include `WHERE team_id = current_team_id`
- Messages ordered by created_at ASC (chronological)
- Close conversation: set status='closed', trigger MemoryExtractor
- Conversation must belong to current team (404 if not)

**Dependencies**: P4-09 (auth deps), P4-14 (conversation schemas), P4-17 (API deps)
**Wave**: 6
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- List conversations returns team-scoped results
- Get conversation returns full details
- Get messages returns paginated chronological messages
- Close conversation marks status=closed
- Close triggers memory extraction
- Cannot access other team's conversations (404)
- `ruff check api/routers/conversations.py` clean

---

## Wave 7: API Tests -- Simple Routers (4 parallel tasks)

### P4-25: Create API Test Conftest + Health Tests

**Description**: Create the test infrastructure for API tests and write health endpoint tests.

**Files to create**:
- `tests/test_api/__init__.py`
- `tests/test_api/conftest.py` -- Shared fixtures: AsyncClient, test DB engine, test user creation, auth helpers.
- `tests/test_api/test_health.py`

**Conftest fixtures**:
```python
@pytest.fixture
async def app() -> AsyncGenerator[FastAPI, None]:
    """Create test FastAPI app with in-memory/test DB."""

@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client for testing endpoints."""

@pytest.fixture
async def db_session(app: FastAPI) -> AsyncGenerator[AsyncSession, None]:
    """Database session for test setup/assertions."""

@pytest.fixture
async def test_user(db_session: AsyncSession) -> UserORM:
    """Create a test user with hashed password."""

@pytest.fixture
async def test_team(db_session: AsyncSession, test_user: UserORM) -> TeamORM:
    """Create a test team with test_user as owner."""

@pytest.fixture
async def auth_headers(test_user: UserORM, test_team: TeamORM) -> dict[str, str]:
    """JWT auth headers for test_user."""

@pytest.fixture
async def auth_client(client: AsyncClient, auth_headers: dict) -> AsyncClient:
    """Client with auth headers pre-set."""
```

**Health test scenarios** (~6-8 tests):
1. `GET /health` returns 200 `{"status": "ok"}`
2. `GET /ready` returns 200 with database connected
3. `GET /ready` includes Redis status
4. No auth required for health endpoints
5. Health endpoint returns JSON content type
6. Ready returns structured response with all fields

**Dependencies**: P4-15 (app factory), P4-18 (health router)
**Wave**: 7
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- Conftest fixtures create working test infrastructure
- Health tests pass with `pytest tests/test_api/test_health.py -v`
- AsyncClient correctly configured for test app
- Test DB isolated from production
- `ruff check tests/test_api/` clean

---

### P4-26: API Tests for Auth Router

**Description**: Comprehensive tests for all auth endpoints.

**Files to create**:
- `tests/test_api/test_auth.py`

**Test Scenarios** (~20-25 tests):
1. Register with valid data returns 201 + token pair
2. Register with duplicate email returns 409
3. Register with short password returns 400
4. Register creates user + team + membership
5. Login with correct credentials returns token pair
6. Login with wrong password returns 401
7. Login with non-existent email returns 401 (same error message)
8. Login returns both access and refresh tokens
9. Refresh with valid refresh token returns new token pair
10. Refresh with expired token returns 401
11. Refresh with revoked token returns 401
12. Access token works on protected endpoint
13. Expired access token returns 401
14. Create API key (authenticated) returns full key
15. Create API key returns key starting with `ska_`
16. List API keys shows prefix only (no full key)
17. Revoke API key sets is_active=False
18. API key authentication works on protected endpoint
19. Revoked API key returns 401
20. Rate limiting on login (429 after 10 attempts)

**Dependencies**: P4-19 (auth router), P4-25 (conftest)
**Wave**: 7
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_auth.py -v`
- Tests cover register, login, refresh, API key CRUD
- Security edge cases tested (wrong password, expired tokens, revoked keys)
- `ruff check tests/test_api/test_auth.py` clean

---

### P4-27: API Tests for Agents Router

**Description**: Comprehensive tests for agent CRUD endpoints.

**Files to create**:
- `tests/test_api/test_agents.py`

**Test Scenarios** (~15-18 tests):
1. List agents returns empty for new team
2. Create agent returns 201 with AgentResponse
3. Create agent with duplicate slug returns 409
4. Get agent by slug returns correct data
5. Get agent from wrong team returns 404
6. Update agent partially updates fields
7. Update agent slug to existing slug returns 409
8. Delete agent sets status to archived
9. List agents excludes archived agents by default
10. Viewer cannot create agent (403)
11. Member cannot create agent (403)
12. Admin can create agent
13. Owner can create agent
14. Agent personality JSONB stored and retrieved correctly
15. Agent model_config JSONB stored and retrieved correctly
16. Pagination works (cursor-based)
17. Created agent has correct team_id

**Dependencies**: P4-20 (agents router), P4-25 (conftest)
**Wave**: 7
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_agents.py -v`
- Multi-tenant isolation verified (cross-team access fails)
- RBAC permissions verified (role-based access)
- `ruff check tests/test_api/test_agents.py` clean

---

### P4-28: API Tests for Teams Router

**Description**: Comprehensive tests for team CRUD and membership management.

**Files to create**:
- `tests/test_api/test_teams.py`

**Test Scenarios** (~18-20 tests):
1. List teams returns user's teams
2. Create team returns 201, user becomes owner
3. Create team with duplicate slug returns 409
4. Get team returns full details
5. Get team user is not member of returns 404/403
6. Update team (owner) succeeds
7. Update team (non-owner) returns 403
8. List members returns all team members with roles
9. Add member with valid user succeeds
10. Add member with admin role (by owner) succeeds
11. Non-admin cannot add members (403)
12. Remove member succeeds (admin+)
13. Cannot remove team owner (400)
14. Viewer cannot manage members (403)
15. Usage dashboard returns aggregated data
16. Usage dashboard with period filter works
17. Team settings JSONB update works
18. Newly created team has owner membership

**Dependencies**: P4-21 (teams router), P4-25 (conftest)
**Wave**: 7
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_teams.py -v`
- RBAC enforcement tested for all operations
- Multi-tenant isolation verified
- `ruff check tests/test_api/test_teams.py` clean

---

## Wave 8: API Tests -- Complex Routers (4 parallel tasks)

### P4-29: API Tests for Chat Router

**Description**: Comprehensive tests for the chat endpoint, including memory integration.

**Files to create**:
- `tests/test_api/test_chat.py`

**Test Scenarios** (~15-18 tests):
1. Chat with valid agent returns response
2. Chat with non-existent agent returns 404
3. Chat without conversation_id creates new conversation
4. Chat with conversation_id appends to existing
5. Chat response includes conversation_id
6. Chat response includes usage (input/output tokens)
7. Chat response includes request_id
8. Messages persisted in database
9. User message and assistant response both stored
10. New conversation gets auto-generated title
11. Rate limiting at 60/min (429 on excess)
12. Cannot chat with another team's agent (404)
13. Unauthenticated request returns 401
14. Chat with archived agent returns 404/400
15. Memory retrieval is called during chat (mock verify)
16. Memory extraction is triggered async (mock verify)

**Note**: Chat tests will need to mock the LLM call (Pydantic AI agent.run). Use dependency override to inject mock agent.

**Dependencies**: P4-22 (chat router), P4-25 (conftest)
**Wave**: 8
**Agent**: builder
**Complexity**: 7/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_chat.py -v`
- LLM calls are mocked (no real API calls in tests)
- Memory integration verified via mocks
- Message persistence verified in DB
- `ruff check tests/test_api/test_chat.py` clean

---

### P4-30: API Tests for Memories Router

**Description**: Comprehensive tests for memory CRUD and search endpoints.

**Files to create**:
- `tests/test_api/test_memories.py`

**Test Scenarios** (~12-15 tests):
1. List memories returns team-scoped results
2. Create memory stores with explicit source
3. Create memory has high importance (8.0)
4. Search memories returns ranked results (mock embeddings)
5. Soft delete moves to cold tier
6. Soft delete does NOT hard delete (record still exists)
7. Pin memory updates importance/pin status
8. Correction creates new version
9. Cannot access other team's memories
10. Empty search returns empty results
11. Pagination on list endpoint works
12. Rate limit on search (30/min per user)

**Dependencies**: P4-23 (memories router), P4-25 (conftest)
**Wave**: 8
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_memories.py -v`
- Embedding service mocked (no real API calls)
- Multi-tenant isolation verified
- `ruff check tests/test_api/test_memories.py` clean

---

### P4-31: API Tests for Conversations Router

**Description**: Comprehensive tests for conversation listing, messages, and close.

**Files to create**:
- `tests/test_api/test_conversations.py`

**Test Scenarios** (~10-12 tests):
1. List conversations returns team-scoped results
2. Get conversation returns full details
3. Get conversation from wrong team returns 404
4. Get messages returns chronological order
5. Message pagination works
6. Close conversation sets status=closed
7. Close conversation triggers memory extraction (mock verify)
8. Cannot close other team's conversation
9. List with agent filter works
10. List with status filter works
11. Closed conversation cannot be chatted in (400)

**Dependencies**: P4-24 (conversations router), P4-25 (conftest)
**Wave**: 8
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- All tests pass: `pytest tests/test_api/test_conversations.py -v`
- Multi-tenant isolation verified
- `ruff check tests/test_api/test_conversations.py` clean

---

### P4-32: Router Registration + Rate Limit Middleware Integration

**Description**: Wire all routers into the app factory. Implement rate limit middleware wrapping existing `RateLimiter` from Phase 3. Add Langfuse integration to chat router.

**Files to modify**:
- `api/app.py` -- Register all routers (health, auth, agents, teams, chat, memories, conversations). Add rate limit middleware.
- `api/middleware/rate_limit.py` (new) -- FastAPI middleware that wraps `src/cache/rate_limiter.py:RateLimiter`. Adds X-RateLimit-* headers.

**Rate limit middleware**:
```python
class RateLimitMiddleware:
    """Apply rate limits per endpoint using existing RateLimiter.

    Reads rate limit config from route metadata.
    Adds headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.
    Returns 429 with ErrorResponse if exceeded.
    """
```

**Langfuse integration** (in chat router or middleware):
```python
# Per-request tracing (optional, only when langfuse configured)
if settings.langfuse_public_key:
    trace = langfuse.trace(name="agent_chat", user_id=..., metadata=...)
    generation = trace.generation(name="llm_call", model=..., usage=...)
```

**Dependencies**: P4-15 (app.py), P4-18-P4-24 (all routers), P4-16 (middleware)
**Wave**: 8
**Agent**: builder
**Complexity**: 6/10

**Acceptance Criteria**:
- All routers registered and accessible
- Rate limit middleware adds X-RateLimit-* headers
- Rate limit returns 429 with ErrorResponse when exceeded
- Langfuse tracing works when configured (does nothing when not configured)
- `uvicorn api.app:create_app --factory` starts without errors
- OpenAPI docs show all endpoints at `/docs`
- `ruff check api/` clean

---

## Wave 9: Verification + Cleanup (3 sequential tasks)

### P4-33: Full Verification Pass

**Description**: Run the complete verification suite to confirm zero regressions and all new tests pass.

**Commands**:
```bash
.venv/bin/python -m pytest tests/ -v                    # ALL tests pass (531 existing + ~150 new)
ruff check src/ tests/ api/                              # Clean
ruff format --check src/ tests/ api/                     # Formatted
mypy src/ api/                                           # Types pass
python -m src.cli --help                                 # CLI still works
uvicorn api.app:create_app --factory --host 0.0.0.0 --port 8000 &  # API starts (manual check)
```

**Dependencies**: P4-25-P4-32 (all tests written, all routers registered)
**Wave**: 9
**Agent**: tester
**Complexity**: 3/10

**Acceptance Criteria**:
- `pytest tests/ -v` passes ALL tests (0 failures, 0 errors)
- `ruff check src/ tests/ api/` reports 0 issues
- `mypy src/ api/` reports 0 errors (or only pre-existing issues)
- CLI launches without errors: `python -m src.cli`
- Total test count: 531 + ~150-180 = ~680-710 tests

---

### P4-34: Update Model Exports + Package Inits

**Description**: Update `src/db/models/__init__.py` to export the 4 new ORM models. Ensure all `__init__.py` files have proper exports.

**Files to modify**:
- `src/db/models/__init__.py` -- Add imports and `__all__` entries for `ApiKeyORM`, `RefreshTokenORM`, `UsageLogORM`, `AuditLogORM`.
- `src/auth/__init__.py` -- Verify exports: `hash_password`, `verify_password`, `create_access_token`, `decode_token`, `generate_api_key`, `check_team_permission`.
- `api/__init__.py` -- Verify export of `create_app`.

**Dependencies**: P4-33 (verification must pass first)
**Wave**: 9
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- `from src.db.models import ApiKeyORM, RefreshTokenORM, UsageLogORM, AuditLogORM` works
- `from src.auth import hash_password, verify_password` works
- `from api.app import create_app` works
- No import cycles
- `ruff check src/db/models/__init__.py src/auth/__init__.py api/__init__.py` clean

---

### P4-35: Update LEARNINGS.md

**Description**: Write Phase 4 learnings, patterns, and gotchas to `LEARNINGS.md`.

**Learnings to add**:
```
- PATTERN: FastAPI app factory → `create_app()` with `@asynccontextmanager lifespan` for startup/shutdown
- PATTERN: FastAPI DI bridge → `api/dependencies.py:get_agent_deps()` bridges to `AgentDependencies` dataclass
- PATTERN: dual auth → Bearer JWT for browser/mobile, ApiKey for CI/CD/webhooks, both team-scoped
- PATTERN: bcrypt 12 rounds → `bcrypt.gensalt(rounds=12)`, min 8 char password
- PATTERN: API key generation → `ska_` prefix + `secrets.token_hex(32)`, store SHA-256 hash only
- PATTERN: cursor-based pagination → `PaginatedResponse[T]` generic, opaque cursor, has_more flag
- PATTERN: rate limit middleware → wraps Phase 3 `RateLimiter`, adds X-RateLimit-* headers
- PATTERN: CostTracker → logs token usage to `usage_log` table per request
- GOTCHA: SA metadata column → mapped as `metadata_json` in UsageLogORM (SA reserved word, same as Phase 1)
- GOTCHA: ip_address column → use Text not INET for simpler SA mapping
- GOTCHA: user enumeration → login returns same 401 for wrong password AND non-existent email
- GOTCHA: refresh token revocation → must check revoked_at in DB (stateful, unlike access tokens)
- GOTCHA: team owner removal → explicitly block DELETE of owner from team members
- DECISION: Phase 4 → all new code in api/ and src/auth/, no modifications to existing src/ modules
- DECISION: Langfuse → optional integration, only active when langfuse_public_key configured
```

**Dependencies**: P4-34 (exports updated)
**Wave**: 9
**Agent**: builder
**Complexity**: 1/10

**Acceptance Criteria**:
- `LEARNINGS.md` has Phase 4 section
- All patterns and gotchas documented
- No import errors after final cleanup

---

## Summary

| Wave | Tasks | Parallel | Description |
|------|-------|----------|-------------|
| 1 | P4-01, P4-02, P4-03, P4-04 | 4 | Foundation: deps, settings, ORM models, migration |
| 2 | P4-05, P4-06, P4-07, P4-08, P4-09 | 5 | Auth module: password, JWT, API keys, permissions, auth deps |
| 3 | P4-10, P4-11, P4-12, P4-13 | 4 | Auth unit tests |
| 4 | P4-14, P4-15, P4-16, P4-17 | 4 | API foundation: schemas, app factory, middleware, API deps |
| 5 | P4-18, P4-19, P4-20, P4-21 | 4 | Simple routers: health, auth, agents, teams |
| 6 | P4-22, P4-23, P4-24 | 3 | Complex routers: chat, memories, conversations |
| 7 | P4-25, P4-26, P4-27, P4-28 | 4 | API tests (simple routers) |
| 8 | P4-29, P4-30, P4-31, P4-32 | 4 | API tests (complex routers) + router registration |
| 9 | P4-33, P4-34, P4-35 | 1+1+1 seq | Verification, exports, LEARNINGS |

**Total**: 35 tasks, 9 waves, max 5 agents per wave
**Critical Path**: P4-01 -> P4-05 -> P4-09 -> P4-15 -> P4-19 -> P4-22 -> P4-25 -> P4-29 -> P4-33 (depth 9)
**Estimated New Tests**: ~150-180
**New Files**: ~40 (12 src/auth + api, 12 tests)
**Modified Files**: 5 (settings, db/models/__init__, pyproject.toml, .env.example, LEARNINGS.md)
