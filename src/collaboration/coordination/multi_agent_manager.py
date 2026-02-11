"""Multi-agent collaboration session manager for Phase 7."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.collaboration.models import (
    CollaborationParticipantInfo,
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    ParticipantRole,
)
from src.db.models.collaboration import (
    CollaborationParticipantV2ORM,
    CollaborationSessionORM,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MultiAgentManager:
    """Manages multi-agent collaboration sessions with pattern validation.

    Creates and manages CollaborationSessionORM records for multi-agent
    workflows. Supports supervisor-worker, pipeline, peer review, brainstorm,
    consensus, and delegation patterns. Validates pattern enums and manages
    participant roles.

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize the multi-agent manager.

        Args:
            session: Async SQLAlchemy session for database operations.
        """
        self._session: "AsyncSession" = session

    async def create_collaboration(
        self,
        conversation_id: UUID,
        pattern: CollaborationPattern,
        goal: str,
        initiator_id: UUID,
    ) -> CollaborationSession:
        """Create a new collaboration session with ACTIVE status.

        Args:
            conversation_id: UUID of the conversation this session belongs to.
            pattern: Collaboration pattern being executed.
            goal: Description of the collaboration goal.
            initiator_id: UUID of the agent initiating the session.

        Returns:
            CollaborationSession model with session details.
        """
        # Validate pattern enum
        if not self._validate_pattern(pattern):
            logger.warning(f"create_collaboration_failed: invalid_pattern={pattern}")
            return CollaborationSession(
                id=uuid4(),
                pattern=CollaborationPattern.DELEGATION,
                status=CollaborationStatus.FAILED,
                initiator_id=initiator_id,
                participants=[],
                started_at=datetime.utcnow(),
                metadata={"error": f"Invalid pattern: {pattern}"},
            )

        # Create session ORM
        session_orm = CollaborationSessionORM(
            id=uuid4(),
            conversation_id=conversation_id,
            session_type=pattern.value,
            goal=goal,
            status=CollaborationStatus.ACTIVE.value,
            stage_outputs={},
            total_cost=0.0,
            total_duration_ms=0,
            started_at=datetime.utcnow(),
        )

        self._session.add(session_orm)
        await self._session.flush()

        logger.info(
            f"collaboration_created: session_id={session_orm.id}, pattern={pattern.value}, "
            f"conversation_id={conversation_id}"
        )

        # Return Pydantic model
        return CollaborationSession(
            id=session_orm.id,
            pattern=pattern,
            status=CollaborationStatus.ACTIVE,
            initiator_id=initiator_id,
            participants=[],
            started_at=session_orm.started_at,
            stage_outputs=[],
            metadata={"conversation_id": str(conversation_id), "goal": goal},
        )

    async def add_participants(
        self,
        session_id: UUID,
        participants: list[tuple[UUID, ParticipantRole]],
    ) -> CollaborationSession:
        """Add agents to a collaboration session.

        Args:
            session_id: UUID of the collaboration session.
            participants: List of (agent_id, role) tuples to add.

        Returns:
            Updated CollaborationSession model.
        """
        # Load session ORM
        session_orm = await self._session.get(CollaborationSessionORM, session_id)
        if not session_orm:
            logger.warning(f"add_participants_failed: session_not_found={session_id}")
            return CollaborationSession(
                id=session_id,
                pattern=CollaborationPattern.DELEGATION,
                status=CollaborationStatus.FAILED,
                initiator_id=None,
                participants=[],
                started_at=datetime.utcnow(),
                metadata={"error": "Session not found"},
            )

        # Create participant ORMs
        participant_infos: list[CollaborationParticipantInfo] = []
        for agent_id, role in participants:
            participant_orm = CollaborationParticipantV2ORM(
                id=uuid4(),
                session_id=session_id,
                agent_id=agent_id,
                role=role.value,
                contribution_summary="",
                turn_count=0,
                cost_incurred=0.0,
            )
            self._session.add(participant_orm)

            participant_infos.append(
                CollaborationParticipantInfo(
                    agent_id=agent_id,
                    role=role,
                    joined_at=participant_orm.created_at or datetime.utcnow(),
                    contribution="",
                )
            )

        await self._session.flush()

        logger.info(
            f"participants_added: session_id={session_id}, count={len(participants)}, "
            f"agent_ids={[str(p[0]) for p in participants]}"
        )

        # Return updated session
        return CollaborationSession(
            id=session_orm.id,
            pattern=CollaborationPattern(session_orm.session_type),
            status=CollaborationStatus(session_orm.status),
            initiator_id=None,  # Not stored in ORM
            participants=participant_infos,
            started_at=session_orm.started_at,
            completed_at=session_orm.completed_at,
            stage_outputs=[],
            metadata={"goal": session_orm.goal},
        )

    async def update_session_status(
        self,
        session_id: UUID,
        status: CollaborationStatus,
        final_result: str | None = None,
    ) -> CollaborationSession:
        """Update collaboration session status.

        Args:
            session_id: UUID of the collaboration session.
            status: New status to set (ACTIVE, COMPLETED, FAILED, etc.).
            final_result: Optional final result for completed sessions.

        Returns:
            Updated CollaborationSession model.
        """
        # Load session ORM
        session_orm = await self._session.get(CollaborationSessionORM, session_id)
        if not session_orm:
            logger.warning(f"update_status_failed: session_not_found={session_id}")
            return CollaborationSession(
                id=session_id,
                pattern=CollaborationPattern.DELEGATION,
                status=CollaborationStatus.FAILED,
                initiator_id=None,
                participants=[],
                started_at=datetime.utcnow(),
                metadata={"error": "Session not found"},
            )

        # Update status
        old_status = session_orm.status
        session_orm.status = status.value

        # Set completed_at if transitioning to terminal status
        if status in (
            CollaborationStatus.COMPLETED,
            CollaborationStatus.FAILED,
            CollaborationStatus.TIMED_OUT,
            CollaborationStatus.CANCELLED,
        ):
            if not session_orm.completed_at:
                session_orm.completed_at = datetime.utcnow()

        await self._session.flush()

        logger.info(
            f"session_status_updated: session_id={session_id}, "
            f"old_status={old_status}, new_status={status.value}"
        )

        # Return updated session
        return CollaborationSession(
            id=session_orm.id,
            pattern=CollaborationPattern(session_orm.session_type),
            status=status,
            initiator_id=None,  # Not stored in ORM
            participants=[],
            started_at=session_orm.started_at,
            completed_at=session_orm.completed_at,
            final_result=final_result,
            metadata={"goal": session_orm.goal},
        )

    async def get_active_sessions(
        self,
        conversation_id: UUID | None = None,
    ) -> list[CollaborationSession]:
        """Query ACTIVE collaboration sessions.

        Args:
            conversation_id: Optional filter by conversation ID.

        Returns:
            List of ACTIVE CollaborationSession models.
        """
        from sqlalchemy import select

        # Build query
        stmt = select(CollaborationSessionORM).where(
            CollaborationSessionORM.status == CollaborationStatus.ACTIVE.value
        )

        if conversation_id:
            stmt = stmt.where(CollaborationSessionORM.conversation_id == conversation_id)

        result = await self._session.execute(stmt)
        session_orms = result.scalars().all()

        logger.info(
            f"active_sessions_queried: count={len(session_orms)}, conversation_id={conversation_id}"
        )

        # Convert to Pydantic models
        sessions: list[CollaborationSession] = []
        for orm in session_orms:
            sessions.append(
                CollaborationSession(
                    id=orm.id,
                    pattern=CollaborationPattern(orm.session_type),
                    status=CollaborationStatus(orm.status),
                    initiator_id=None,  # Not stored in ORM
                    participants=[],
                    started_at=orm.started_at,
                    completed_at=orm.completed_at,
                    metadata={"goal": orm.goal},
                )
            )

        return sessions

    def _validate_pattern(self, pattern: CollaborationPattern) -> bool:
        """Validate that pattern is a valid CollaborationPattern enum value.

        Args:
            pattern: Pattern to validate.

        Returns:
            True if valid, False otherwise.
        """
        try:
            # Check if pattern is in enum values
            return pattern in CollaborationPattern
        except (ValueError, TypeError):
            return False
