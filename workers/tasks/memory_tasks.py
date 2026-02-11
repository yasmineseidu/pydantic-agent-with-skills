"""Celery tasks for memory extraction and management."""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from celery import shared_task
from sqlalchemy import and_, select as sa_select, update as sa_update

from src.db.models.memory import (
    MemoryORM,
    MemorySourceEnum,
    MemoryStatusEnum,
    MemoryTierEnum,
    MemoryTypeEnum,
)
from workers.utils import get_task_session_factory, get_task_settings, run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.memory_tasks.extract_memories",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def extract_memories(
    self,  # type: ignore[no-untyped-def]
    messages: list[dict[str, str]],
    team_id: str,
    agent_id: str,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Extract memories from conversation messages via double-pass LLM extraction.

    Args:
        self: Celery task instance (for retries).
        messages: List of {"role": "...", "content": "..."} message dicts.
        team_id: Team UUID as string.
        agent_id: Agent UUID as string.
        user_id: User UUID as string.
        conversation_id: Conversation UUID as string.

    Returns:
        Dict with extraction counts: memories_created, memories_versioned,
        duplicates_skipped, contradictions_found.
    """
    logger.info(
        "extract_memories_started: conversation_id=%s, message_count=%d",
        conversation_id,
        len(messages),
    )

    try:
        result = run_async(
            _async_extract_memories(
                messages=messages,
                team_id=team_id,
                agent_id=agent_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        )
        logger.info(
            "extract_memories_completed: conversation_id=%s, result=%s",
            conversation_id,
            result,
        )
        return result
    except Exception as exc:
        logger.warning(
            "extract_memories_failed: conversation_id=%s, error=%s, retry=%d/%d",
            conversation_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


async def _async_extract_memories(
    messages: list[dict[str, str]],
    team_id: str,
    agent_id: str,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Async implementation of memory extraction.

    Creates fresh services per invocation to avoid sharing state
    between Celery task executions.

    Args:
        messages: Conversation messages to extract from.
        team_id: Team UUID as string.
        agent_id: Agent UUID as string.
        user_id: User UUID as string.
        conversation_id: Conversation UUID as string.

    Returns:
        Extraction result counts.
    """
    from uuid import UUID

    from src.memory.contradiction import ContradictionDetector
    from src.memory.embedding import EmbeddingService
    from src.memory.memory_log import MemoryAuditLog
    from src.memory.storage import MemoryExtractor

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    async with session_factory() as session:
        # Create fresh services for this task invocation
        embedding_service = EmbeddingService(
            api_key=settings.embedding_api_key or settings.llm_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        audit_log = MemoryAuditLog(session)
        contradiction_detector = ContradictionDetector(
            session=session,
            embedding_service=embedding_service,
        )

        extractor = MemoryExtractor(
            session=session,
            embedding_service=embedding_service,
            contradiction_detector=contradiction_detector,
            audit_log=audit_log,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or "https://openrouter.ai/api/v1",
            extraction_model=settings.llm_model,
        )

        result = await extractor.extract_from_conversation(
            messages=messages,
            team_id=UUID(team_id),
            agent_id=UUID(agent_id),
            user_id=UUID(user_id),
            conversation_id=UUID(conversation_id),
        )

        await session.commit()

        return {
            "memories_created": result.memories_created,
            "memories_versioned": result.memories_versioned,
            "duplicates_skipped": result.duplicates_skipped,
            "contradictions_found": result.contradictions_found,
        }


# ---------------------------------------------------------------------------
# Consolidation Phase 1: merge near-duplicate memories
# ---------------------------------------------------------------------------

MERGE_SIMILARITY_THRESHOLD: float = 0.92


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Cosine similarity score between -1.0 and 1.0.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _call_llm(settings: Any, prompt: str, system_prompt: str = "") -> str:
    """Call LLM via httpx for consolidation operations.

    Args:
        settings: Application settings with LLM config.
        prompt: User prompt content.
        system_prompt: Optional system prompt.

    Returns:
        LLM response text.
    """
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.llm_base_url or 'https://openrouter.ai/api/v1'}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": 1024,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


