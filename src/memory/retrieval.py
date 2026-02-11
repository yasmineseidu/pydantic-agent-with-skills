"""Five-signal memory retrieval pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import MemoryORM, MemoryStatusEnum
from src.db.repositories.memory_repo import MemoryRepository
from src.memory.embedding import EmbeddingService
from src.memory.token_budget import TokenBudgetManager
from src.memory.types import (
    Contradiction,
    RetrievalResult,
    RetrievalStats,
    ScoredMemory,
)
from src.models.agent_models import RetrievalWeights
from src.models.memory_models import MemoryRecord, MemoryType

if TYPE_CHECKING:
    from src.cache.hot_cache import HotMemoryCache

logger = logging.getLogger(__name__)

# Hot cache TTL in seconds
_CACHE_TTL: float = 60.0

# Maximum L0 cache entries to prevent unbounded memory growth
_CACHE_MAX_SIZE: int = 500


class _CacheEntry:
    """In-memory cache entry with TTL tracking.

    Attributes:
        result: The cached RetrievalResult.
        created_at: Monotonic timestamp when the entry was created.
    """

    __slots__ = ("result", "created_at")

    def __init__(self, result: RetrievalResult) -> None:
        self.result: RetrievalResult = result
        self.created_at: float = time.monotonic()

    def is_expired(self) -> bool:
        """Check whether this cache entry has exceeded its TTL.

        Returns:
            True if the entry is older than _CACHE_TTL seconds.
        """
        return (time.monotonic() - self.created_at) > _CACHE_TTL


def _orm_to_record(orm: MemoryORM) -> MemoryRecord:
    """Convert a MemoryORM instance to a MemoryRecord Pydantic model.

    Args:
        orm: The SQLAlchemy ORM memory object.

    Returns:
        A MemoryRecord with all fields mapped from the ORM row.
    """
    return MemoryRecord(
        id=orm.id,
        team_id=orm.team_id,
        agent_id=orm.agent_id,
        user_id=orm.user_id,
        memory_type=orm.memory_type,
        content=orm.content,
        subject=orm.subject,
        importance=orm.importance,
        confidence=orm.confidence,
        access_count=orm.access_count,
        is_pinned=orm.is_pinned,
        source_type=orm.source_type,
        source_conversation_id=orm.source_conversation_id,
        source_message_ids=orm.source_message_ids or [],
        extraction_model=orm.extraction_model,
        version=orm.version,
        superseded_by=orm.superseded_by,
        contradicts=orm.contradicts or [],
        related_to=orm.related_to or [],
        metadata=orm.metadata_json or {},
        tier=orm.tier,
        status=orm.status,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        last_accessed_at=orm.last_accessed_at,
        expires_at=orm.expires_at,
    )


def _cache_key(query: str) -> str:
    """Compute a cache key from a query string via SHA-256.

    Args:
        query: The raw query text.

    Returns:
        SHA-256 hex digest of the lowercased, stripped query.
    """
    normalized: str = query.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _compute_semantic_score(similarity: float) -> float:
    """Return the semantic signal score from cosine similarity.

    Args:
        similarity: Cosine similarity in [0.0, 1.0].

    Returns:
        The similarity value clamped to [0.0, 1.0].
    """
    return max(0.0, min(1.0, similarity))


def _compute_recency_score(last_accessed_at: datetime) -> float:
    """Compute the recency signal as an exponential decay.

    Score = exp(-0.01 * hours_since_last_access).

    Args:
        last_accessed_at: When the memory was last accessed (timezone-aware).

    Returns:
        Recency score in [0.0, 1.0].
    """
    now = datetime.now(timezone.utc)
    hours: float = (now - last_accessed_at).total_seconds() / 3600.0
    return math.exp(-0.01 * max(0.0, hours))


def _compute_importance_score(memory: MemoryRecord) -> float:
    """Compute the importance signal from memory metadata.

    Rules:
    - identity type -> 1.0
    - pinned -> 1.0
    - disputed status -> (importance / 10.0) * 0.5
    - otherwise -> importance / 10.0

    Args:
        memory: The memory record to score.

    Returns:
        Importance score in [0.0, 1.0].
    """
    if memory.memory_type == MemoryType.IDENTITY:
        return 1.0
    if memory.is_pinned:
        return 1.0
    base: float = memory.importance / 10.0
    if memory.status == "disputed":
        return base * 0.5
    return base


def _compute_continuity_score(
    memory: MemoryRecord,
    conversation_id: UUID | None,
) -> float:
    """Compute the continuity signal based on conversation context.

    Memories from the same conversation score 1.0, otherwise 0.0.

    Args:
        memory: The memory record to score.
        conversation_id: The current conversation UUID, or None.

    Returns:
        1.0 if same conversation, 0.0 otherwise.
    """
    if conversation_id and memory.source_conversation_id == conversation_id:
        return 1.0
    return 0.0


def _compute_weighted_score(
    signals: dict[str, float],
    weights: RetrievalWeights,
) -> float:
    """Compute a final weighted score from individual signal scores.

    Args:
        signals: Dict mapping signal names to their [0.0, 1.0] scores.
        weights: The RetrievalWeights defining each signal's weight.

    Returns:
        Weighted sum clamped to [0.0, 1.0].
    """
    score: float = (
        signals.get("semantic", 0.0) * weights.semantic
        + signals.get("recency", 0.0) * weights.recency
        + signals.get("importance", 0.0) * weights.importance
        + signals.get("continuity", 0.0) * weights.continuity
        + signals.get("relationship", 0.0) * weights.relationship
    )
    return max(0.0, min(1.0, score))


def _detect_contradictions(memories: list[ScoredMemory]) -> list[Contradiction]:
    """Detect contradictions among retrieved memories.

    A contradiction exists when memory A lists memory B's ID in its
    ``contradicts`` field (or vice versa).

    Args:
        memories: The scored memories to check for contradictions.

    Returns:
        List of Contradiction objects found among the memories.
    """
    memory_map: dict[UUID, MemoryRecord] = {sm.memory.id: sm.memory for sm in memories}
    seen_pairs: set[tuple[UUID, UUID]] = set()
    contradictions: list[Contradiction] = []

    for sm in memories:
        for contradicted_id in sm.memory.contradicts:
            cid = UUID(str(contradicted_id))
            if cid in memory_map:
                pair = tuple(sorted([sm.memory.id, cid], key=str))
                pair_key = (pair[0], pair[1])
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    contradictions.append(
                        Contradiction(
                            memory_a=sm.memory.id,
                            memory_b=cid,
                            reason=(
                                f"Memory '{sm.memory.content[:60]}' contradicts "
                                f"'{memory_map[cid].content[:60]}'"
                            ),
                        )
                    )

    return contradictions


def _format_prompt(
    memories: list[ScoredMemory],
    contradictions: list[Contradiction],
) -> str:
    """Format memories into a prompt-ready string grouped by type.

    Args:
        memories: Scored memories to format, ordered by score descending.
        contradictions: Contradictions to append as a disputed-facts section.

    Returns:
        Formatted string with section headers per memory type.
    """
    if not memories and not contradictions:
        return ""

    sections: dict[str, list[str]] = {}
    for sm in memories:
        type_name: str = sm.memory.memory_type.value
        sections.setdefault(type_name, []).append(sm.memory.content)

    parts: list[str] = []
    for type_name, contents in sections.items():
        parts.append(f"### {type_name.replace('_', ' ').title()} Memories")
        for content in contents:
            parts.append(f"- {content}")

    if contradictions:
        parts.append("\n### Disputed Facts")
        for c in contradictions:
            parts.append(f"[FACT DISPUTED]: {c.reason}")

    return "\n".join(parts)


class MemoryRetriever:
    """Five-signal memory retrieval pipeline with caching and budget management.

    Implements a 7-step retrieval process:
    1. Generate query embedding
    2. Check L0 in-memory cache, then L1 Redis hot cache
    3. Run 5-signal parallel search (semantic, recency, importance,
       continuity, relationship)
    4. Merge, deduplicate, and score results
    5. Apply token budget allocation
    6. Format memories for prompt injection
    7. Fire-and-forget access metadata update + warm L1 cache

    Args:
        session: Async SQLAlchemy session for database operations.
        embedding_service: Service for generating text embeddings.
        retrieval_weights: Per-signal weights for composite scoring.
        token_budget_manager: Manager for token budget allocation.
        hot_cache: Optional L1 Redis cache for frequently-accessed memories.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        retrieval_weights: RetrievalWeights,
        token_budget_manager: TokenBudgetManager,
        hot_cache: Optional[HotMemoryCache] = None,
    ) -> None:
        self._session: AsyncSession = session
        self._embedding_service: EmbeddingService = embedding_service
        self._weights: RetrievalWeights = retrieval_weights
        self._budget_manager: TokenBudgetManager = token_budget_manager
        self._repo: MemoryRepository = MemoryRepository(session)
        self._cache: dict[str, _CacheEntry] = {}
        self._hot_cache: Optional[HotMemoryCache] = hot_cache

    def _evict_cache(self) -> None:
        """Evict expired and oldest entries when cache exceeds max size.

        First removes all expired entries. If still over _CACHE_MAX_SIZE,
        removes oldest entries (by creation time) until at max size.
        """
        # Phase 1: Remove expired entries
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            del self._cache[key]

        # Phase 2: If still over limit, evict oldest entries
        if len(self._cache) >= _CACHE_MAX_SIZE:
            sorted_keys = sorted(
                self._cache.keys(), key=lambda k: self._cache[k].created_at
            )
            evict_count = len(self._cache) - _CACHE_MAX_SIZE + 1
            for key in sorted_keys[:evict_count]:
                del self._cache[key]

    async def retrieve(
        self,
        query: str,
        team_id: UUID,
        agent_id: UUID | None = None,
        conversation_id: UUID | None = None,
        budget: int | None = None,
    ) -> RetrievalResult:
        """Execute the 5-signal retrieval pipeline for a query.

        Args:
            query: The natural-language query to retrieve memories for.
            team_id: Team scope for memory visibility.
            agent_id: Optional agent scope. When provided, includes both
                agent-specific and team-wide (agent_id IS NULL) memories.
            conversation_id: Optional current conversation for continuity signal.
            budget: Optional token budget override.

        Returns:
            RetrievalResult containing scored memories, formatted prompt,
            performance stats, and any detected contradictions.
        """
        start_time: float = time.monotonic()

        # Step 1: Generate query embedding
        query_embedding: list[float] = await self._embedding_service.embed_text(query)

        # Step 2: Check L1 hot cache
        cache_key: str = _cache_key(query)
        cached_entry: _CacheEntry | None = self._cache.get(cache_key)
        if cached_entry is not None and not cached_entry.is_expired():
            elapsed_ms: float = (time.monotonic() - start_time) * 1000.0
            logger.info(
                "retrieve: cache_hit=True query_length=%d elapsed_ms=%.1f",
                len(query),
                elapsed_ms,
            )
            # Update stats to reflect cache hit timing
            cached_result = cached_entry.result.model_copy(deep=True)
            cached_result.stats.cache_hit = True
            cached_result.stats.total_ms = elapsed_ms
            return cached_result

        # Evict expired entry if present
        if cached_entry is not None:
            del self._cache[cache_key]

        # Step 2b: Check L1 Redis hot cache
        if self._hot_cache is not None and agent_id is not None:
            user_id_for_cache = team_id  # Use team_id as user scope
            cached_memories = await self._hot_cache.get_memories(
                agent_id=agent_id,
                user_id=user_id_for_cache,
                limit=20,
            )
            if cached_memories is not None:
                # L1 hit — reconstruct RetrievalResult from cached data
                elapsed_ms = (time.monotonic() - start_time) * 1000.0
                logger.info(
                    "retrieve: hot_cache_hit=True query_length=%d elapsed_ms=%.1f",
                    len(query),
                    elapsed_ms,
                )
                # Reconstruct ScoredMemory objects from cached dicts
                scored_memories_from_cache: list[ScoredMemory] = []
                for mem_dict in cached_memories:
                    try:
                        sm = ScoredMemory.model_validate(mem_dict)
                        scored_memories_from_cache.append(sm)
                    except Exception:
                        continue  # Skip malformed cache entries

                if scored_memories_from_cache:
                    contradictions = _detect_contradictions(scored_memories_from_cache)
                    formatted_prompt = _format_prompt(scored_memories_from_cache, contradictions)
                    stats = RetrievalStats(
                        signals_hit=self._count_signals_hit(scored_memories_from_cache),
                        cache_hit=True,
                        total_ms=elapsed_ms,
                        query_tokens=self._budget_manager.estimate_tokens(query),
                    )
                    result = RetrievalResult(
                        memories=scored_memories_from_cache,
                        formatted_prompt=formatted_prompt,
                        stats=stats,
                        contradictions=contradictions,
                    )
                    # Also populate L0 (with eviction)
                    self._evict_cache()
                    self._cache[cache_key] = _CacheEntry(result)
                    return result

        # Step 3: 5-signal parallel search
        # Run semantic search and team-wide recency fetch concurrently
        semantic_task = self._search_semantic(query_embedding, team_id, agent_id)
        recency_task = self._fetch_for_recency(team_id, agent_id)

        semantic_results, recency_results = await asyncio.gather(semantic_task, recency_task)

        # Step 4: Merge, deduplicate, and score
        scored_memories: list[ScoredMemory] = self._merge_and_score(
            semantic_results=semantic_results,
            recency_results=recency_results,
            conversation_id=conversation_id,
        )

        # Apply relationship bonus after initial scoring
        scored_memories = self._apply_relationship_bonus(scored_memories)

        # Sort by final_score descending
        scored_memories.sort(key=lambda sm: sm.final_score, reverse=True)

        # Detect contradictions among results
        contradictions: list[Contradiction] = _detect_contradictions(scored_memories)

        # Step 5: Token budget allocation
        included_memories, allocation = self._budget_manager.allocate(
            scored_memories, budget=budget
        )

        # Step 6: Format for prompt
        formatted_prompt: str = _format_prompt(included_memories, contradictions)

        # Compute stats
        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        signals_hit: int = self._count_signals_hit(included_memories)
        query_tokens: int = self._budget_manager.estimate_tokens(query)

        stats = RetrievalStats(
            signals_hit=signals_hit,
            cache_hit=False,
            total_ms=elapsed_ms,
            query_tokens=query_tokens,
        )

        result = RetrievalResult(
            memories=included_memories,
            formatted_prompt=formatted_prompt,
            stats=stats,
            contradictions=contradictions,
        )

        # Cache the result (with eviction)
        self._evict_cache()
        self._cache[cache_key] = _CacheEntry(result)

        # Step 7: Update access metadata (awaited to avoid shared session race)
        memory_ids: list[UUID] = [sm.memory.id for sm in included_memories]
        if memory_ids:
            await self._update_access_metadata(memory_ids)

        # Warm L1 Redis hot cache (fire-and-forget is safe here -- no shared session)
        if self._hot_cache is not None and agent_id is not None:
            user_id_for_cache = team_id
            # Serialize ScoredMemory objects to dicts for Redis storage
            memory_dicts = [sm.model_dump() for sm in included_memories]
            asyncio.create_task(
                self._hot_cache.warm_cache(agent_id, user_id_for_cache, memory_dicts)
            )

        logger.info(
            "retrieve: cache_hit=False memories=%d trimmed=%d elapsed_ms=%.1f budget_used=%d",
            allocation.memories_included,
            allocation.memories_trimmed,
            elapsed_ms,
            allocation.total_tokens,
        )

        return result

    async def _search_semantic(
        self,
        embedding: list[float],
        team_id: UUID,
        agent_id: UUID | None,
    ) -> list[tuple[MemoryORM, float]]:
        """Run semantic vector search via the repository.

        When agent_id is provided, performs two searches: one for agent-specific
        memories and one for team-wide (agent_id IS NULL) memories, then merges.

        Args:
            embedding: Query embedding vector.
            team_id: Team scope.
            agent_id: Optional agent scope.

        Returns:
            List of (MemoryORM, similarity) tuples.
        """
        if agent_id is not None:
            # Search agent-specific and team-wide in parallel
            agent_task = self._repo.search_by_embedding(
                embedding=embedding,
                team_id=team_id,
                agent_id=agent_id,
                limit=20,
            )
            team_task = self._repo.search_by_embedding(
                embedding=embedding,
                team_id=team_id,
                agent_id=None,
                limit=20,
            )
            agent_results, team_results = await asyncio.gather(agent_task, team_task)
            # Merge, dedup by memory ID keeping highest similarity
            merged: dict[UUID, tuple[MemoryORM, float]] = {}
            for orm, sim in agent_results + team_results:
                if orm.id not in merged or sim > merged[orm.id][1]:
                    merged[orm.id] = (orm, sim)
            return list(merged.values())
        else:
            return await self._repo.search_by_embedding(
                embedding=embedding,
                team_id=team_id,
                limit=20,
            )

    async def _fetch_for_recency(
        self,
        team_id: UUID,
        agent_id: UUID | None,
    ) -> list[MemoryORM]:
        """Fetch recent memories for the recency signal.

        Fetches team-wide memories ordered by last_accessed_at DESC.
        When agent_id is provided, also fetches agent-specific memories.

        Args:
            team_id: Team scope.
            agent_id: Optional agent scope.

        Returns:
            List of MemoryORM objects ordered by recency.
        """
        if agent_id is not None:
            agent_task = self._repo.get_by_team(
                team_id=team_id,
                status=MemoryStatusEnum.ACTIVE,
                limit=50,
            )
            # get_by_team doesn't filter by agent_id directly;
            # we fetch broadly and let merge handle dedup
            results = await agent_task
            return results
        else:
            return await self._repo.get_by_team(
                team_id=team_id,
                status=MemoryStatusEnum.ACTIVE,
                limit=50,
            )

    def _merge_and_score(
        self,
        semantic_results: list[tuple[MemoryORM, float]],
        recency_results: list[MemoryORM],
        conversation_id: UUID | None,
    ) -> list[ScoredMemory]:
        """Merge semantic and recency results, compute 4 of 5 signal scores.

        Relationship signal is applied separately after this step.

        Args:
            semantic_results: (MemoryORM, similarity) tuples from vector search.
            recency_results: MemoryORM objects from recency fetch.
            conversation_id: Current conversation for continuity scoring.

        Returns:
            Deduplicated list of ScoredMemory with 4-signal scores computed.
        """
        # Collect all unique memories with their semantic similarity
        memory_data: dict[UUID, tuple[MemoryRecord, float]] = {}

        for orm, similarity in semantic_results:
            record = _orm_to_record(orm)
            if record.id not in memory_data:
                memory_data[record.id] = (record, similarity)
            else:
                # Keep higher similarity
                existing_sim = memory_data[record.id][1]
                if similarity > existing_sim:
                    memory_data[record.id] = (record, similarity)

        for orm in recency_results:
            record = _orm_to_record(orm)
            if record.id not in memory_data:
                # No semantic similarity for recency-only memories
                memory_data[record.id] = (record, 0.0)

        # Compute per-memory signal scores
        scored: list[ScoredMemory] = []
        for memory_id, (record, similarity) in memory_data.items():
            signals: dict[str, float] = {
                "semantic": _compute_semantic_score(similarity),
                "recency": _compute_recency_score(record.last_accessed_at),
                "importance": _compute_importance_score(record),
                "continuity": _compute_continuity_score(record, conversation_id),
                "relationship": 0.0,  # Applied in next step
            }
            final_score = _compute_weighted_score(signals, self._weights)

            scored.append(
                ScoredMemory(
                    memory=record,
                    final_score=final_score,
                    signal_scores=signals,
                )
            )

        return scored

    def _apply_relationship_bonus(
        self,
        scored_memories: list[ScoredMemory],
    ) -> list[ScoredMemory]:
        """Apply the relationship signal bonus to scored memories.

        For each memory M, if any other retrieved memory N has M.id in
        N.related_to, M gets a 0.5 relationship score. The final weighted
        score is then recomputed.

        Args:
            scored_memories: Memories with 4-signal scores already computed.

        Returns:
            Updated list with relationship bonus applied and scores recomputed.
        """
        # Build set of all IDs that are referenced by other memories' related_to
        referenced_ids: set[UUID] = set()
        for sm in scored_memories:
            for related_id in sm.memory.related_to:
                referenced_ids.add(UUID(str(related_id)))

        # Apply bonus and recompute
        updated: list[ScoredMemory] = []
        for sm in scored_memories:
            if sm.memory.id in referenced_ids:
                new_signals = dict(sm.signal_scores)
                new_signals["relationship"] = 0.5
                new_score = _compute_weighted_score(new_signals, self._weights)
                updated.append(
                    ScoredMemory(
                        memory=sm.memory,
                        final_score=new_score,
                        signal_scores=new_signals,
                    )
                )
            else:
                updated.append(sm)

        return updated

    def _count_signals_hit(self, memories: list[ScoredMemory]) -> int:
        """Count how many distinct signals contributed non-zero scores.

        Looks across all included memories and counts signal names that
        had at least one non-zero value.

        Args:
            memories: The included memories to inspect.

        Returns:
            Number of distinct signals with at least one non-zero score.
        """
        signal_names: set[str] = set()
        for sm in memories:
            for name, score in sm.signal_scores.items():
                if score > 0.0:
                    signal_names.add(name)
        return len(signal_names)

    async def _update_access_metadata(self, memory_ids: list[UUID]) -> None:
        """Increment access_count and update last_accessed_at for memories.

        Runs as a fire-and-forget task. Errors are logged but do not
        propagate to the caller.

        Args:
            memory_ids: UUIDs of memories that were retrieved and included.
        """
        try:
            now = datetime.now(timezone.utc)
            for memory_id in memory_ids:
                orm: Optional[MemoryORM] = await self._repo.get(memory_id)
                if orm is not None:
                    orm.access_count += 1
                    orm.last_accessed_at = now
            await self._session.flush()
            logger.info(
                "update_access_metadata: updated=%d memory_ids",
                len(memory_ids),
            )
        except Exception as e:
            logger.error(
                "update_access_metadata: error=%s memory_count=%d",
                str(e),
                len(memory_ids),
            )
