"""Scheduled job ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.agent import AgentORM
    from src.db.models.user import TeamORM, UserORM


class ScheduledJobORM(Base, UUIDMixin, TimestampMixin):
    """Scheduled background job for periodic agent execution.

    Each row represents a recurring job that triggers agent runs on a cron schedule.
    Maps to the ``scheduled_job`` table.
    """

    __tablename__ = "scheduled_job"
    __table_args__ = (
        Index("idx_job_next_run", "next_run_at", postgresql_where=text("is_active = true")),
        Index("idx_job_team", "team_id"),
    )

    # Foreign keys
    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    # Job definition
    name: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'UTC'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Execution tracking
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Delivery configuration
    delivery_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Relationships
    team: Mapped["TeamORM"] = relationship("TeamORM")
    agent: Mapped["AgentORM"] = relationship("AgentORM")
    user: Mapped["UserORM"] = relationship("UserORM")
