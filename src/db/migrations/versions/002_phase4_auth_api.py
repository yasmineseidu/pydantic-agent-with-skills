"""Phase 4: Auth + API Foundation - 4 tables.

Revision ID: 002
Revises: 001
Create Date: 2026-02-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # TABLE 1: api_key
    # =========================================================================
    op.create_table(
        "api_key",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("key_hash", name="uq_api_key_hash"),
    )

    # =========================================================================
    # TABLE 2: refresh_token
    # =========================================================================
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("device_info", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )

    # =========================================================================
    # TABLE 3: usage_log
    # =========================================================================
    op.create_table(
        "usage_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent.id"), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id"), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("operation", sa.Text(), nullable=False, server_default=sa.text("'chat'")),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # =========================================================================
    # TABLE 4: audit_log
    # =========================================================================
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("team.id"), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("changes", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # =========================================================================
    # INDEXES
    # =========================================================================

    # --- api_key ---
    op.execute("CREATE INDEX idx_api_key_hash ON api_key (key_hash) WHERE is_active = true")
    op.create_index("idx_api_key_team", "api_key", ["team_id"])

    # --- refresh_token ---
    op.execute(
        "CREATE INDEX idx_refresh_token_user ON refresh_token (user_id) WHERE revoked_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_refresh_token_expiry ON refresh_token (expires_at) "
        "WHERE revoked_at IS NULL"
    )

    # --- usage_log ---
    op.execute("CREATE INDEX idx_usage_team_time ON usage_log (team_id, created_at DESC)")
    op.execute(
        "CREATE INDEX idx_usage_agent ON usage_log (agent_id, created_at DESC) "
        "WHERE agent_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_usage_conversation ON usage_log (conversation_id) "
        "WHERE conversation_id IS NOT NULL"
    )

    # --- audit_log ---
    op.execute("CREATE INDEX idx_audit_team ON audit_log (team_id, created_at DESC)")
    op.execute("CREATE INDEX idx_audit_user ON audit_log (user_id, created_at DESC)")
    op.execute(
        "CREATE INDEX idx_audit_resource ON audit_log (resource_type, resource_id) "
        "WHERE resource_id IS NOT NULL"
    )


def downgrade() -> None:
    # =========================================================================
    # TABLES (reverse order respecting FK dependencies)
    # =========================================================================
    op.drop_table("audit_log")
    op.drop_table("usage_log")
    op.drop_table("refresh_token")
    op.drop_table("api_key")
