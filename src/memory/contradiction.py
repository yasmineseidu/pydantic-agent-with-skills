"""Contradiction detection for memory storage and retrieval."""

import logging
from itertools import combinations
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import MemoryORM, MemoryStatusEnum
from src.db.repositories.memory_repo import MemoryRepository
from src.memory.embedding import EmbeddingService
from src.memory.types import (
    Contradiction,
    ContradictionResult,
    ExtractedMemory,
    ScoredMemory,
)

logger = logging.getLogger(__name__)

# Semantic similarity threshold for detecting contradictions
_SEMANTIC_CONTRADICTION_THRESHOLD: float = 0.7

# Similarity threshold above which memories are near-duplicates
_DEDUP_THRESHOLD: float = 0.92


class ContradictionDetector:
    """Detects contradictions between memories during storage and retrieval.

    Provides two entry points:

    - ``check_on_store``: Pre-persistence check that compares a new memory
      against existing memories with the same subject, returning an action
      (supersede, dispute, or coexist).
    - ``check_on_retrieve``: Post-retrieval scan that identifies contradictions
      among a batch of returned memories so the caller can surface warnings.

    Args:
        session: Async SQLAlchemy session for database queries.
        embedding_service: Service for generating text embeddings.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
    ) -> None:
        """Initialize the contradiction detector.

        Args:
            session: Async SQLAlchemy session for database queries.
            embedding_service: Service for generating text embeddings.
        """
        self._session: AsyncSession = session
        self._embedding_service: EmbeddingService = embedding_service
        self._repo: MemoryRepository = MemoryRepository(session)

    async def check_on_store(
        self,
        new_memory: ExtractedMemory,
        team_id: UUID,
        agent_id: Optional[UUID] = None,
    ) -> ContradictionResult:
        """Check a new memory against existing memories before persistence.

        Performs a two-phase check:

        1. **Subject match**: Queries active memories with the same subject
           and compares content for conflicts.
        2. **Semantic similarity**: Embeds the new content and searches for
           semantically similar memories above a 0.7 cosine threshold that
           have clearly different content.

        Resolution rules:
        - Near-duplicate (cosine >= 0.92) with same content -> coexist
        - Same subject, different content, new memory has higher importance -> supersede
        - Same subject, different content, equal or lower importance -> dispute
        - No subject or no matches -> coexist

        Args:
            new_memory: The extracted memory to check before storing.
            team_id: Team scope for the search.
            agent_id: Optional agent scope (None = team-wide).

        Returns:
            ContradictionResult with contradicting memory UUIDs and resolution action.
        """
        # No subject means nothing to contradict on
        if not new_memory.subject:
            logger.info("check_on_store: no_subject, action=coexist")
            return ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No subject specified; cannot check for contradictions.",
            )

        # Phase 1: Query existing memories with the same subject
        subject_matches: list[MemoryORM] = await self._query_by_subject(
            subject=new_memory.subject,
            team_id=team_id,
            agent_id=agent_id,
        )

        contradicting_ids: list[UUID] = []
        action: str = "coexist"
        reasons: list[str] = []

        for existing in subject_matches:
            comparison: str = self._compare_content(
                new_content=new_memory.content,
                existing_content=existing.content,
            )

            if comparison == "same":
                # Content is effectively identical -- coexist / duplicate
                continue
            elif comparison == "different":
                contradicting_ids.append(existing.id)
                if new_memory.importance > existing.importance:
                    action = "supersede"
                    reasons.append(
                        f"New memory (importance={new_memory.importance}) supersedes "
                        f"existing memory {existing.id} (importance={existing.importance}) "
                        f"on subject '{new_memory.subject}'."
                    )
                else:
                    action = "dispute"
                    reasons.append(
                        f"Conflicting content with memory {existing.id} on subject "
                        f"'{new_memory.subject}'; importance is equal or lower."
                    )

        # Phase 2: Semantic similarity check
        semantic_contradictions: list[UUID] = await self._check_semantic_similarity(
            new_memory=new_memory,
            team_id=team_id,
            already_flagged=set(contradicting_ids),
        )

        for sem_id in semantic_contradictions:
            contradicting_ids.append(sem_id)
            if action == "coexist":
                action = "dispute"
            reasons.append(
                f"Semantic similarity above {_SEMANTIC_CONTRADICTION_THRESHOLD} "
                f"with memory {sem_id} but content differs."
            )

        reason: str = " ".join(reasons) if reasons else "No contradictions detected."

        logger.info(
            "check_on_store: subject=%s contradictions=%d action=%s",
            new_memory.subject,
            len(contradicting_ids),
            action,
        )

        return ContradictionResult(
            contradicts=contradicting_ids,
            action=action,
            reason=reason,
        )

    def check_on_retrieve(
        self,
        memories: list[ScoredMemory],
    ) -> list[Contradiction]:
        """Scan retrieved memories for contradictions among them.

        Groups memories by subject, then within each group compares
        every pair for differing content. Returns a Contradiction for
        each conflicting pair.

        Args:
            memories: Scored memories returned from retrieval.

        Returns:
            List of Contradiction objects for each disputed pair.
        """
        # Group memories by subject (skip those without a subject)
        subject_groups: dict[str, list[ScoredMemory]] = {}
        for scored in memories:
            subject: Optional[str] = scored.memory.subject
            if subject is None:
                continue
            normalized: str = subject.strip().lower()
            if not normalized:
                continue
            subject_groups.setdefault(normalized, []).append(scored)

        contradictions: list[Contradiction] = []

        for subject_key, group in subject_groups.items():
            if len(group) < 2:
                continue

            # Pairwise comparison within the subject group
            for mem_a, mem_b in combinations(group, 2):
                comparison: str = self._compare_content(
                    new_content=mem_a.memory.content,
                    existing_content=mem_b.memory.content,
                )
                if comparison == "different":
                    contradictions.append(
                        Contradiction(
                            memory_a=mem_a.memory.id,
                            memory_b=mem_b.memory.id,
                            reason=(
                                f"Conflicting content on subject '{subject_key}': "
                                f"'{mem_a.memory.content[:80]}' vs "
                                f"'{mem_b.memory.content[:80]}'."
                            ),
                        )
                    )

        logger.info(
            "check_on_retrieve: memories=%d contradictions=%d",
            len(memories),
            len(contradictions),
        )

        return contradictions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _query_by_subject(
        self,
        subject: str,
        team_id: UUID,
        agent_id: Optional[UUID] = None,
    ) -> list[MemoryORM]:
        """Query active memories with a matching subject.

        Args:
            subject: Subject string to match (case-insensitive).
            team_id: Team scope.
            agent_id: Optional agent scope.

        Returns:
            List of active MemoryORM records with the same subject.
        """
        filters = [
            MemoryORM.team_id == team_id,
            MemoryORM.status == MemoryStatusEnum.ACTIVE,
            MemoryORM.subject.isnot(None),
            func_lower(MemoryORM.subject) == subject.strip().lower(),
        ]
        if agent_id is not None:
            filters.append(MemoryORM.agent_id == agent_id)

        stmt = select(MemoryORM).where(and_(*filters)).order_by(MemoryORM.created_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _check_semantic_similarity(
        self,
        new_memory: ExtractedMemory,
        team_id: UUID,
        already_flagged: set[UUID],
    ) -> list[UUID]:
        """Find semantically similar memories that have different content.

        Embeds the new memory's content, searches for similar memories,
        and filters to those above the contradiction threshold but below
        the dedup threshold whose content actually differs.

        Args:
            new_memory: The memory being checked.
            team_id: Team scope for the search.
            already_flagged: Memory IDs already identified as contradicting.

        Returns:
            List of memory UUIDs that are semantically similar but content-different.
        """
        embedding: list[float] = await self._embedding_service.embed_text(new_memory.content)

        # Use search_by_embedding to get memories with similarity scores
        results: list[tuple[MemoryORM, float]] = await self._repo.search_by_embedding(
            embedding=embedding,
            team_id=team_id,
            limit=20,
        )

        semantic_contradictions: list[UUID] = []

        for existing, similarity in results:
            # Skip if already flagged by subject match
            if existing.id in already_flagged:
                continue

            # Skip near-duplicates (dedup range)
            if similarity >= _DEDUP_THRESHOLD:
                continue

            # Only consider memories above the contradiction threshold
            if similarity < _SEMANTIC_CONTRADICTION_THRESHOLD:
                continue

            # Content must actually differ
            comparison: str = self._compare_content(
                new_content=new_memory.content,
                existing_content=existing.content,
            )
            if comparison == "different":
                semantic_contradictions.append(existing.id)

        return semantic_contradictions

    @staticmethod
    def _compare_content(new_content: str, existing_content: str) -> str:
        """Compare two memory contents for equivalence.

        Uses normalized string comparison. Two pieces of content are
        considered "same" if their lowercased, stripped forms match.
        Otherwise they are "different".

        Args:
            new_content: Content of the new/first memory.
            existing_content: Content of the existing/second memory.

        Returns:
            "same" if contents match after normalization, "different" otherwise.
        """
        normalized_new: str = new_content.strip().lower()
        normalized_existing: str = existing_content.strip().lower()

        if normalized_new == normalized_existing:
            return "same"

        return "different"


def func_lower(column: object) -> object:
    """Apply SQL LOWER() to a column for case-insensitive comparison.

    Args:
        column: SQLAlchemy column expression.

    Returns:
        SQLAlchemy func.lower() expression.
    """
    from sqlalchemy import func

    return func.lower(column)
