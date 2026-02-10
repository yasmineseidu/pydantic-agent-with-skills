# Phase 3: Redis + Caching Layer -- Task Decomposition

> **Mode**: EXISTING | **Complexity Score**: 4 (Ambiguity=0, Integration=1, Novelty=1, Risk=1, Scale=1)
> **Tasks**: 18 atomic tasks | **Waves**: 6 | **Critical Path**: P3-01 -> P3-03 -> P3-05 -> P3-10 -> P3-14 -> P3-17 (depth 6)
> **Estimated Test Count**: ~80-100 new tests | **New Files**: 13 | **Modified Files**: 5

## Integration Points (Verified via Code Read)

| Existing File | Line(s) | What Changes |
|---|---|---|
| `src/settings.py:32-99` | Settings class | Add `redis_url`, `redis_key_prefix`; add `enable_redis_cache` to FeatureFlags |
| `src/dependencies.py:13-63` | AgentDependencies | Add 5 Optional fields under TYPE_CHECKING: redis_manager, hot_cache, working_memory, embedding_cache, rate_limiter |
| `src/memory/retrieval.py:277-424` | MemoryRetriever | Replace in-memory `_CacheEntry` dict with `HotMemoryCache` integration at Step 2 |
| `src/memory/embedding.py:56-98` | EmbeddingService | Insert Redis L2 cache between LRU and API call in `embed_text`/`embed_batch` |
| `pyproject.toml:7-19` | dependencies | Add `redis[hiredis]~=5.2.0` and `fakeredis[lua]~=2.26.0` (dev) |
| `.env.example` | bottom | Add REDIS_URL, REDIS_KEY_PREFIX |

## Wave Plan

```
Wave 1 (4 tasks, parallel): P3-01, P3-02, P3-03, P3-04  -- Foundation + leaf types
Wave 2 (4 tasks, parallel): P3-05, P3-06, P3-07, P3-08  -- Core cache modules
Wave 3 (4 tasks, parallel): P3-09, P3-10, P3-11, P3-12  -- Unit tests for cache modules
Wave 4 (2 tasks, parallel): P3-13, P3-14                 -- Integration with existing code
Wave 5 (2 tasks, parallel): P3-15, P3-16                 -- Integration + fallback tests
Wave 6 (2 tasks, sequential): P3-17, P3-18               -- Verification + cleanup
```

## Dependency Graph

```
P3-01 (deps/settings) ─────────────┬─> P3-05 (hot_cache)   ─> P3-09 (test hot_cache)
                                    ├─> P3-06 (working_mem)  ─> P3-10 (test working_mem)
P3-02 (pyproject.toml) ────────────┤
                                    ├─> P3-07 (embed_cache)  ─> P3-11 (test embed_cache)
P3-03 (client.py) ─────────────────┤
                                    └─> P3-08 (rate_limiter) ─> P3-12 (test rate_limiter)
P3-04 (conftest + __init__)  ──────┘

P3-09 ──┐                                          P3-17 (full verification)
P3-10 ──┤                                             │
P3-11 ──┼─> P3-13 (modify retrieval.py)  ─────────────┤
P3-12 ──┤   P3-14 (modify embedding.py) ──────────────┤
        │                                              │
        └─> P3-15 (test integration)    ──────────────┤
            P3-16 (test graceful fallback) ───────────┘
                                                       │
                                                   P3-18 (LEARNINGS update)
```

---

## Wave 1: Foundation (4 parallel tasks)

### P3-01: Update Settings + Dependencies + .env.example

**Description**: Add Redis configuration fields to `Settings` and `FeatureFlags` in `src/settings.py`. Add 5 new Optional fields to `AgentDependencies` in `src/dependencies.py` under the TYPE_CHECKING block. Update `.env.example` with Redis section.

