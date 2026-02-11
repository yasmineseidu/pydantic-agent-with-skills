"""Phase 7: Agent collaboration tables for routing, handoff, and coordination.

Revision ID: 004
Revises: 003
Create Date: 2026-02-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # ENUM: participant_role
    # =========================================================================
    op.execute("CREATE TYPE participant_role AS ENUM ('primary', 'assistant', 'observer')")

    # =========================================================================
    # TABLE: conversation_participant
    # =========================================================================
    op.create_table(
        "conversation_participant",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM("primary", "assistant", "observer", name="participant_role"),
            nullable=False,
            server_default=sa.text("'primary'"),
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "added_by_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id"),
            nullable=True,
        ),
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
        sa.UniqueConstraint(
            "conversation_id", "agent_id", name="uq_participant_conversation_agent"
        ),
    )

    # =========================================================================
    # TABLE: agent_handoff
    # =========================================================================
    op.create_table(
        "agent_handoff",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "context_transferred",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "handoff_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
    )

    # =========================================================================
    # TABLE: routing_decision_log
    # =========================================================================
    op.create_table(
        "routing_decision_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column(
            "selected_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scores",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("routing_confidence", sa.Float(), nullable=False),
        sa.Column(
            "routing_strategy",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'moe_gate'"),
        ),
        sa.Column(
            "decision_time_ms",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
    )

    # =========================================================================
    # TABLE: agent_task
    # =========================================================================
    op.create_table(
        "agent_task",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_task_id",
            sa.Uuid(),
            sa.ForeignKey("agent_task.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("delegation_depth", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("delegation_depth <= 3", name="ck_task_delegation_depth"),
        sa.CheckConstraint(
            "created_by_agent_id != assigned_to_agent_id", name="ck_task_no_self_assign"
        ),
    )

    # =========================================================================
    # TABLE: agent_message
    # =========================================================================
    op.create_table(
        "agent_message",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_type", sa.Text(), nullable=False, server_default=sa.text("'info'")),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    # =========================================================================
    # TABLE: collaboration_session
    # =========================================================================
    op.create_table(
        "collaboration_session",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_type", sa.Text(), nullable=False, server_default=sa.text("'general'")),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "stage_outputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("total_cost", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("total_duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    # =========================================================================
    # TABLE: collaboration_participant_v2
    # =========================================================================
    op.create_table(
        "collaboration_participant_v2",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("collaboration_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'participant'")),
        sa.Column(
            "contribution_summary",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_incurred", sa.Float(), nullable=False, server_default=sa.text("0.0")),
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
        sa.UniqueConstraint("session_id", "agent_id", name="uq_collab_session_agent"),
    )

    # =========================================================================
    # INDEXES
    # =========================================================================
    op.create_index("idx_participant_conversation", "conversation_participant", ["conversation_id"])
    op.create_index("idx_participant_agent", "conversation_participant", ["agent_id"])

    op.create_index("idx_handoff_conversation", "agent_handoff", ["conversation_id"])
    op.create_index("idx_handoff_from_agent", "agent_handoff", ["from_agent_id"])
    op.create_index("idx_handoff_to_agent", "agent_handoff", ["to_agent_id"])

    op.create_index("idx_routing_conversation", "routing_decision_log", ["conversation_id"])
    op.create_index("idx_routing_agent", "routing_decision_log", ["selected_agent_id"])
    op.execute(
        "CREATE INDEX idx_routing_decision_scores ON routing_decision_log USING gin (scores)"
    )

    op.create_index("idx_task_conversation", "agent_task", ["conversation_id"])
    op.create_index("idx_task_created_by", "agent_task", ["created_by_agent_id"])
    op.create_index("idx_task_assigned_to", "agent_task", ["assigned_to_agent_id"])
    op.create_index("idx_task_parent", "agent_task", ["parent_task_id"])

    op.create_index("idx_agent_message_conversation", "agent_message", ["conversation_id"])
    op.create_index("idx_message_from_agent", "agent_message", ["from_agent_id"])
    op.create_index("idx_message_to_agent", "agent_message", ["to_agent_id"])
    op.execute(
        "CREATE INDEX idx_message_unread ON agent_message (to_agent_id, read_at) WHERE read_at IS NULL"
    )

    op.create_index("idx_collab_session_conversation", "collaboration_session", ["conversation_id"])

    op.create_index(
        "idx_collab_participant_session", "collaboration_participant_v2", ["session_id"]
    )
    op.create_index("idx_collab_participant_agent", "collaboration_participant_v2", ["agent_id"])

    # =========================================================================
    # TRIGGERS (reuses trigger_set_updated_at from migration 001)
    # =========================================================================
    op.execute("""
        CREATE TRIGGER set_updated_at_conversation_participant
            BEFORE UPDATE ON conversation_participant
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_agent_handoff
            BEFORE UPDATE ON agent_handoff
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_routing_decision_log
            BEFORE UPDATE ON routing_decision_log
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_agent_task
            BEFORE UPDATE ON agent_task
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_agent_message
            BEFORE UPDATE ON agent_message
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_collaboration_session
            BEFORE UPDATE ON collaboration_session
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_collaboration_participant_v2
            BEFORE UPDATE ON collaboration_participant_v2
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("collaboration_participant_v2")
    op.drop_table("collaboration_session")
    op.drop_table("agent_message")
    op.drop_table("agent_task")
    op.drop_table("routing_decision_log")
    op.drop_table("agent_handoff")
    op.drop_table("conversation_participant")

    # Drop enum
    op.execute("DROP TYPE participant_role")
