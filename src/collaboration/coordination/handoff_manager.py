"""Agent handoff coordination with delegation depth enforcement."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import func, select

from src.collaboration.models import HandoffResult, MAX_DELEGATION_DEPTH
from src.db.models.collaboration import AgentHandoffORM, RoutingDecisionLogORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class HandoffManager:
    """Manages agent-to-agent handoffs with delegation depth tracking.

    Coordinates the transfer of conversation control from one agent to another,
    enforcing the MAX_DELEGATION_DEPTH limit to prevent infinite delegation
    chains. All handoffs are logged to AgentHandoffORM and routing decisions
    are recorded to RoutingDecisionLogORM for analytics.

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize HandoffManager.

        Args:
            session: Async SQLAlchemy session for database operations.
        """
        self._session: "AsyncSession" = session

    async def initiate_handoff(
        self,
        conversation_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        reason: str,
        context_transferred: dict,
    ) -> HandoffResult:
        """Initiate a handoff from one agent to another.

        Validates that the delegation depth limit has not been exceeded,
        creates an AgentHandoffORM record, and logs the routing decision.

        Args:
            conversation_id: UUID of the conversation being handed off.
            from_agent_id: UUID of the agent initiating the handoff.
            to_agent_id: UUID of the agent receiving the handoff.
            reason: Human-readable reason for the handoff.
            context_transferred: Dictionary of context data transferred to new agent.

        Returns:
            HandoffResult indicating success or failure with error details.
        """
        # Validate delegation depth
        is_valid, error_message = await self._validate_handoff(conversation_id, from_agent_id)
        if not is_valid:
            logger.warning(
                f"handoff_rejected: conversation_id={conversation_id}, "
                f"from={from_agent_id}, to={to_agent_id}, reason={error_message}"
            )
            return HandoffResult(
                target_agent_id=to_agent_id,
                success=False,
                context_transferred="",
                reason=error_message or "Validation failed",
            )

        # Create handoff record
        handoff = AgentHandoffORM(
            conversation_id=conversation_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            reason=reason,
            context_transferred=context_transferred,
            handoff_at=datetime.utcnow(),
        )
        self._session.add(handoff)

        # Log routing decision
        await self._log_handoff_decision(
            conversation_id=conversation_id,
            user_message=reason,
            selected_agent_id=to_agent_id,
            from_agent_id=from_agent_id,
        )

        logger.info(
            f"handoff_initiated: conversation_id={conversation_id}, "
            f"from={from_agent_id}, to={to_agent_id}"
        )

        return HandoffResult(
            target_agent_id=to_agent_id,
            success=True,
            context_transferred=str(context_transferred),
            reason=reason,
        )

    async def complete_handoff(
        self,
        conversation_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        result_summary: str,
    ) -> None:
        """Mark a handoff as complete with result summary.

        This is called after the receiving agent has successfully taken over
        the conversation. The result summary is logged for analytics.

        Args:
            conversation_id: UUID of the conversation.
            from_agent_id: UUID of the agent that initiated the handoff.
            to_agent_id: UUID of the agent that received the handoff.
            result_summary: Summary of the handoff outcome.
        """
        logger.info(
            f"handoff_completed: conversation_id={conversation_id}, "
            f"from={from_agent_id}, to={to_agent_id}, result={result_summary[:100]}"
        )

    async def get_handoff_history(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[AgentHandoffORM]:
        """Retrieve handoff history for a conversation.

        Returns the most recent handoffs in reverse chronological order
        (newest first).

        Args:
            conversation_id: UUID of the conversation to query.
            limit: Maximum number of handoffs to return.

        Returns:
            List of AgentHandoffORM records, newest first.
        """
        stmt = (
            select(AgentHandoffORM)
            .where(AgentHandoffORM.conversation_id == conversation_id)
            .order_by(AgentHandoffORM.handoff_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        handoffs = list(result.scalars().all())

        logger.info(
            f"handoff_history_retrieved: conversation_id={conversation_id}, count={len(handoffs)}"
        )
        return handoffs

    async def _validate_handoff(
        self,
        conversation_id: UUID,
        from_agent_id: UUID,
    ) -> tuple[bool, Optional[str]]:
        """Validate that a handoff can proceed.

        Checks that the delegation depth does not exceed MAX_DELEGATION_DEPTH.
        The depth is the number of handoffs in this conversation chain.

        Args:
            conversation_id: UUID of the conversation.
            from_agent_id: UUID of the agent initiating the handoff.

        Returns:
            Tuple of (is_valid, error_message).
                is_valid is True if handoff can proceed.
                error_message is None if valid, or an error string if invalid.
        """
        # Count existing handoffs in this conversation
        stmt = (
            select(func.count())
            .select_from(AgentHandoffORM)
            .where(AgentHandoffORM.conversation_id == conversation_id)
        )
        result = await self._session.execute(stmt)
        handoff_count = result.scalar() or 0

        if handoff_count >= MAX_DELEGATION_DEPTH:
            error_msg = (
                f"Error: Maximum delegation depth ({MAX_DELEGATION_DEPTH}) exceeded. "
                f"Current depth: {handoff_count}"
            )
            return (False, error_msg)

        return (True, None)

    async def _log_handoff_decision(
        self,
        conversation_id: UUID,
        user_message: str,
        selected_agent_id: UUID,
        from_agent_id: UUID,
    ) -> None:
        """Log the handoff routing decision for analytics.

        Creates a RoutingDecisionLogORM record capturing the handoff decision.
        This enables analysis of handoff patterns and routing confidence.

        Args:
            conversation_id: UUID of the conversation.
            user_message: The reason or context for the handoff.
            selected_agent_id: UUID of the agent selected to receive the handoff.
            from_agent_id: UUID of the agent initiating the handoff.
        """
        decision_log = RoutingDecisionLogORM(
            conversation_id=conversation_id,
            user_message=user_message[:1000],  # Truncate long messages
            selected_agent_id=selected_agent_id,
            scores={"from_agent_id": str(from_agent_id), "handoff": True},
            routing_confidence=1.0,  # Handoffs are explicit, so confidence is 100%
            routing_strategy="handoff",
            decision_time_ms=0,  # Handoffs are synchronous, no routing latency
        )
        self._session.add(decision_log)

        logger.debug(
            f"handoff_decision_logged: conversation_id={conversation_id}, "
            f"selected_agent_id={selected_agent_id}"
        )
