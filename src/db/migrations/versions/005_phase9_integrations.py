"""Phase 9: Platform integrations (Telegram, Slack webhooks).

Revision ID: 005
Revises: 004
Create Date: 2026-02-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # ENUM: platform_type
    # =========================================================================
    op.execute("CREATE TYPE platform_type AS ENUM ('telegram', 'slack', 'discord', 'whatsapp')")

    # =========================================================================
    # ENUM: platform_status
    # =========================================================================
    op.execute("CREATE TYPE platform_status AS ENUM ('active', 'paused', 'error', 'disconnected')")

    # =========================================================================
    # TABLE: platform_connection
    # =========================================================================
    op.create_table(
        "platform_connection",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            postgresql.ENUM(
                "telegram",
                "slack",
                "discord",
                "whatsapp",
                name="platform_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "credentials_encrypted",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("external_bot_id", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "paused",
                "error",
                "disconnected",
                name="platform_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("agent_id", "platform", name="uq_platform_agent"),
    )

    # =========================================================================
    # TABLE: webhook_delivery_log
    # =========================================================================
    op.create_table(
        "webhook_delivery_log",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column(
            "attempt",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("event_id", name="uq_webhook_event_id"),
    )

    # =========================================================================
    # INDEXES
    # =========================================================================
    op.create_index("idx_platform_team", "platform_connection", ["team_id", "status"])
    op.create_index(
        "idx_platform_external",
        "platform_connection",
        ["platform", "external_bot_id"],
    )

    op.create_index("idx_webhook_team", "webhook_delivery_log", ["team_id", "created_at"])
    op.execute(
        "CREATE INDEX idx_webhook_pending ON webhook_delivery_log (next_retry_at) "
        "WHERE delivered_at IS NULL AND failed_at IS NULL"
    )

    # =========================================================================
    # TRIGGERS (reuses trigger_set_updated_at from migration 001)
    # =========================================================================
    op.execute("""
        CREATE TRIGGER set_updated_at_platform_connection
            BEFORE UPDATE ON platform_connection
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("webhook_delivery_log")
    op.drop_table("platform_connection")

    # Drop enums
    op.execute("DROP TYPE platform_status")
    op.execute("DROP TYPE platform_type")
