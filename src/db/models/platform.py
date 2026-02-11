"""ORM models for platform integrations and webhook delivery."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDMixin


class PlatformTypeEnum(str, enum.Enum):
    """Platform types for external integrations.

    Maps to the ``platform_type`` PostgreSQL enum type.
    """

    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"


class PlatformStatusEnum(str, enum.Enum):
    """Platform connection status.

    Maps to the ``platform_status`` PostgreSQL enum type.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class PlatformConnectionORM(Base, UUIDMixin, TimestampMixin):
    """External platform bot connections.

    Maps external bot IDs (Telegram bot token, Slack app) to agents.

    WARNING: ``credentials_json`` stores platform credentials as plaintext JSONB.
    Application-level encryption (e.g. Fernet) is a TODO before production use.

    Maps to the ``platform_connection`` table.
    """

    __tablename__ = "platform_connection"
    __table_args__ = (
        UniqueConstraint("agent_id", "platform", name="uq_platform_agent"),
        Index("idx_platform_team", "team_id", "status"),
        Index("idx_platform_external", "platform", "external_bot_id"),
    )

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    platform: Mapped[str] = mapped_column(
        Enum(PlatformTypeEnum, name="platform_type", native_enum=True, create_constraint=False),
        nullable=False,
    )
    credentials_json: Mapped[dict] = mapped_column(
        "credentials_encrypted",  # Keep DB column name for backwards compat
        JSONB,
        nullable=False,
        doc="Platform credentials. WARNING: stored as plaintext JSONB. App-level encryption TODO.",
    )
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_bot_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(
            PlatformStatusEnum,
            name="platform_status",
            native_enum=True,
            create_constraint=False,
        ),
        nullable=False,
        server_default=text("'active'"),
    )
    last_event_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WebhookDeliveryLogORM(Base, UUIDMixin):
    """Outbound webhook delivery tracking with retry logic.

    Maps to the ``webhook_delivery_log`` table.
    """

    __tablename__ = "webhook_delivery_log"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_webhook_event_id"),
        Index(
            "idx_webhook_pending",
            "next_retry_at",
            postgresql_where=text("delivered_at IS NULL AND failed_at IS NULL"),
        ),
        Index("idx_webhook_team", "team_id", "created_at"),
    )

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