**Files to modify**:
- `src/settings.py` -- Add `redis_url: Optional[str] = Field(default=None)`, `redis_key_prefix: str = Field(default="ska:")` to Settings. Add `enable_redis_cache: bool = Field(default=False, description="Phase 3: Redis caching layer")` to FeatureFlags.
- `src/dependencies.py` -- Add TYPE_CHECKING imports for `RedisManager`, `HotMemoryCache`, `WorkingMemoryCache`, `EmbeddingCache`, `RateLimiter` from `src.cache.*`. Add 5 Optional fields to AgentDependencies: `redis_manager`, `hot_cache`, `working_memory`, `embedding_cache`, `rate_limiter`.
- `.env.example` -- Add Redis section with `REDIS_URL=` and `REDIS_KEY_PREFIX=ska:`.

**Dependencies**: None (leaf task)
**Wave**: 1
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- `Settings()` still loads without `REDIS_URL` set (Optional[str] default None)
- `FeatureFlags` has `enable_redis_cache` defaulting to False
- `AgentDependencies` has 5 new Optional fields, all default None
- `python -m src.cli` still launches (no import errors)
- `mypy src/settings.py src/dependencies.py` passes
- `ruff check src/settings.py src/dependencies.py` clean
- Existing 445 tests pass (no regressions)

---

### P3-02: Add Redis Dependencies to pyproject.toml

**Description**: Add `redis[hiredis]~=5.2.0` to project dependencies and `fakeredis[lua]~=2.26.0` to dev dependencies. Install both.

**Files to modify**:
- `pyproject.toml` -- Add `"redis[hiredis]~=5.2.0"` to `[project].dependencies`. Add `"fakeredis[lua]~=2.26.0"` to `[dependency-groups].dev` and `[project.optional-dependencies].dev`.

**Commands to run**:
```bash
uv add "redis[hiredis]~=5.2.0"
uv add --dev "fakeredis[lua]~=2.26.0"
```

**Dependencies**: None (leaf task)
**Wave**: 1
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- `redis` and `fakeredis` importable in Python: `python -c "import redis; import fakeredis"`
- `pyproject.toml` has both packages listed
- Existing 445 tests still pass

---

### P3-03: Create RedisManager Client (`src/cache/client.py`)

**Description**: Create the `src/cache/` package with `__init__.py` and `client.py`. The `RedisManager` class manages an async Redis connection pool with health checking and graceful fallback. When Redis is unavailable, `get_client()` returns None and all callers handle None gracefully.

**Files to create**:
- `src/cache/__init__.py` -- Package init, export `RedisManager`, `HotMemoryCache`, `WorkingMemoryCache`, `EmbeddingCache`, `RateLimiter` (lazy imports or explicit).
- `src/cache/client.py` -- `RedisManager` class.

**Class Signature**:
```python
class RedisManager:
    """Async Redis connection pool with graceful fallback."""

    def __init__(self, redis_url: Optional[str], key_prefix: str = "ska:") -> None: ...

    async def get_client(self) -> Optional["Redis"]: ...
        # Returns None if Redis unavailable or url is None

    @property
    def available(self) -> bool: ...
        # Health check without throwing

    @property
    def key_prefix(self) -> str: ...

    async def close(self) -> None: ...
        # Close connection pool gracefully

    async def health_check(self) -> dict[str, Any]: ...
        # Returns {"status": "ok"|"unavailable", "latency_ms": float}
```

**Key Design Decisions**:
- `redis_url=None` means "no Redis configured" -- all methods return None/False gracefully
- Use `redis.asyncio.from_url()` for pool creation
- Catch `redis.ConnectionError`, `redis.TimeoutError` on `get_client()` -- return None, log warning
- Key prefix stored as property for callers to build namespaced keys

**Dependencies**: None (leaf task -- uses stdlib types only, redis import guarded)
**Wave**: 1
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- `RedisManager(redis_url=None).available` returns False
- `await RedisManager(redis_url=None).get_client()` returns None
- `RedisManager(redis_url=None).key_prefix` returns "ska:"
- No exceptions thrown when Redis is not configured
- `mypy src/cache/client.py` passes
- `ruff check src/cache/client.py` clean
- Google-style docstrings on all public methods

---

### P3-04: Create Test Conftest + Package Init for test_cache

