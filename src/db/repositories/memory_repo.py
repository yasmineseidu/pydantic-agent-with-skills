"""Memory repository with vector similarity search."""

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import MemoryORM, MemoryStatusEnum, MemoryTypeEnum
from src.db.repositories.base import BaseRepository


class MemoryRepository(BaseRepository[MemoryORM]):
    """Repository for memory operations including vector similarity search.

    Extends BaseRepository with memory-specific queries:
    - Vector similarity search via pgvector cosine distance
    - Filtered retrieval by team, agent, memory type
    - Duplicate/similar memory detection for deduplication
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the memory repository.

        Args:
            session: AsyncSession for database operations.
        """
        super().__init__(session, MemoryORM)

    async def search_by_embedding(
        self,
        embedding: list[float],
        team_id: UUID,
        agent_id: Optional[UUID] = None,
        memory_types: Optional[list[MemoryTypeEnum]] = None,
        limit: int = 20,
    ) -> list[tuple[MemoryORM, float]]:
        """Search memories by vector similarity.

        Args:
            embedding: Query embedding vector (1536 dimensions).
            team_id: Team scope for search.
            agent_id: Optional agent scope (None = team-wide).
            memory_types: Optional filter by memory types.
            limit: Max results to return.

        Returns:
            List of (memory, similarity_score) tuples sorted by similarity DESC.
        """
        filters = [
            MemoryORM.team_id == team_id,
            MemoryORM.status.in_([MemoryStatusEnum.ACTIVE, MemoryStatusEnum.DISPUTED]),
            MemoryORM.embedding.isnot(None),
        ]
        if agent_id is not None:
            filters.append(MemoryORM.agent_id == agent_id)
        if memory_types:
            filters.append(MemoryORM.memory_type.in_(memory_types))

        # Cosine distance via pgvector <=> operator; similarity = 1 - distance
        distance = MemoryORM.embedding.cosine_distance(embedding)

        stmt = (
            select(MemoryORM, (1 - distance).label("similarity"))
            .where(and_(*filters))
            .order_by(distance)
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def find_similar(
        self,
        embedding: list[float],
        team_id: UUID,
        threshold: float = 0.92,
    ) -> list[MemoryORM]:
        """Find memories similar to a given embedding (for deduplication).

        Args:
            embedding: Embedding to compare against.
            team_id: Team scope.
            threshold: Minimum similarity score (0-1).

        Returns:
            List of memories above the similarity threshold.
        """
        distance = MemoryORM.embedding.cosine_distance(embedding)

        stmt = (
            select(MemoryORM)
            .where(
                and_(
                    MemoryORM.team_id == team_id,
                    MemoryORM.status == MemoryStatusEnum.ACTIVE,
                    MemoryORM.embedding.isnot(None),
                    (1 - distance) >= threshold,
                )
            )
            .order_by(distance)
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_team(
        self,
        team_id: UUID,
        memory_types: Optional[list[MemoryTypeEnum]] = None,
        status: MemoryStatusEnum = MemoryStatusEnum.ACTIVE,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryORM]:
        """Get memories for a team with optional filters.

        Args:
            team_id: Team to get memories for.
            memory_types: Optional filter by types.
            status: Filter by status (default: active).
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of matching memories ordered by last_accessed_at DESC.
        """
        filters = [
            MemoryORM.team_id == team_id,
            MemoryORM.status == status,
        ]
        if memory_types:
            filters.append(MemoryORM.memory_type.in_(memory_types))

        stmt = (
            select(MemoryORM)
            .where(and_(*filters))
            .order_by(MemoryORM.last_accessed_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())
