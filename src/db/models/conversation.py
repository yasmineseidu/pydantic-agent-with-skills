"""Conversation and Message ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.agent import AgentORM
    from src.db.models.user import TeamORM, UserORM


class ConversationStatusEnum(str, enum.Enum):
    """Status of a conversation.

    Maps to the ``conversation_status`` PostgreSQL enum type.
    """

    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


class MessageRoleEnum(str, enum.Enum):
    """Role of a message sender.

    Maps to the ``message_role`` PostgreSQL enum type.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationORM(Base, UUIDMixin, TimestampMixin):
    """A conversation between a user and one or more agents.

    Maps to the ``conversation`` table.
    """

    __tablename__ = "conversation"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(
            ConversationStatusEnum,
            name="conversation_status",
            native_enum=True,
            create_constraint=False,
        ),
        nullable=False,
        server_default=text("'active'"),
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    team: Mapped["TeamORM"] = relationship("TeamORM")
    agent: Mapped["AgentORM"] = relationship("AgentORM", back_populates="conversations")
    user: Mapped["UserORM"] = relationship("UserORM", back_populates="conversations")
    messages: Mapped[List["MessageORM"]] = relationship(
        "MessageORM", back_populates="conversation", cascade="all, delete-orphan"
    )


class MessageORM(Base, UUIDMixin):
    """Individual message within a conversation.

    Messages are immutable -- no updated_at column.
    Maps to the ``message`` table.
    """

    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint(
            "feedback_rating IN ('positive', 'negative')",
            name="ck_message_feedback_rating",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agent.id"), nullable=True)
    role: Mapped[str] = mapped_column(
        Enum(MessageRoleEnum, name="message_role", native_enum=True, create_constraint=False),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_rating: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", back_populates="messages"
    )