**Description**: Create the `tests/test_cache/` package with `__init__.py` and `conftest.py`. The conftest provides shared fixtures using `fakeredis` for async Redis testing.

**Files to create**:
- `tests/test_cache/__init__.py` -- Empty package init.
- `tests/test_cache/conftest.py` -- Shared fixtures.

**Fixtures to provide**:
```python
@pytest.fixture
async def fake_redis() -> AsyncGenerator[FakeRedis, None]:
    """Async fakeredis client for isolated testing."""

@pytest.fixture
def redis_manager(fake_redis: FakeRedis) -> RedisManager:
    """RedisManager with injected fakeredis client (bypass pool creation)."""

@pytest.fixture
def unavailable_redis_manager() -> RedisManager:
    """RedisManager configured with no Redis URL (always unavailable)."""

@pytest.fixture
def key_prefix() -> str:
    """Standard test key prefix."""
    return "test:"
```

**Dependencies**: P3-02 (needs fakeredis installed), P3-03 (needs RedisManager class)
**Wave**: 1 (can start independently since it only defines fixtures, actual tests come in Wave 3)
**Agent**: builder
**Complexity**: 2/10

**Acceptance Criteria**:
- `tests/test_cache/conftest.py` provides `fake_redis`, `redis_manager`, `unavailable_redis_manager` fixtures
- `fakeredis` correctly creates async-compatible mock Redis
- No import errors when running pytest collection: `pytest tests/test_cache/ --collect-only`
- All existing 445 tests still pass

---

## Wave 2: Core Cache Modules (4 parallel tasks)

### P3-05: Implement HotMemoryCache (`src/cache/hot_cache.py`)

**Description**: Redis ZSET-backed hot memory cache for frequently-accessed memories. Uses sorted sets where score = `final_score` from 5-signal retrieval. TTL: 15 minutes, auto-refresh on access.

**Files to create**:
- `src/cache/hot_cache.py`

**Class Signature**:
```python
class HotMemoryCache:
    """L1 hot cache for frequently-accessed memories using Redis ZSET."""

    def __init__(self, redis_manager: RedisManager) -> None: ...

    async def get_memories(
        self, agent_id: UUID, user_id: UUID, limit: int = 20
    ) -> Optional[list[ScoredMemory]]: ...
        # Returns None on cache miss or Redis unavailable

    async def warm_cache(
        self, agent_id: UUID, user_id: UUID, memories: list[ScoredMemory]
    ) -> None: ...
        # Populate hot cache with TTL 15 min

    async def invalidate(
        self, agent_id: UUID, user_id: Optional[UUID] = None
    ) -> None: ...
        # Clear hot cache for agent (all users or specific user)

    def _key(self, agent_id: UUID, user_id: UUID) -> str: ...
        # Returns "ska:hot:{agent_id}:{user_id}"
```

**Serialization**: Store `ScoredMemory` as JSON in ZSET member, score = `final_score`. Deserialize on read. Use `orjson` or `json` for fast serialization.

**Key**: `{prefix}hot:{agent_id}:{user_id}` (ZSET, TTL 15 min = 900s)

**Dependencies**: P3-03 (RedisManager)
**Wave**: 2
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- `warm_cache()` stores memories in Redis ZSET with correct scores
- `get_memories()` returns deserialized ScoredMemory list sorted by score DESC
- `get_memories()` returns None when Redis unavailable
- `invalidate()` deletes the ZSET key
- TTL set to 900 seconds on warm_cache
- `mypy src/cache/hot_cache.py` passes
- `ruff check src/cache/hot_cache.py` clean

---

### P3-06: Implement WorkingMemoryCache (`src/cache/working_memory.py`)

**Description**: Conversation-scoped working memory stored in Redis HASH. Tracks current conversation context, active skills, and scratchpad. TTL: 2 hours.

**Files to create**:
- `src/cache/working_memory.py`

