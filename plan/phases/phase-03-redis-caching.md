# Phase 3: Redis + Caching Layer

> **Timeline**: Week 2-3 | **Prerequisites**: Phase 1 (Database Foundation), Phase 2 (Bulletproof Memory) | **Status**: Not Started

## Goal

Add Redis for caching, sessions, working memory, and rate limiting. Enables sub-100ms memory retrieval for hot data. Phase 3 introduces NO new database tables -- it is Redis-only. All features degrade gracefully when Redis is unavailable.

## Dependencies (Install)

```toml
[project]
dependencies = [
    # ... existing + Phase 1 + Phase 2 ...
    "redis[hiredis]~=5.2.0",
]
```

> `hiredis` is a C-based Redis parser that provides ~10x faster parsing. The `redis[hiredis]` extra installs it automatically.

## Settings Extensions

Add to `src/settings.py`:

```python
redis_url: Optional[str] = Field(default=None, description="Redis connection URL")
redis_key_prefix: str = Field(default="ska:", description="Redis key namespace prefix")
```

Also update `.env.example` with:
```bash
REDIS_URL=redis://localhost:6379/0
```

## New Directories & Files

```
src/cache/
    __init__.py
    client.py           # Async Redis pool creation, health check, cleanup
    working_memory.py   # WorkingMemoryCache (current conversation context)
    hot_cache.py        # HotMemoryCache (pre-warmed frequent memories)
    embedding_cache.py  # EmbeddingCache (avoid re-embedding same text)
    rate_limiter.py     # Token-bucket rate limiter
```

## Database Tables Introduced

**No new tables.** Phase 3 is Redis-only. No PostgreSQL schema changes.

All Redis data is ephemeral with TTLs -- no persistent data stored exclusively in Redis. PostgreSQL remains the source of truth.

Reference: `plan/sql/schema.sql` (no Phase 3 section exists -- Redis has no schema)

## Implementation Details

### Redis Key Namespaces

```
ska:working:{conversation_id}      # Current convo context (HASH, TTL 2h)
ska:hot:{agent_id}:{user_id}       # Pre-warmed memories (ZSET, TTL 15m)
ska:embed:{sha256}                  # Cached embeddings (STRING, TTL 24h)
ska:rate:{team_id}:{resource}       # Rate limit counters (STRING, TTL window)
ska:lock:{resource}:{id}            # Distributed locks (STRING, TTL 30s)
```

### Redis Client (`src/cache/client.py`)

```python
class RedisManager:
    """Redis with graceful fallback to no-cache."""

    async def get_client(self) -> Optional[Redis]:
        """Returns None if Redis unavailable. All callers handle None."""

    @property
    def available(self) -> bool:
        """Health check without throwing."""
```

### Graceful Degradation

If Redis is down, all features fall back gracefully:

| Feature | Normal Mode (Redis Up) | Degraded Mode (Redis Down) |
|---------|----------------------|---------------------------|
| Working memory | Redis HASH with TTL 2h | Falls back to in-process dict |
| Hot cache | Redis ZSET with TTL 15m | Falls back to direct PostgreSQL queries |
| Rate limiting | Redis token-bucket counters | Disabled (log warning) |
| Embedding cache | Redis STRING with TTL 24h | Falls back to LRU in-memory (Phase 2) |
| Distributed locks | Redis SETNX with TTL 30s | Skip locking (log warning) |

### Retrieval with Cache (Updated Flow)

This integrates with the Phase 2 `MemoryRetriever` by injecting a `HotMemoryCache` instance:

```
User message arrives
    |
    +-> Check ska:hot:{agent_id}:{user_id}
    |   +-- HIT: Return cached memories (< 5ms)
    |   +-- MISS: Fall through to PostgreSQL retrieval
    |              +-- After retrieval: populate hot cache
```

The Phase 2 `MemoryRetriever.__init__` already accepts `hot_cache: Optional[HotMemoryCache] = None`. Phase 3 provides the concrete implementation.

### Hot Memory Cache (`src/cache/hot_cache.py`)

Pre-warmed Redis sorted set of frequently-accessed memories (L1 tier):

```python
class HotMemoryCache:
    """
    L1 hot cache for frequently-accessed memories.

    Uses Redis ZSET where score = final_score from 5-signal retrieval.
    TTL: 15 minutes (auto-refresh on access).
    Key: ska:hot:{agent_id}:{user_id}
    """

    async def get_memories(
        self,
        agent_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> Optional[list[ScoredMemory]]:
        """
        Get pre-warmed memories from Redis.
        Returns None on cache miss (caller falls through to PostgreSQL).
        """

    async def warm_cache(
        self,
        agent_id: UUID,
        user_id: UUID,
        memories: list[ScoredMemory],
    ) -> None:
        """
        Populate hot cache after a PostgreSQL retrieval.
        Set TTL to 15 minutes.
        """

    async def invalidate(
        self,
        agent_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> None:
        """
        Clear hot cache for an agent (all users or specific user).
        Called when: new memories stored, memories superseded, manual flush.
        """
```

### Working Memory (`src/cache/working_memory.py`)

In-conversation state stored in Redis (not PostgreSQL):

```python
class WorkingMemoryCache:
    """Manage active conversation state in Redis."""

    async def set_context(
        self, conversation_id: UUID, context: dict
    ) -> None: ...

    async def get_context(
        self, conversation_id: UUID
    ) -> Optional[dict]: ...

    async def append_turn(
        self, conversation_id: UUID, role: str, content: str
    ) -> None: ...
```

Working memory includes:
- Current conversation summary (auto-generated every 20 messages)
- Active skill context (which skills are loaded)
- Temporary scratchpad (agent can store intermediate results)

Key format: `ska:working:{conversation_id}` (HASH, TTL 2h)

