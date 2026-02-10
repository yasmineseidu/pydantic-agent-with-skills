"""Agent message bus service for inter-agent communication in Phase 7."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import select

from src.collaboration.models import AgentMessage, AgentMessageType
from src.db.models.collaboration import AgentMessageORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentMessageBus:
    """Service for managing inter-agent messages and communication.

    Handles sending messages between agents, retrieving pending messages,
    marking messages as read, and fetching conversation history.

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize the message bus with a database session.

        Args:
            session: Async SQLAlchemy session for database operations.
        """
        self._session = session

    async def send_message(
        self,
        conversation_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        message_type: AgentMessageType,
        subject: str,
        body: str,
        metadata: Optional[dict] = None,
    ) -> Optional[AgentMessage]:
        """Send a message from one agent to another.

        Creates an AgentMessageORM record and returns the created message
        as an AgentMessage Pydantic model.

        Args:
            conversation_id: UUID of the conversation context.
            from_agent_id: UUID of the sending agent.
            to_agent_id: UUID of the receiving agent.
            message_type: Type of message (from AgentMessageType enum).
            subject: Message subject line.
            body: Message body content.
            metadata: Optional metadata dictionary (default: empty dict).

        Returns:
            AgentMessage model if successful, None if creation fails.

        Raises:
            No exceptions raised - returns None on error.
        """
        try:
            # Validate message type
            if not self._validate_message_type(message_type):
                logger.warning(
                    f"send_message_invalid_type: from={from_agent_id}, to={to_agent_id}, "
                    f"type={message_type}"
                )
                return None

            # Create ORM instance
            message_orm = AgentMessageORM(
                conversation_id=conversation_id,
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                message_type=message_type.value,
                subject=subject,
                body=body,
                metadata_json=metadata or {},
                read_at=None,
            )

            self._session.add(message_orm)
            await self._session.flush()
            await self._session.refresh(message_orm)

            logger.info(
                f"message_sent: from={from_agent_id}, to={to_agent_id}, "
                f"type={message_type.value}, id={message_orm.id}"
            )

            # Convert to Pydantic model
            return AgentMessage(
                id=message_orm.id,
                message_type=AgentMessageType(message_orm.message_type),
                sender_id=message_orm.from_agent_id,
                recipient_id=message_orm.to_agent_id,
                content=message_orm.body,
                timestamp=message_orm.created_at,
                metadata=message_orm.metadata_json,
            )

        except Exception as e:
            logger.error(
                f"send_message_error: from={from_agent_id}, to={to_agent_id}, error={str(e)}"
            )
            return None

    async def get_pending_messages(
        self,
        agent_id: UUID,
        conversation_id: Optional[UUID] = None,
    ) -> list[AgentMessage]:
        """Retrieve all unread messages for a specific agent.

        Args:
            agent_id: UUID of the agent to fetch messages for.
            conversation_id: Optional conversation UUID to filter by.

        Returns:
            List of AgentMessage models (unread messages only).
            Returns empty list if no pending messages or on error.

        Raises:
            No exceptions raised - returns empty list on error.
        """
        try:
            stmt = select(AgentMessageORM).where(
                AgentMessageORM.to_agent_id == agent_id,
                AgentMessageORM.read_at.is_(None),
            )

            if conversation_id:
                stmt = stmt.where(AgentMessageORM.conversation_id == conversation_id)

            stmt = stmt.order_by(AgentMessageORM.created_at.asc())

            result = await self._session.execute(stmt)
            messages_orm = result.scalars().all()

            logger.info(
                f"get_pending_messages: agent_id={agent_id}, "
                f"conversation_id={conversation_id}, count={len(messages_orm)}"
            )

            # Convert to Pydantic models
            return [
                AgentMessage(
                    id=msg.id,
                    message_type=AgentMessageType(msg.message_type),
                    sender_id=msg.from_agent_id,
                    recipient_id=msg.to_agent_id,
                    content=msg.body,
                    timestamp=msg.created_at,
                    metadata=msg.metadata_json,
                )
                for msg in messages_orm
            ]

        except Exception as e:
            logger.error(f"get_pending_messages_error: agent_id={agent_id}, error={str(e)}")
            return []

    async def mark_as_read(
        self,
        message_id: UUID,
    ) -> bool:
        """Mark a message as read by updating the read_at timestamp.

        Args:
            message_id: UUID of the message to mark as read.

        Returns:
            True if message was marked as read, False if message not found or already read.

        Raises:
            No exceptions raised - returns False on error.
        """
        try:
            stmt = select(AgentMessageORM).where(
                AgentMessageORM.id == message_id,
                AgentMessageORM.read_at.is_(None),
            )

            result = await self._session.execute(stmt)
            message_orm = result.scalar_one_or_none()

            if not message_orm:
                logger.warning(f"mark_as_read_not_found: message_id={message_id}")
                return False

            message_orm.read_at = datetime.now()
            await self._session.flush()

            logger.info(f"message_marked_read: message_id={message_id}")
            return True

        except Exception as e:
            logger.error(f"mark_as_read_error: message_id={message_id}, error={str(e)}")
            return False

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentMessage]:
        """Fetch all messages for a conversation with pagination.

        Args:
            conversation_id: UUID of the conversation.
            limit: Maximum number of messages to return (default: 50).
            offset: Number of messages to skip for pagination (default: 0).

        Returns:
            List of AgentMessage models in chronological order.
            Returns empty list if no messages or on error.

        Raises:
            No exceptions raised - returns empty list on error.
        """
        try:
            stmt = (
                select(AgentMessageORM)
                .where(AgentMessageORM.conversation_id == conversation_id)
                .order_by(AgentMessageORM.created_at.asc())
                .limit(limit)
                .offset(offset)
            )

            result = await self._session.execute(stmt)
            messages_orm = result.scalars().all()

            logger.info(
                f"get_conversation_messages: conversation_id={conversation_id}, "
                f"count={len(messages_orm)}, limit={limit}, offset={offset}"
            )

            # Convert to Pydantic models
            return [
                AgentMessage(
                    id=msg.id,
                    message_type=AgentMessageType(msg.message_type),
                    sender_id=msg.from_agent_id,
                    recipient_id=msg.to_agent_id,
                    content=msg.body,
                    timestamp=msg.created_at,
                    metadata=msg.metadata_json,
                )
                for msg in messages_orm
            ]

        except Exception as e:
            logger.error(
                f"get_conversation_messages_error: conversation_id={conversation_id}, error={str(e)}"
            )
            return []

    def _validate_message_type(self, message_type: AgentMessageType) -> bool:
        """Validate that the message type is a valid AgentMessageType enum value.

        Args:
            message_type: Message type to validate.

        Returns:
            True if valid AgentMessageType, False otherwise.
        """
        try:
            return isinstance(message_type, AgentMessageType)
        except Exception:
            return False