**Class Signature**:
```python
class WorkingMemoryCache:
    """Manage active conversation state in Redis HASH."""

    def __init__(self, redis_manager: RedisManager) -> None: ...

    async def set_context(
        self, conversation_id: UUID, context: dict[str, Any]
    ) -> None: ...
        # Store full context as JSON in HASH field "context", TTL 2h

    async def get_context(
        self, conversation_id: UUID
    ) -> Optional[dict[str, Any]]: ...
        # Returns None on miss or Redis unavailable

    async def append_turn(
        self, conversation_id: UUID, role: str, content: str
    ) -> None: ...
        # Append turn to HASH field "turns" (JSON list), refresh TTL

    async def get_turns(
        self, conversation_id: UUID
    ) -> list[dict[str, str]]: ...
        # Returns list of {"role": ..., "content": ...} dicts

    async def set_field(
        self, conversation_id: UUID, field: str, value: Any
    ) -> None: ...
        # Set arbitrary HASH field (scratchpad, active_skills, summary)

    async def get_field(
        self, conversation_id: UUID, field: str
    ) -> Optional[Any]: ...

    async def delete(self, conversation_id: UUID) -> None: ...

    def _key(self, conversation_id: UUID) -> str: ...
        # Returns "ska:working:{conversation_id}"
```

**Key**: `{prefix}working:{conversation_id}` (HASH, TTL 7200s = 2h)

**Dependencies**: P3-03 (RedisManager)
**Wave**: 2
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- `set_context()`/`get_context()` round-trips a dict through Redis HASH
- `append_turn()` accumulates turns in a JSON list
- `get_context()` returns None when Redis unavailable
- TTL is 7200 seconds, refreshed on writes
- `delete()` removes the key
- `mypy src/cache/working_memory.py` passes
- `ruff check src/cache/working_memory.py` clean

---

### P3-07: Implement EmbeddingCache (`src/cache/embedding_cache.py`)

**Description**: Redis STRING-backed embedding cache. Supplements the Phase 2 in-memory LRU cache with persistent Redis storage. Key is SHA-256 of normalized text. TTL: 24 hours.

**Files to create**:
- `src/cache/embedding_cache.py`

**Class Signature**:
```python
class EmbeddingCache:
    """Redis-backed embedding cache with 24h TTL."""

    def __init__(self, redis_manager: RedisManager) -> None: ...

    async def get_embedding(self, text: str) -> Optional[list[float]]: ...
        # Returns None on miss or Redis unavailable

    async def store_embedding(self, text: str, embedding: list[float]) -> None: ...
        # Store as JSON string with 24h TTL

    def _cache_key(self, text: str) -> str: ...
        # Returns "ska:embed:{sha256_of_normalized_text}"

    @staticmethod
    def _normalize(text: str) -> str: ...
        # Returns text.lower().strip()
```

**Key**: `{prefix}embed:{sha256}` (STRING, TTL 86400s = 24h)

**Serialization**: Store embedding as JSON-encoded list of floats. Use `json.dumps`/`json.loads` for compatibility.

**Dependencies**: P3-03 (RedisManager)
**Wave**: 2
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- `store_embedding()`/`get_embedding()` round-trips float vectors
- Cache key is SHA-256 of lowercased, stripped text
- `get_embedding()` returns None when Redis unavailable
- TTL is 86400 seconds
- `mypy src/cache/embedding_cache.py` passes
- `ruff check src/cache/embedding_cache.py` clean

---

### P3-08: Implement RateLimiter (`src/cache/rate_limiter.py`)

**Description**: Token-bucket rate limiter using Redis STRING counters with INCR + EXPIRE. Returns a `RateLimitResult` dataclass with allowed/remaining/reset_at/limit fields.

**Files to create**:
- `src/cache/rate_limiter.py`

**Class/Type Signatures**:
```python
@dataclass(frozen=True)
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    reset_at: datetime
    limit: int

class RateLimiter:
    """Token-bucket rate limiter using Redis counters."""

    def __init__(self, redis_manager: RedisManager) -> None: ...

    async def check_rate_limit(
        self,
        team_id: UUID,
        resource: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult: ...
        # Returns RateLimitResult. When Redis unavailable: allowed=True (degraded mode, log warning)

    def _key(self, team_id: UUID, resource: str) -> str: ...
        # Returns "ska:rate:{team_id}:{resource}"
```

