"""Phase 7: Collaboration ORM models for agent routing and coordination."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.agent import AgentORM
    from src.db.models.conversation import ConversationORM


class ParticipantRoleEnum(str, enum.Enum):
    """Role of an agent participating in a conversation.

    Maps to the ``participant_role`` PostgreSQL enum type.
    """

    PRIMARY = "primary"
    ASSISTANT = "assistant"
    OBSERVER = "observer"


class ConversationParticipantORM(Base, UUIDMixin, TimestampMixin):
    """Tracks which agents are participating in a conversation and their roles.

    Maps to the ``conversation_participant`` table.
    """

    __tablename__ = "conversation_participant"
    __table_args__ = (
        UniqueConstraint("conversation_id", "agent_id", name="uq_participant_conversation_agent"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        Enum(
            ParticipantRoleEnum, name="participant_role", native_enum=True, create_constraint=False
        ),
        nullable=False,
        server_default=text("'primary'"),
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    added_by_agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agent.id"), nullable=True)

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )
    agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[agent_id])
    added_by: Mapped[Optional["AgentORM"]] = relationship(
        "AgentORM", foreign_keys=[added_by_agent_id]
    )


class AgentHandoffORM(Base, UUIDMixin, TimestampMixin):
    """Records when control is handed off from one agent to another.

    Maps to the ``agent_handoff`` table.
    """

    __tablename__ = "agent_handoff"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    to_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context_transferred: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    handoff_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )
    from_agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[from_agent_id])
    to_agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[to_agent_id])


class RoutingDecisionLogORM(Base, UUIDMixin, TimestampMixin):
    """Logs routing decisions made by the MoE router for analysis.

    Maps to the ``routing_decision_log`` table.
    """

    __tablename__ = "routing_decision_log"
    __table_args__ = (Index("idx_routing_decision_scores", "scores", postgresql_using="gin"),)

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    selected_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    routing_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    routing_strategy: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'moe_gate'")
    )
    decision_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )
    selected_agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[selected_agent_id])


class AgentTaskORM(Base, UUIDMixin, TimestampMixin):
    """Tasks delegated from one agent to another with depth tracking.

    Maps to the ``agent_task`` table.
    """

    __tablename__ = "agent_task"
    __table_args__ = (
        CheckConstraint("delegation_depth <= 3", name="ck_task_delegation_depth"),
        CheckConstraint(
            "created_by_agent_id != assigned_to_agent_id", name="ck_task_no_self_assign"
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    created_by_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    assigned_to_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    parent_task_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("agent_task.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    delegation_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )
    created_by: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[created_by_agent_id])
    assigned_to: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[assigned_to_agent_id])
    parent_task: Mapped[Optional["AgentTaskORM"]] = relationship(
        "AgentTaskORM", remote_side="AgentTaskORM.id", foreign_keys=[parent_task_id]
    )


class AgentMessageORM(Base, UUIDMixin, TimestampMixin):
    """Messages sent between agents for coordination and communication.

    Maps to the ``agent_message`` table.
    """

    __tablename__ = "agent_message"
    __table_args__ = (
        Index(
            "idx_message_unread",
            "to_agent_id",
            "read_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    from_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    to_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    message_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'info'"))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )
    from_agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[from_agent_id])
    to_agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[to_agent_id])


class CollaborationSessionORM(Base, UUIDMixin, TimestampMixin):
    """Collaboration session tracking for multi-agent workflows.

    Maps to the ``collaboration_session`` table.
    """

    __tablename__ = "collaboration_session"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    session_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'general'")
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    stage_outputs: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    total_duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", foreign_keys=[conversation_id]
    )


class CollaborationParticipantV2ORM(Base, UUIDMixin, TimestampMixin):
    """Participants in a collaboration session with role and contribution tracking.

    Maps to the ``collaboration_participant_v2`` table.
    """

    __tablename__ = "collaboration_participant_v2"
    __table_args__ = (UniqueConstraint("session_id", "agent_id", name="uq_collab_session_agent"),)

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("collaboration_session.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'participant'"))
    contribution_summary: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_incurred: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))

    # Relationships
    session: Mapped["CollaborationSessionORM"] = relationship(
        "CollaborationSessionORM", foreign_keys=[session_id]
    )
    agent: Mapped["AgentORM"] = relationship("AgentORM", foreign_keys=[agent_id])