@shared_task(
    name="workers.tasks.memory_tasks.consolidate_memories",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def consolidate_memories(
    self,  # type: ignore[no-untyped-def]
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Consolidate near-duplicate memories by merging similar pairs.

    Phase 1: finds active memory pairs with cosine similarity > 0.92,
    merges their content via LLM, re-embeds, and marks losers as superseded.

    When called without args (e.g., from Beat schedule), iterates all distinct
    (team_id, agent_id) pairs with active memories.

    Args:
        self: Celery task instance (for retries).
        team_id: Team UUID as string. None to process all teams.
        agent_id: Agent UUID as string. None to process all agents.

    Returns:
        Dict with total merge and summary counts.
    """
    logger.info(
        "consolidate_memories_started: team_id=%s, agent_id=%s",
        team_id,
        agent_id,
    )

    try:
        result = run_async(
            _async_consolidate(
                team_id=team_id,
                agent_id=agent_id,
            )
        )
        logger.info(
            "consolidate_memories_completed: team_id=%s, agent_id=%s, result=%s",
            team_id,
            agent_id,
            result,
        )
        return result
    except Exception as exc:
        logger.warning(
            "consolidate_memories_failed: team_id=%s, agent_id=%s, error=%s, retry=%d/%d",
            team_id,
            agent_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


async def _async_consolidate(
    team_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Async implementation of memory consolidation.

    When team_id and agent_id are provided, consolidates only that pair.
    When both are None, queries all distinct (team_id, agent_id) pairs
    with active memories and consolidates each.

    Args:
        team_id: Team UUID as string, or None to process all teams.
        agent_id: Agent UUID as string, or None to process all agents.

    Returns:
        Dict with total merge and summary counts.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.memory.embedding import EmbeddingService

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    # Build list of (team_id, agent_id) pairs to process
    pairs: list[tuple[UUID, UUID]] = []

    if team_id is not None and agent_id is not None:
        pairs = [(UUID(team_id), UUID(agent_id))]
    else:
        # Query all distinct (team_id, agent_id) pairs with active memories
        async with session_factory() as session:
            stmt = (
                select(MemoryORM.team_id, MemoryORM.agent_id)
                .where(MemoryORM.status == MemoryStatusEnum.ACTIVE)
                .distinct()
            )
            result = await session.execute(stmt)
            pairs = [(row[0], row[1]) for row in result.all() if row[0] and row[1]]

    if not pairs:
        logger.info("consolidate_memories: no active memory pairs found")
        return {"merges": 0, "summaries": 0}

    total_merges = 0
    total_summaries = 0

    for pair_team_id, pair_agent_id in pairs:
        async with session_factory() as session:
            embedding_service = EmbeddingService(
                api_key=settings.embedding_api_key or settings.llm_api_key,
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )

            merges = await _merge_near_duplicates(
                session=session,
                embedding_service=embedding_service,
                settings=settings,
                agent_id=pair_agent_id,
                team_id=pair_team_id,
            )

            summaries = await _summarize_old_episodic(
                session=session,
                embedding_service=embedding_service,
                settings=settings,
                agent_id=pair_agent_id,
                team_id=pair_team_id,
            )

            await session.commit()

            total_merges += merges
            total_summaries += summaries

    return {"merges": total_merges, "summaries": total_summaries}


async def _merge_near_duplicates(
    session: Any,
    embedding_service: Any,
    settings: Any,
    agent_id: Any,
    team_id: Any,
) -> int:
    """Merge near-duplicate active memories (Phase 1 consolidation).

    Queries active memories grouped by memory_type and agent_id, computes
    pairwise cosine similarity on embeddings, and merges pairs above the
    threshold. The winner (higher importance) keeps its record, gets merged
    content via LLM, and is re-embedded. The loser is marked superseded.

    Args:
        session: AsyncSession for database operations.
        embedding_service: EmbeddingService for re-embedding merged content.
        settings: Application settings for LLM calls.
        agent_id: Agent UUID to scope memories.
        team_id: Team UUID to scope memories.

    Returns:
        Number of merges performed.
    """
    from collections import defaultdict

    from sqlalchemy import select

    from src.db.models.memory import MemoryORM, MemorySourceEnum, MemoryStatusEnum, MemoryTierEnum

    # Limit per query to bound O(n^2) pairwise comparisons.
    # 500 memories per (team, agent) → max 250K comparisons per type group.
    _CONSOLIDATION_LIMIT: int = 500

    stmt = (
        select(MemoryORM)
        .where(
            MemoryORM.team_id == team_id,
            MemoryORM.agent_id == agent_id,
            MemoryORM.status == MemoryStatusEnum.ACTIVE,
            MemoryORM.embedding.is_not(None),
        )
        .order_by(MemoryORM.last_accessed_at.desc())
        .limit(_CONSOLIDATION_LIMIT)
    )
    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    if len(memories) < 2:
        logger.info("merge_near_duplicates: skipped, fewer than 2 active memories")
        return 0

    # Group by memory_type for targeted comparison
    groups: dict[str, list[Any]] = defaultdict(list)
    for mem in memories:
        groups[mem.memory_type].append(mem)

    merge_count = 0
    merged_ids: set[Any] = set()

    for memory_type, group_memories in groups.items():
        if len(group_memories) < 2:
            continue

        # Pairwise comparison within each type group
        for i in range(len(group_memories)):
            if group_memories[i].id in merged_ids:
                continue

            for j in range(i + 1, len(group_memories)):
                if group_memories[j].id in merged_ids:
                    continue

                mem_a = group_memories[i]
                mem_b = group_memories[j]

                # Both must have embeddings (already filtered, but guard)
                if mem_a.embedding is None or mem_b.embedding is None:
                    continue

                similarity = _cosine_similarity(
                    list(mem_a.embedding),
                    list(mem_b.embedding),
                )

                if similarity < MERGE_SIMILARITY_THRESHOLD:
                    continue

                # Determine winner (higher importance, or first if equal)
                if mem_b.importance > mem_a.importance:
                    winner, loser = mem_b, mem_a
                else:
                    winner, loser = mem_a, mem_b

                # Merge content via LLM
                try:
                    merged_content = await _call_llm(
                        settings,
                        prompt=(
                            f"Merge these two similar memories into one concise statement.\n\n"
                            f"Memory A: {winner.content}\n\n"
                            f"Memory B: {loser.content}\n\n"
                            f"Output ONLY the merged memory text, no explanation."
                        ),
                        system_prompt="You are a memory consolidation assistant. Merge overlapping information into a single clear statement.",
                    )
                except Exception as exc:
                    logger.warning(
                        "merge_llm_failed: winner_id=%s, loser_id=%s, error=%s",
                        winner.id,
                        loser.id,
                        str(exc),
                    )
                    continue

                # Re-embed the merged content
                try:
                    new_embedding = await embedding_service.embed_text(merged_content)
                except Exception as exc:
                    logger.warning(
                        "merge_embed_failed: winner_id=%s, error=%s",
                        winner.id,
                        str(exc),
                    )
                    continue

                # Update winner with merged content
                winner.content = merged_content.strip()
                winner.embedding = new_embedding
                winner.source_type = MemorySourceEnum.CONSOLIDATION
                winner.version = winner.version + 1

                # Mark loser as superseded
                loser.status = MemoryStatusEnum.SUPERSEDED
                loser.tier = MemoryTierEnum.COLD
                loser.superseded_by = winner.id

                merged_ids.add(loser.id)
                merge_count += 1

                logger.info(
                    "memory_merged: winner_id=%s, loser_id=%s, similarity=%.4f, type=%s",
                    winner.id,
                    loser.id,
                    similarity,
                    memory_type,
                )

    logger.info(
        "merge_near_duplicates_completed: team_id=%s, agent_id=%s, merges=%d",
        team_id,
        agent_id,
        merge_count,
    )
    return merge_count


# ---------------------------------------------------------------------------
# Consolidation Phase 2: summarize old episodic memories
# ---------------------------------------------------------------------------

EPISODIC_CLUSTER_THRESHOLD: float = 0.80
_EPISODIC_STALE_DAYS: int = 7
_EPISODIC_MIN_ACCESS: int = 3
_EPISODIC_MIN_CLUSTER_SIZE: int = 3


async def _summarize_old_episodic(
    session: Any,
    embedding_service: Any,
    settings: Any,
    agent_id: UUID,
    team_id: UUID,
) -> int:
    """Summarize old, rarely-accessed episodic memories into consolidated entries.

    Queries episodic memories older than 7 days with access_count < 3,
    clusters by cosine similarity > 0.8, and creates LLM summaries for
    clusters with more than 2 members. Originals are marked superseded.

    Args:
        session: Async database session.
        embedding_service: Service for generating embeddings.
        settings: Application settings with LLM config.
        agent_id: Agent UUID.
        team_id: Team UUID.

    Returns:
        Number of consolidation summaries created.
    """
    from sqlalchemy import select

    cutoff = datetime.now(timezone.utc) - timedelta(days=_EPISODIC_STALE_DAYS)

    stmt = select(MemoryORM).where(
        MemoryORM.team_id == team_id,
        MemoryORM.agent_id == agent_id,
        MemoryORM.memory_type == MemoryTypeEnum.EPISODIC,
        MemoryORM.status == MemoryStatusEnum.ACTIVE,
        MemoryORM.created_at < cutoff,
        MemoryORM.access_count < _EPISODIC_MIN_ACCESS,
        MemoryORM.embedding.is_not(None),
    )
    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    if len(memories) < _EPISODIC_MIN_CLUSTER_SIZE:
        logger.info(
            "summarize_old_episodic: skipped, fewer than %d eligible memories",
            _EPISODIC_MIN_CLUSTER_SIZE,
        )
        return 0

    # Greedy clustering by cosine > 0.8
    clusters: list[list[MemoryORM]] = []
    used: set[int] = set()

    for i, mem_a in enumerate(memories):
        if i in used:
            continue
        cluster = [mem_a]
        used.add(i)
        for j in range(i + 1, len(memories)):
            if j in used:
                continue
            mem_b = memories[j]
            sim = _cosine_similarity(list(mem_a.embedding), list(mem_b.embedding))
            if sim > EPISODIC_CLUSTER_THRESHOLD:
                cluster.append(mem_b)
                used.add(j)
        if len(cluster) >= _EPISODIC_MIN_CLUSTER_SIZE:
            clusters.append(cluster)

    summaries_created = 0
    for cluster in clusters:
        contents = "\n---\n".join(m.content for m in cluster)
        try:
            summary = await _call_llm(
                settings,
                prompt=(
                    f"Summarize these {len(cluster)} related memories into one concise memory:\n\n"
                    f"{contents}"
                ),
                system_prompt="You are a memory consolidation system. Create a brief, factual summary.",
            )
        except Exception as exc:
            logger.warning(
                "summarize_episodic_llm_failed: cluster_size=%d, error=%s",
                len(cluster),
                str(exc),
            )
            continue

        max_importance = max(
            (m.importance for m in cluster if m.importance is not None),
            default=5,
        )

        # Re-embed the summary
        try:
            new_embedding = await embedding_service.embed_text(summary)
        except Exception as exc:
            logger.warning(
                "summarize_episodic_embed_failed: error=%s",
                str(exc),
            )
            continue

        # Create consolidated memory (episodic → semantic)
        new_memory = MemoryORM(
            team_id=team_id,
            agent_id=agent_id,
            memory_type=MemoryTypeEnum.SEMANTIC,
            content=summary.strip(),
            importance=max_importance,
            source_type=MemorySourceEnum.CONSOLIDATION,
            status=MemoryStatusEnum.ACTIVE,
            tier=MemoryTierEnum.WARM,
            embedding=new_embedding,
        )

        session.add(new_memory)
        await session.flush()

        # Mark originals as superseded
        for mem in cluster:
            mem.superseded_by = new_memory.id
            mem.status = MemoryStatusEnum.SUPERSEDED
            mem.tier = MemoryTierEnum.COLD

        summaries_created += 1
        logger.info(
            "episodic_cluster_summarized: cluster_size=%d, new_memory_id=%s, importance=%d",
            len(cluster),
            new_memory.id,
            max_importance,
        )

    logger.info(
        "summarize_old_episodic_completed: team_id=%s, agent_id=%s, clusters=%d, summaries=%d",
        team_id,
        agent_id,
        len(clusters),
        summaries_created,
    )
    return summaries_created


# ---------------------------------------------------------------------------
# Consolidation Phase 3-4: decay/expire memories + cache invalidation
# ---------------------------------------------------------------------------

# Memories accessed more recently than this are kept in warm tier
_STALE_WARM_DAYS: int = 30


@shared_task(
    name="workers.tasks.memory_tasks.decay_and_expire_memories",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def decay_and_expire_memories(
    self,  # type: ignore[no-untyped-def]
) -> dict[str, Any]:
    """Decay stale memories and expire old ones with cache invalidation.

    Phase 3: Archive expired, demote stale warm (with protection rules).
    Phase 4: Invalidate hot cache for affected agents.

    Returns:
        Dict with counts: archived, demoted, cache_invalidated.
    """
    logger.info("decay_and_expire_started")

    try:
        result = run_async(_async_decay_and_expire())
        logger.info("decay_and_expire_completed: result=%s", result)
        return result
    except Exception as exc:
        logger.warning(
            "decay_and_expire_failed: error=%s, retry=%d/%d",
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=120)


async def _async_decay_and_expire() -> dict[str, Any]:
    """Async implementation of decay/expire with cache invalidation.

    Phase 3 (decay):
        - Archive expired memories (expires_at < now, not already archived).
        - Demote stale warm memories (last_accessed_at older than 30 days).
        - Protection: never demote identity memories, pinned, or importance >= 8.
    Phase 4 (cache invalidation):
        - Collect agent_ids affected by Phase 3 changes.
        - Invalidate HotMemoryCache for each affected agent.
        - Graceful: if Redis unavailable, log warning and continue.

    Returns:
        Dict with counts: archived, demoted, cache_invalidated.
    """
    settings = get_task_settings()
    session_factory = get_task_session_factory()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=_STALE_WARM_DAYS)

    affected_agent_ids: set[UUID] = set()
    archived_count: int = 0
    demoted_count: int = 0

    async with session_factory() as session:
        # Phase 3a: Archive expired memories
        # First collect affected agent_ids before bulk update
        expired_agents_stmt = (
            sa_select(MemoryORM.agent_id)
            .where(
                MemoryORM.expires_at.isnot(None),
                MemoryORM.expires_at < now,
                MemoryORM.status != MemoryStatusEnum.ARCHIVED,
            )
            .distinct()
        )
        expired_agents_result = await session.execute(expired_agents_stmt)
        for (agent_id,) in expired_agents_result.all():
            if agent_id is not None:
                affected_agent_ids.add(agent_id)

        archive_stmt = (
            sa_update(MemoryORM)
            .where(
                MemoryORM.expires_at.isnot(None),
                MemoryORM.expires_at < now,
                MemoryORM.status != MemoryStatusEnum.ARCHIVED,
            )
            .values(
                tier=MemoryTierEnum.COLD,
                status=MemoryStatusEnum.ARCHIVED,
            )
        )
        archive_result = await session.execute(archive_stmt)
        archived_count = archive_result.rowcount  # type: ignore[assignment]

        logger.info("decay_archive_expired: count=%d", archived_count)

        # Phase 3b: Demote stale warm memories (with protection rules)
        # Protection: NEVER demote identity, pinned, or importance >= 8
        protection = and_(
            MemoryORM.memory_type != MemoryTypeEnum.IDENTITY,
            MemoryORM.is_pinned.is_(False),
            MemoryORM.importance < 8,
        )

        # Collect affected agent_ids for stale warm demotion
        stale_agents_stmt = (
            sa_select(MemoryORM.agent_id)
            .where(
                MemoryORM.tier == MemoryTierEnum.WARM,
                MemoryORM.last_accessed_at < stale_cutoff,
                protection,
            )
            .distinct()
        )
        stale_agents_result = await session.execute(stale_agents_stmt)
        for (agent_id,) in stale_agents_result.all():
            if agent_id is not None:
                affected_agent_ids.add(agent_id)

        demote_stmt = (
            sa_update(MemoryORM)
            .where(
                MemoryORM.tier == MemoryTierEnum.WARM,
                MemoryORM.last_accessed_at < stale_cutoff,
                protection,
            )
            .values(tier=MemoryTierEnum.COLD)
        )
        demote_result = await session.execute(demote_stmt)
        demoted_count = demote_result.rowcount  # type: ignore[assignment]

        logger.info("decay_demote_stale_warm: count=%d", demoted_count)

        await session.commit()

    # Phase 4: Cache invalidation for affected agents
    cache_invalidated: int = 0

    if affected_agent_ids:
        try:
            from src.cache.client import RedisManager
            from src.cache.hot_cache import HotMemoryCache

            if settings.redis_url:
                redis_mgr = RedisManager(
                    redis_url=settings.redis_url,
                    key_prefix=settings.redis_key_prefix,
                )
                cache = HotMemoryCache(redis_manager=redis_mgr)

                for agent_id in affected_agent_ids:
                    try:
                        await cache.invalidate(agent_id)
                        cache_invalidated += 1
                    except Exception as exc:
                        logger.warning(
                            "decay_cache_invalidate_agent_failed: agent_id=%s, error=%s",
                            agent_id,
                            str(exc),
                        )
        except Exception:
            logger.warning(
                "decay_cache_invalidation_failed: affected_agents=%d",
                len(affected_agent_ids),
            )

    logger.info(
        "decay_and_expire_summary: archived=%d, demoted=%d, cache_invalidated=%d",
        archived_count,
        demoted_count,
        cache_invalidated,
    )

    return {
        "archived": archived_count,
        "demoted": demoted_count,
        "cache_invalidated": cache_invalidated,
    }
