"""Usage and audit log ORM models."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, UUIDMixin


class UsageLogORM(Base, UUIDMixin):
    """Token usage and cost tracking per API call.

    Records input/output/embedding tokens and estimated cost
    for each operation. Maps to the ``usage_log`` table.
    """

    __tablename__ = "usage_log"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agent.id"), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("user.id"), nullable=True)
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("conversation.id"), nullable=True
    )
    request_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    embedding_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    operation: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'chat'"))
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLogORM(Base, UUIDMixin):
    """General system audit trail for compliance.

    Records user actions on resources with before/after changes.
    Maps to the ``audit_log`` table.
    """

    __tablename__ = "audit_log"

    team_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("team.id"), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("user.id"), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[Optional[UUID]] = mapped_column(nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