**Algorithm**: INCR the counter. If result == 1, set EXPIRE to window_seconds. If count > limit, deny.

**Dependencies**: P3-03 (RedisManager)
**Wave**: 2
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- `check_rate_limit()` allows requests within limit
- `check_rate_limit()` denies requests exceeding limit
- Counter resets after window expires (TTL-based)
- Returns correct `remaining` count and `reset_at` datetime
- When Redis unavailable: returns `allowed=True` (degraded), logs warning
- `mypy src/cache/rate_limiter.py` passes
- `ruff check src/cache/rate_limiter.py` clean

---

## Wave 3: Unit Tests (4 parallel tasks)

### P3-09: Unit Tests for HotMemoryCache

**Description**: Comprehensive unit tests for `HotMemoryCache` using fakeredis.

**Files to create**:
- `tests/test_cache/test_hot_cache.py`

**Test Scenarios** (~15-18 tests):
1. `warm_cache` stores memories in Redis ZSET
2. `get_memories` returns cached memories sorted by score DESC
3. `get_memories` returns None on cache miss (empty key)
4. `get_memories` respects limit parameter
5. `get_memories` returns None when Redis unavailable
6. `warm_cache` sets TTL to 900 seconds
7. `invalidate` removes all cached memories for agent+user
8. `invalidate` with user_id=None clears all users for agent (pattern delete)
9. `warm_cache` overwrites previous cache content
10. ScoredMemory serialization/deserialization round-trip preserves all fields
11. Cache key format is `{prefix}hot:{agent_id}:{user_id}`
12. Empty memory list warm_cache is a no-op

**Dependencies**: P3-04 (conftest), P3-05 (HotMemoryCache)
**Wave**: 3
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- All test scenarios pass with `pytest tests/test_cache/test_hot_cache.py -v`
- Uses fakeredis fixtures from conftest
- No real Redis required
- `ruff check tests/test_cache/test_hot_cache.py` clean

---

### P3-10: Unit Tests for WorkingMemoryCache

**Description**: Comprehensive unit tests for `WorkingMemoryCache` using fakeredis.

**Files to create**:
- `tests/test_cache/test_working_memory.py`

**Test Scenarios** (~15-18 tests):
1. `set_context`/`get_context` round-trips dict correctly
2. `get_context` returns None on cache miss
3. `get_context` returns None when Redis unavailable
4. `append_turn` adds turn to turns list
5. `append_turn` accumulates multiple turns in order
6. `get_turns` returns empty list on miss
7. `set_field`/`get_field` for arbitrary fields (scratchpad, summary)
8. `delete` removes the key entirely
9. TTL is set to 7200 seconds
10. `append_turn` refreshes TTL
11. `set_context` overwrites existing context
12. Key format is `{prefix}working:{conversation_id}`
13. Large context dict (nested, 10+ keys) round-trips correctly

**Dependencies**: P3-04 (conftest), P3-06 (WorkingMemoryCache)
**Wave**: 3
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- All test scenarios pass with `pytest tests/test_cache/test_working_memory.py -v`
- Uses fakeredis fixtures from conftest
- `ruff check tests/test_cache/test_working_memory.py` clean

---

### P3-11: Unit Tests for EmbeddingCache

**Description**: Comprehensive unit tests for `EmbeddingCache` using fakeredis.

**Files to create**:
- `tests/test_cache/test_embedding_cache.py`

**Test Scenarios** (~12-15 tests):
1. `store_embedding`/`get_embedding` round-trips float vectors
2. `get_embedding` returns None on cache miss
3. `get_embedding` returns None when Redis unavailable
4. Cache key is SHA-256 of lowercased, stripped text
5. Same text with different case/whitespace hits same cache key
6. TTL is set to 86400 seconds
7. Different texts produce different cache keys
8. 1536-dimensional vector round-trips without precision loss
9. `store_embedding` overwrites existing embedding for same text
10. Empty text still produces valid cache key