### Embedding Cache (`src/cache/embedding_cache.py`)

Avoids re-embedding the same text by caching embedding vectors in Redis:

```python
class EmbeddingCache:
    """
    Redis-backed embedding cache.

    Supplements the Phase 2 in-memory LRU cache with persistent
    Redis storage. TTL: 24 hours.
    Key: ska:embed:{sha256_of_normalized_text}
    """

    async def get_embedding(self, text: str) -> Optional[list[float]]:
        """Check Redis for cached embedding. Returns None on miss."""

    async def store_embedding(self, text: str, embedding: list[float]) -> None:
        """Store embedding in Redis with 24h TTL."""
```

The Phase 2 `EmbeddingService` is updated to check Redis cache before making API calls:
1. Check in-memory LRU cache (< 1ms)
2. Check Redis cache (< 5ms)
3. Call OpenAI API (< 500ms)
4. Store result in both caches

### Rate Limiter (`src/cache/rate_limiter.py`)

Token-bucket rate limiter using Redis counters:

```python
class RateLimiter:
    """
    Token-bucket rate limiter using Redis.

    Key: ska:rate:{team_id}:{resource}
    TTL: matches the rate limit window
    """

    async def check_rate_limit(
        self,
        team_id: UUID,
        resource: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """
        Check if request is within rate limit.

        Returns RateLimitResult with:
        - allowed: bool
        - remaining: int
        - reset_at: datetime
        - limit: int
        """
```

Rate limit configuration (used by Phase 4 API, defined here):

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

### Integration Points with Phase 2

Phase 3 enhances Phase 2 components:

| Phase 2 Component | Phase 3 Enhancement |
|-------------------|-------------------|
| `EmbeddingService` (in-memory LRU) | + Redis embedding cache (24h TTL) |
| `MemoryRetriever` (`hot_cache=None`) | + `HotMemoryCache` concrete implementation |
| `TierManager` (L1 hot = concept only) | + Actual Redis-backed L1 hot tier |
| `CompactionShield` (generates summary) | + Summary stored in `WorkingMemoryCache` |

### Critical Constraint

After Phase 3 completes:
```bash
python -m src.cli                    # CLI still works (Redis is Optional)
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
```

## Tests

```
tests/test_cache/
    conftest.py             # Redis test fixtures (fakeredis)
    test_working_memory.py  # Set/get context, append turns, TTL expiry
    test_hot_cache.py       # Warm cache, get memories, invalidation
    test_embedding_cache.py # Store/retrieve embeddings, TTL, cache key
    test_rate_limiter.py    # Allow/deny, window reset, counter increment
    test_graceful_fallback.py  # Verify behavior when Redis is down
```

### Key Test Scenarios

- Hot cache hit returns memories in < 10ms (using fakeredis)
- Hot cache miss returns None (falls through to PostgreSQL)
- Hot cache TTL expires after 15 minutes (simulated)
- Hot cache invalidation clears all cached memories for an agent
- Working memory stores and retrieves conversation context
- Working memory TTL expires after 2 hours (simulated)
- Working memory append_turn accumulates conversation turns
- Embedding cache stores and retrieves embeddings correctly
- Embedding cache TTL expires after 24 hours (simulated)
- Embedding cache key is SHA-256 of normalized text
- Rate limiter allows requests within limit
- Rate limiter denies requests that exceed limit
- Rate limiter resets after window expires
- Rate limiter returns correct remaining count and reset time
- Graceful fallback: working memory uses in-process dict when Redis is down
- Graceful fallback: hot cache returns None (direct PG queries) when Redis is down
- Graceful fallback: rate limiting disabled when Redis is down (logs warning)
- Graceful fallback: embedding cache falls back to LRU in-memory when Redis is down
- Redis health check returns correct status
- CLI still works with no Redis configured
- All Phase 1 and Phase 2 tests continue to pass

## Acceptance Criteria

- [ ] Hot cache hit returns memories in < 10ms
- [ ] Cache miss falls through to PostgreSQL correctly
- [ ] Working memory persists across API calls within conversation
- [ ] Rate limiter correctly throttles excessive requests
- [ ] All features degrade gracefully when Redis is unavailable
- [ ] CLI still works (Redis is Optional)

## Rollback Strategy

- Delete `src/cache/` module entirely
- All Redis keys are TTL-based (auto-expire) -- no manual cleanup needed
- Revert `src/settings.py` changes (remove `redis_url`, `redis_key_prefix`)
- Revert `.env.example` changes (remove `REDIS_URL`)
- Revert `pyproject.toml` dependency additions (remove `redis[hiredis]`)
- Phase 2 `MemoryRetriever` continues to work with `hot_cache=None`
- Phase 2 `EmbeddingService` continues to work with in-memory LRU cache only

## Links to Main Plan

- Architecture: `plan/multi-agent-platform.md` Section 2 (Redis in architecture diagram)
- ADRs:
  - ADR-2: Celery + Redis (Section 3, Redis as broker + cache)
- Memory Hierarchy: Section 3B (L1 Hot tier = Redis, L2 Warm = PostgreSQL, L3 Cold = PostgreSQL archive)
- Phase 3 implementation details: Section 4, "Phase 3: Redis + Caching Layer"
- Files modified: Section 5 (`pyproject.toml`, `src/settings.py`)
- New directories: Section 6 (`src/cache/`)
- Performance targets: Section 10 (hot cache hit < 10ms, cold DB < 200ms)
- Rollback: Section 23
- Phase dependency graph: Section 21 (Phase 3 depends on Phase 2, can overlap with Phase 2 development)
- Rate limits: Section 16 (API Design Conventions)
- Glossary: Section 12 (Hot Cache, Working Memory, Memory Tier definitions)
