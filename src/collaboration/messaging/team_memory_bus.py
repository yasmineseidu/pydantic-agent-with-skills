"""Team memory bus for broadcasting and persisting shared team knowledge."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from src.db.models.memory import MemoryStatusEnum, MemoryTypeEnum

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.repositories.memory_repo import MemoryRepository

logger = logging.getLogger(__name__)

# Deduplication threshold (cosine similarity)
DEDUP_THRESHOLD: float = 0.92


class TeamMemoryBus:
    """Service for broadcasting and persisting team-wide shared memories.

    Manages the flow of knowledge across collaboration sessions:
    - Publishing memories to all session participants
    - Storing team knowledge with deduplication
    - Retrieving recent team context for agents joining sessions

    Uses MemoryRepository for persistence and MemoryType.SHARED for team-scoped memories.

    Attributes:
        _session: AsyncSession for database operations.
        _memory_repo: MemoryRepository for memory storage/retrieval.
    """

    def __init__(
        self,
        session: AsyncSession,
        memory_repo: MemoryRepository,
    ) -> None:
        """Initialize the team memory bus.

        Args:
            session: AsyncSession for database operations.
            memory_repo: MemoryRepository for memory persistence.
        """
        self._session = session
        self._memory_repo = memory_repo

    async def publish_to_team(
        self,
        session_id: UUID,
        team_id: UUID,
        memory_content: str,
        subject: Optional[str] = None,
        importance: int = 5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Broadcast a memory to all participants in a collaboration session.

        Returns memory data for immediate distribution to active session participants.
        Does NOT persist to database (use store_team_knowledge for that).

        Args:
            session_id: ID of the collaboration session.
            team_id: ID of the team.
            memory_content: Content of the memory to broadcast.
            subject: Optional subject/summary.
            importance: Memory importance (1-10).
            metadata: Optional metadata dict.

        Returns:
            List containing a single memory dict for broadcast:
                [{
                    "session_id": UUID,
                    "team_id": UUID,
                    "content": str,
                    "subject": str|None,
                    "importance": int,
                    "metadata": dict
                }]
        """
        logger.info(
            f"publish_to_team: session_id={session_id}, team_id={team_id}, "
            f"importance={importance}"
        )

        memory_dict: dict[str, Any] = {
            "session_id": session_id,
            "team_id": team_id,
            "content": memory_content,
            "subject": subject,
            "importance": importance,
            "metadata": metadata or {},
        }

        return [memory_dict]

    async def store_team_knowledge(
        self,
        team_id: UUID,
        agent_id: Optional[UUID],
        content: str,
        subject: Optional[str] = None,
        importance: int = 5,
        confidence: float = 1.0,
        embedding: Optional[list[float]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Persist shared team knowledge to the memory database with deduplication.

        Creates a MemoryORM record with MemoryType.SHARED. Checks for duplicates
        before storage using embedding similarity.

        Args:
            team_id: ID of the team.
            agent_id: Optional ID of the agent creating the memory.
            content: Memory content to store.
            subject: Optional subject/summary.
            importance: Memory importance (1-10).
            confidence: Confidence score (0.0-1.0).
            embedding: Optional embedding vector for deduplication.
            metadata: Optional metadata dict.

        Returns:
            List of memory dicts (empty if duplicate detected):
                [{
                    "id": UUID,
                    "team_id": UUID,
                    "agent_id": UUID|None,
                    "content": str,
                    "subject": str|None,
                    "importance": int,
                    "memory_type": "shared"
                }]
        """
        logger.info(
            f"store_team_knowledge: team_id={team_id}, agent_id={agent_id}, "
            f"importance={importance}"
        )

        # Deduplication check if embedding provided
        if embedding is not None:
            is_duplicate = await self._deduplicate_memories(team_id, embedding)
            if is_duplicate:
                logger.info(
                    f"store_team_knowledge_duplicate: team_id={team_id}, "
                    "skipping duplicate memory"
                )
                return []

        # Create MemoryORM with SHARED type
        memory_orm = await self._memory_repo.create(
            team_id=team_id,
            agent_id=agent_id,
            user_id=None,
            memory_type=MemoryTypeEnum.SHARED,
            content=content,
            subject=subject,
            importance=importance,
            confidence=confidence,
            tier="warm",
            status=MemoryStatusEnum.ACTIVE,
            embedding=embedding,
            metadata_json=metadata or {},
        )

        logger.info(
            f"team_memory_stored: team_id={team_id}, memory_id={memory_orm.id}, "
            f"importance={importance}"
        )

        # Return memory dict
        memory_dict: dict[str, Any] = {
            "id": memory_orm.id,
            "team_id": memory_orm.team_id,
            "agent_id": memory_orm.agent_id,
            "content": memory_orm.content,
            "subject": memory_orm.subject,
            "importance": memory_orm.importance,
            "memory_type": "shared",
        }

        return [memory_dict]

    async def retrieve_team_context(
        self,
        team_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch recent team memories for agents joining a collaboration session.

        Retrieves SHARED memories for the team to provide context to new participants.

        Args:
            team_id: ID of the team.
            limit: Maximum number of memories to retrieve (default: 50).

        Returns:
            List of memory dicts ordered by recency:
                [{
                    "id": UUID,
                    "team_id": UUID,
                    "agent_id": UUID|None,
                    "content": str,
                    "subject": str|None,
                    "importance": int,
                    "memory_type": "shared",
                    "created_at": datetime
                }]
        """
        logger.info(f"retrieve_team_context: team_id={team_id}, limit={limit}")

        # Fetch SHARED memories for team
        memories = await self._memory_repo.get_by_team(
            team_id=team_id,
            memory_types=[MemoryTypeEnum.SHARED],
            status=MemoryStatusEnum.ACTIVE,
            limit=limit,
            offset=0,
        )

        logger.info(
            f"team_context_retrieved: team_id={team_id}, count={len(memories)}"
        )

        # Convert to dicts
        memory_dicts: list[dict[str, Any]] = []
        for memory in memories:
            memory_dict: dict[str, Any] = {
                "id": memory.id,
                "team_id": memory.team_id,
                "agent_id": memory.agent_id,
                "content": memory.content,
                "subject": memory.subject,
                "importance": memory.importance,
                "memory_type": "shared",
                "created_at": memory.created_at,
            }
            memory_dicts.append(memory_dict)

        return memory_dicts

    async def _deduplicate_memories(
        self,
        team_id: UUID,
        embedding: list[float],
    ) -> bool:
        """Check if a memory with similar content already exists (private helper).

        Uses cosine similarity to detect near-duplicate memories. Threshold is 0.92.

        Args:
            team_id: ID of the team.
            embedding: Embedding vector to compare.

        Returns:
            True if a similar memory exists (duplicate), False otherwise.
        """
        similar_memories = await self._memory_repo.find_similar(
            embedding=embedding,
            team_id=team_id,
            threshold=DEDUP_THRESHOLD,
        )

        if similar_memories:
            logger.debug(
                f"deduplication_check: team_id={team_id}, "
                f"found_similar={len(similar_memories)}"
            )
            return True

        return False