**Dependencies**: P3-04 (conftest), P3-07 (EmbeddingCache)
**Wave**: 3
**Agent**: builder
**Complexity**: 3/10

**Acceptance Criteria**:
- All test scenarios pass with `pytest tests/test_cache/test_embedding_cache.py -v`
- Uses fakeredis fixtures from conftest
- `ruff check tests/test_cache/test_embedding_cache.py` clean

---

### P3-12: Unit Tests for RateLimiter

**Description**: Comprehensive unit tests for `RateLimiter` using fakeredis.

**Files to create**:
- `tests/test_cache/test_rate_limiter.py`

**Test Scenarios** (~12-15 tests):
1. First request within limit: `allowed=True`, `remaining=limit-1`
2. Requests up to limit: all allowed, remaining decrements
3. Request exceeding limit: `allowed=False`, `remaining=0`
4. After window expires: counter resets, request allowed
5. `reset_at` is in the future and within window
6. Different resources have independent counters
7. Different team_ids have independent counters
8. Redis unavailable: returns `allowed=True` (degraded mode)
9. Key format is `{prefix}rate:{team_id}:{resource}`
10. RateLimitResult is frozen dataclass

**Dependencies**: P3-04 (conftest), P3-08 (RateLimiter)
**Wave**: 3
**Agent**: builder
**Complexity**: 4/10

**Acceptance Criteria**:
- All test scenarios pass with `pytest tests/test_cache/test_rate_limiter.py -v`
- Uses fakeredis fixtures from conftest
- `ruff check tests/test_cache/test_rate_limiter.py` clean

---

## Wave 4: Integration with Existing Code (2 parallel tasks)

### P3-13: Integrate HotMemoryCache into MemoryRetriever

**Description**: Modify `src/memory/retrieval.py` to use `HotMemoryCache` when available. The existing in-memory `_CacheEntry` dict remains as L0 (per-instance), Redis `HotMemoryCache` becomes L1.

**Files to modify**:
- `src/memory/retrieval.py` -- Add optional `hot_cache: Optional[HotMemoryCache] = None` parameter to `MemoryRetriever.__init__()`. In `retrieve()` Step 2, check `hot_cache.get_memories()` before the in-memory cache. After Step 6, call `hot_cache.warm_cache()` to populate on cache miss.

**Integration Logic**:
```
Step 2 (updated):
  a) Check in-memory _CacheEntry dict (L0, existing)
  b) If L0 miss and hot_cache available: check hot_cache.get_memories() (L1)
  c) If L1 hit: return early (populate L0 from result)
  d) If both miss: proceed to PostgreSQL (Steps 3-7)
  After Step 7: warm_cache() with results
```

**Dependencies**: P3-05 (HotMemoryCache), P3-09 (tests for hot_cache must pass first)
**Wave**: 4
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- `MemoryRetriever.__init__` accepts optional `hot_cache` parameter
- When `hot_cache=None` (default): behavior is identical to Phase 2 (no regressions)
- When `hot_cache` provided and hit: returns cached result with `cache_hit=True`
- When `hot_cache` provided and miss: falls through to PostgreSQL, then warms cache
- All existing `test_retrieval.py` tests still pass (hot_cache=None path)
- `mypy src/memory/retrieval.py` passes
- `ruff check src/memory/retrieval.py` clean

---

### P3-14: Integrate EmbeddingCache into EmbeddingService

**Description**: Modify `src/memory/embedding.py` to use `EmbeddingCache` as L2 between the in-memory LRU (L1) and the API call (L3).

**Files to modify**:
- `src/memory/embedding.py` -- Add optional `redis_cache: Optional[EmbeddingCache] = None` parameter to `EmbeddingService.__init__()`. In `embed_text()`, check Redis after LRU miss. In `embed_batch()`, check Redis for each uncached text.

**Integration Logic**:
```
embed_text():
  1. Check in-memory LRU (L1, existing)
  2. If L1 miss and redis_cache available: check redis_cache.get_embedding() (L2)
  3. If L2 hit: store in L1, return
  4. If both miss: call API (L3, existing)
  5. Store in L1 (existing) + L2 (new)

embed_batch():
  For each uncached text:
  1. Check L1 LRU (existing)
  2. Check L2 Redis (new)
  3. Remaining uncached: batch API call (existing)
  4. Store results in L1 + L2
```

**Dependencies**: P3-07 (EmbeddingCache), P3-11 (tests for embed_cache must pass first)
**Wave**: 4
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- `EmbeddingService.__init__` accepts optional `redis_cache` parameter
- When `redis_cache=None` (default): behavior identical to Phase 2 (no regressions)
- When `redis_cache` provided: checks Redis L2 on LRU miss
- On L2 hit: stores in L1, returns without API call
- On L2 miss: calls API, stores in both L1 and L2
- All existing `test_embedding.py` tests still pass (redis_cache=None path)
- `mypy src/memory/embedding.py` passes
- `ruff check src/memory/embedding.py` clean

---

## Wave 5: Integration + Fallback Tests (2 parallel tasks)

### P3-15: Integration Tests for Cache Layer

**Description**: Integration tests verifying end-to-end cache behavior across modules.

**Files to create**:
- `tests/test_cache/test_integration.py`

**Test Scenarios** (~10-12 tests):
1. RedisManager with fakeredis URL: `available` returns True, `get_client()` returns client
2. RedisManager with None URL: `available` returns False, `get_client()` returns None
3. RedisManager `health_check()` returns status dict with latency
4. HotMemoryCache -> warm -> get -> invalidate full lifecycle
5. WorkingMemoryCache -> set_context -> append_turn -> get_turns full lifecycle
6. EmbeddingCache -> store -> get -> different text miss full lifecycle
7. RateLimiter -> allow -> allow -> ... -> deny at limit -> wait -> allow (window reset)
8. All cache modules work with same RedisManager instance
9. Cache modules handle RedisManager.close() gracefully
10. `enable_redis_cache` feature flag gates initialization (when False, caches not created)

**Dependencies**: P3-09, P3-10, P3-11, P3-12 (all unit tests pass)
**Wave**: 5
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All integration tests pass with `pytest tests/test_cache/test_integration.py -v`
- Uses fakeredis, no real Redis required
- `ruff check tests/test_cache/test_integration.py` clean

---

### P3-16: Graceful Fallback Tests

**Description**: Tests verifying that ALL cache features degrade gracefully when Redis is unavailable. Each module must return safe defaults (None, True, empty list) without throwing exceptions.

**Files to create**:
- `tests/test_cache/test_graceful_fallback.py`

**Test Scenarios** (~12-15 tests):
1. HotMemoryCache: `get_memories()` returns None when Redis unavailable
2. HotMemoryCache: `warm_cache()` is silent no-op when Redis unavailable
3. HotMemoryCache: `invalidate()` is silent no-op when Redis unavailable
4. WorkingMemoryCache: `get_context()` returns None when Redis unavailable
5. WorkingMemoryCache: `set_context()` is silent no-op when Redis unavailable
6. WorkingMemoryCache: `append_turn()` is silent no-op when Redis unavailable
7. EmbeddingCache: `get_embedding()` returns None when Redis unavailable
8. EmbeddingCache: `store_embedding()` is silent no-op when Redis unavailable
9. RateLimiter: `check_rate_limit()` returns `allowed=True` when Redis unavailable
10. RateLimiter: logs warning when degraded
11. MemoryRetriever with unavailable hot_cache: falls through to PostgreSQL (no crash)
12. EmbeddingService with unavailable redis_cache: uses LRU only (no crash)
13. No exceptions propagate to caller from any cache module when Redis is down
14. CLI starts and works with `REDIS_URL` not set

**Dependencies**: P3-13, P3-14 (integration modifications complete), P3-09-P3-12 (unit tests)
**Wave**: 5
**Agent**: builder
**Complexity**: 5/10

**Acceptance Criteria**:
- All graceful fallback tests pass
- Zero exceptions leak when Redis unavailable
- Warning logs emitted for degraded operations
- `ruff check tests/test_cache/test_graceful_fallback.py` clean

---

## Wave 6: Verification + Cleanup (2 sequential tasks)

### P3-17: Full Verification Pass

**Description**: Run the complete verification suite to confirm zero regressions and all new tests pass.

**Commands**:
```bash
.venv/bin/python -m pytest tests/ -v            # ALL tests pass (445 existing + ~80 new)
ruff check src/ tests/                           # Clean
ruff format --check src/ tests/                  # Formatted
mypy src/                                        # Types pass
python -m src.cli --help                         # CLI still works without Redis
```

**Dependencies**: P3-15, P3-16 (all tests written)
**Wave**: 6
**Agent**: tester
**Complexity**: 2/10

**Acceptance Criteria**:
- `pytest tests/ -v` passes ALL tests (0 failures, 0 errors)
- `ruff check src/ tests/` reports 0 issues
- `mypy src/` reports 0 errors
- CLI launches without Redis configured
- Total test count: 445 + ~80-100 = ~525-545 tests

---

### P3-18: Update LEARNINGS.md + Package Init Exports

**Description**: Update `LEARNINGS.md` with Phase 3 patterns, gotchas, and decisions. Ensure `src/cache/__init__.py` exports all public classes. Verify `src/cache/` follows the same module boundary pattern as `src/memory/` and `src/moe/`.

**Files to modify**:
- `LEARNINGS.md` -- Add Phase 3 learnings
- `src/cache/__init__.py` -- Ensure clean exports

**Learnings to add**:
```
- PATTERN: graceful degradation → check `redis_manager.available` before ops, return None on failure
- PATTERN: Redis key namespacing → `{prefix}{type}:{scope_ids}` pattern for all keys
- PATTERN: fakeredis for testing → `fakeredis[lua]` with async support, no real Redis needed
- PATTERN: L0/L1/L2 cache hierarchy → in-memory dict (L0) → Redis (L1) → PostgreSQL (L2)
- GOTCHA: redis ZSET scores are floats → ScoredMemory.final_score maps directly
- GOTCHA: Redis unavailable → return safe defaults (None, True, []), NEVER raise
- DECISION: Phase 3 feature-flagged → `enable_redis_cache` controls initialization
- DECISION: token-bucket rate limiter → INCR + EXPIRE atomic pattern, degrades to allow-all
```

**Dependencies**: P3-17 (verification must pass first)
**Wave**: 6
**Agent**: builder
**Complexity**: 1/10

**Acceptance Criteria**:
- `LEARNINGS.md` has Phase 3 section
- `src/cache/__init__.py` exports `RedisManager`, `HotMemoryCache`, `WorkingMemoryCache`, `EmbeddingCache`, `RateLimiter`
- No import cycles

---

## Summary

| Wave | Tasks | Parallel | Description |
|------|-------|----------|-------------|
| 1 | P3-01, P3-02, P3-03, P3-04 | 4 | Foundation: settings, deps, client, conftest |
| 2 | P3-05, P3-06, P3-07, P3-08 | 4 | Core: hot_cache, working_memory, embedding_cache, rate_limiter |
| 3 | P3-09, P3-10, P3-11, P3-12 | 4 | Unit tests for all 4 cache modules |
| 4 | P3-13, P3-14 | 2 | Modify retrieval.py + embedding.py |
| 5 | P3-15, P3-16 | 2 | Integration tests + graceful fallback tests |
| 6 | P3-17, P3-18 | 1+1 seq | Full verification + LEARNINGS update |

**Total**: 18 tasks, 6 waves, max 4 agents per wave
**Critical Path**: P3-01 -> P3-05 -> P3-09 -> P3-13 -> P3-16 -> P3-17 (depth 6)
**Estimated New Tests**: ~80-100
**New Files**: 13 (6 src + 7 test)
**Modified Files**: 5 (settings, dependencies, retrieval, embedding, pyproject.toml) + .env.example + LEARNINGS.md
