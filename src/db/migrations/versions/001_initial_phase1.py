"""Initial Phase 1: Database Foundation - 9 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # EXTENSIONS
    # =========================================================================
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # =========================================================================
    # ENUM TYPES
    # =========================================================================
    op.execute("CREATE TYPE user_role AS ENUM ('owner', 'admin', 'member', 'viewer')")
    op.execute("CREATE TYPE agent_status AS ENUM ('draft', 'active', 'paused', 'archived')")
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool')")
    op.execute(
        "CREATE TYPE memory_type_enum AS ENUM ("
        "'semantic', 'episodic', 'procedural', 'agent_private', "
        "'shared', 'identity', 'user_profile')"
    )
    op.execute("CREATE TYPE memory_status AS ENUM ('active', 'superseded', 'archived', 'disputed')")
    op.execute("CREATE TYPE memory_tier AS ENUM ('hot', 'warm', 'cold')")
    op.execute(
        "CREATE TYPE memory_source AS ENUM ("
        "'extraction', 'explicit', 'system', 'feedback', 'consolidation', 'compaction')"
    )
    op.execute("CREATE TYPE conversation_status AS ENUM ('active', 'idle', 'closed')")

    # =========================================================================
    # TABLE 1: user
    # =========================================================================
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("email", name="uq_user_email"),
        sa.CheckConstraint(r"email ~* '^[^@]+@[^@]+\.[^@]+$'", name="ck_user_email_format"),
    )

    # =========================================================================
    # TABLE 2: team
    # =========================================================================
    op.create_table(
        "team",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "shared_skill_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column(
            "conversation_retention_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("90"),
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
        sa.UniqueConstraint("slug", name="uq_team_slug"),
        sa.CheckConstraint(r"slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'", name="ck_team_slug_format"),
    )

    # =========================================================================
    # TABLE 3: team_membership
    # =========================================================================
    op.create_table(
        "team_membership",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM(
                "owner", "admin", "member", "viewer", name="user_role", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "team_id", name="uq_team_membership"),
    )

    # =========================================================================
    # TABLE 4: agent
    # =========================================================================
    _model_config_default = (
        '{"model_name": "anthropic/claude-sonnet-4.5",'
        ' "temperature": 0.7,'
        ' "max_output_tokens": 4096}'
    )
    _memory_config_default = (
        '{"token_budget": 2000,'
        ' "auto_extract": true,'
        ' "auto_pin_preferences": true,'
        ' "summarize_interval": 20,'
        ' "retrieval_weights": {'
        ' "semantic": 0.35,'
        ' "recency": 0.20,'
        ' "importance": 0.20,'
        ' "continuity": 0.15,'
        ' "relationship": 0.10'
        " }}"
    )
    _boundaries_default = '{"max_autonomy": "execute", "max_tool_calls_per_turn": 10}'

    op.create_table(
        "agent",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("tagline", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("avatar_emoji", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "personality",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "shared_skill_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "custom_skill_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "disabled_skill_names",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "model_config_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{_model_config_default}'::jsonb"),
        ),
        sa.Column(
            "memory_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{_memory_config_default}'::jsonb"),
        ),
        sa.Column(
            "boundaries",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{_boundaries_default}'::jsonb"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "active", "paused", "archived", name="agent_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
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
        sa.UniqueConstraint("team_id", "slug", name="uq_agent_team_slug"),
        sa.CheckConstraint(r"slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'", name="ck_agent_slug_format"),
    )

    # =========================================================================
    # TABLE 5: conversation
    # =========================================================================
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "idle", "closed", name="conversation_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", sa.Text(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # =========================================================================
    # TABLE 6: message
    # =========================================================================
    op.create_table(
        "message",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent.id"), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(
                "user", "assistant", "system", "tool", name="message_role", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("tool_results", postgresql.JSONB(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("feedback_rating", sa.Text(), nullable=True),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "feedback_rating IN ('positive', 'negative')", name="ck_message_feedback_rating"
        ),
    )

    # =========================================================================
    # TABLE 7: memory
    # =========================================================================
    op.create_table(
        "memory",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("team.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agent.id"), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "memory_type",
            postgresql.ENUM(
                "semantic",
                "episodic",
                "procedural",
                "agent_private",
                "shared",
                "identity",
                "user_profile",
                name="memory_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        # embedding column added via ALTER TABLE below (pgvector type not natively supported)
        sa.Column("importance", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "extraction",
                "explicit",
                "system",
                "feedback",
                "consolidation",
                "compaction",
                name="memory_source",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'extraction'"),
        ),
        sa.Column(
            "source_conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversation.id"),
            nullable=True,
        ),
        sa.Column("source_message_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("extraction_model", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("memory.id"), nullable=True),
        sa.Column("contradicts", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("related_to", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "tier",
            postgresql.ENUM("hot", "warm", "cold", name="memory_tier", create_type=False),
            nullable=False,
            server_default=sa.text("'warm'"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "superseded",
                "archived",
                "disputed",
                name="memory_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'active'"),
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
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("importance BETWEEN 1 AND 10", name="ck_memory_importance"),
        sa.CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_memory_confidence"),
    )

    # Add embedding column (pgvector type not supported by op.create_table)
    op.execute("ALTER TABLE memory ADD COLUMN embedding vector(1536)")

    # =========================================================================
    # TABLE 8: memory_log
    # =========================================================================
    op.create_table(
        "memory_log",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("old_content", sa.Text(), nullable=True),
        sa.Column("new_content", sa.Text(), nullable=True),
        sa.Column("old_importance", sa.Integer(), nullable=True),
        sa.Column("new_importance", sa.Integer(), nullable=True),
        sa.Column("old_tier", sa.Text(), nullable=True),
        sa.Column("new_tier", sa.Text(), nullable=True),
        sa.Column("old_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("related_memory_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # =========================================================================
    # TABLE 9: memory_tag
    # =========================================================================
    op.create_table(
        "memory_tag",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("memory_id", "tag", name="uq_memory_tag"),
    )

    # =========================================================================
    # INDEXES
    # =========================================================================

    # --- user ---
    op.create_index("idx_user_email", "user", ["email"])

    # --- team ---
    op.create_index("idx_team_slug", "team", ["slug"])

    # --- team_membership ---
    op.create_index("idx_membership_user", "team_membership", ["user_id"])
    op.create_index("idx_membership_team", "team_membership", ["team_id", "role"])

    # --- agent ---
    op.create_index("idx_agent_team_status", "agent", ["team_id", "status"])
    op.create_index("idx_agent_team_slug", "agent", ["team_id", "slug"])

    # --- conversation ---
    op.execute("CREATE INDEX idx_conversation_team ON conversation (team_id, created_at DESC)")
    op.execute("CREATE INDEX idx_conversation_user ON conversation (user_id, created_at DESC)")
    op.execute("CREATE INDEX idx_conversation_agent ON conversation (agent_id, created_at DESC)")
    op.execute(
        "CREATE INDEX idx_conversation_status ON conversation (team_id, status) "
        "WHERE status = 'active'"
    )

    # --- message ---
    op.create_index("idx_message_conversation", "message", ["conversation_id", "created_at"])
    op.execute(
        "CREATE INDEX idx_message_feedback ON message (conversation_id) "
        "WHERE feedback_rating IS NOT NULL"
    )

    # --- memory (CRITICAL - most queried table) ---

    # Vector similarity search (IVFFlat)
    op.execute(
        "CREATE INDEX idx_memory_embedding ON memory "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Filtered retrieval
    op.execute(
        "CREATE INDEX idx_memory_team_type_status ON memory (team_id, memory_type, status) "
        "WHERE status IN ('active', 'disputed')"
    )

    # Agent-scoped retrieval
    op.execute(
        "CREATE INDEX idx_memory_agent ON memory (agent_id, memory_type) "
        "WHERE agent_id IS NOT NULL AND status = 'active'"
    )

    # User-profile retrieval
    op.execute(
        "CREATE INDEX idx_memory_user_profile ON memory (team_id, user_id, memory_type) "
        "WHERE memory_type = 'user_profile' AND status = 'active'"
    )

    # Recency signal
    op.execute(
        "CREATE INDEX idx_memory_recency ON memory (team_id, last_accessed_at DESC) "
        "WHERE status = 'active'"
    )

    # Importance signal
    op.execute(
        "CREATE INDEX idx_memory_importance ON memory (team_id, importance DESC) "
        "WHERE status = 'active' AND (is_pinned = TRUE OR importance >= 7)"
    )

    # Conversation continuity
    op.execute(
        "CREATE INDEX idx_memory_conversation ON memory (source_conversation_id) "
        "WHERE source_conversation_id IS NOT NULL"
    )

    # Contradiction lookup
    op.execute(
        "CREATE INDEX idx_memory_subject ON memory (team_id, subject) "
        "WHERE subject IS NOT NULL AND status = 'active'"
    )

    # Tier management
    op.execute(
        "CREATE INDEX idx_memory_tier ON memory (tier, last_accessed_at) WHERE status = 'active'"
    )

    # Expiration
    op.execute(
        "CREATE INDEX idx_memory_expiration ON memory (expires_at) "
        "WHERE expires_at IS NOT NULL AND status = 'active'"
    )

    # --- memory_log ---
    op.create_index("idx_memory_log_memory", "memory_log", ["memory_id", "created_at"])
    op.create_index("idx_memory_log_time", "memory_log", ["created_at"])

    # --- memory_tag ---
    op.create_index("idx_memory_tag_tag", "memory_tag", ["tag"])
    op.create_index("idx_memory_tag_memory", "memory_tag", ["memory_id"])

    # =========================================================================
    # FUNCTIONS
    # =========================================================================

    # Auto-update updated_at timestamp
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Auto-increment conversation stats on new message
    op.execute("""
        CREATE OR REPLACE FUNCTION trigger_update_conversation_stats()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE conversation
            SET message_count = message_count + 1,
                last_message_at = NEW.created_at
            WHERE id = NEW.conversation_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Memory access tracking
    op.execute("""
        CREATE OR REPLACE FUNCTION update_memory_access(memory_ids UUID[])
        RETURNS VOID AS $$
        BEGIN
            UPDATE memory
            SET access_count = access_count + 1,
                last_accessed_at = NOW()
            WHERE id = ANY(memory_ids);
        END;
        $$ LANGUAGE plpgsql
    """)

    # Point-in-time memory reconstruction
    op.execute("""
        CREATE OR REPLACE FUNCTION reconstruct_memory_at(
            p_memory_id UUID,
            p_timestamp TIMESTAMPTZ
        )
        RETURNS TABLE (
            content TEXT,
            importance INT,
            tier TEXT,
            status TEXT,
            as_of TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH ordered_logs AS (
                SELECT
                    ml.new_content,
                    ml.new_importance,
                    ml.new_tier,
                    ml.new_status,
                    ml.created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY ml.memory_id
                        ORDER BY ml.created_at DESC
                    ) AS rn
                FROM memory_log ml
                WHERE ml.memory_id = p_memory_id
                  AND ml.created_at <= p_timestamp
            )
            SELECT
                ol.new_content AS content,
                ol.new_importance AS importance,
                ol.new_tier AS tier,
                ol.new_status AS status,
                ol.created_at AS as_of
            FROM ordered_logs ol
            WHERE ol.rn = 1;
        END;
        $$ LANGUAGE plpgsql
    """)

    # =========================================================================
    # TRIGGERS (Phase 1 only)
    # =========================================================================

    op.execute("""
        CREATE TRIGGER set_updated_at_user
            BEFORE UPDATE ON "user"
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_team
            BEFORE UPDATE ON team
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_agent
            BEFORE UPDATE ON agent
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_conversation
            BEFORE UPDATE ON conversation
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER set_updated_at_memory
            BEFORE UPDATE ON memory
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER update_conversation_on_message
            AFTER INSERT ON message
            FOR EACH ROW EXECUTE FUNCTION trigger_update_conversation_stats()
    """)


def downgrade() -> None:
    # =========================================================================
    # TRIGGERS
    # =========================================================================
    op.execute("DROP TRIGGER IF EXISTS update_conversation_on_message ON message")
    op.execute("DROP TRIGGER IF EXISTS set_updated_at_memory ON memory")
    op.execute("DROP TRIGGER IF EXISTS set_updated_at_conversation ON conversation")
    op.execute("DROP TRIGGER IF EXISTS set_updated_at_agent ON agent")
    op.execute("DROP TRIGGER IF EXISTS set_updated_at_team ON team")
    op.execute('DROP TRIGGER IF EXISTS set_updated_at_user ON "user"')

    # =========================================================================
    # FUNCTIONS
    # =========================================================================
    op.execute("DROP FUNCTION IF EXISTS reconstruct_memory_at")
    op.execute("DROP FUNCTION IF EXISTS update_memory_access")
    op.execute("DROP FUNCTION IF EXISTS trigger_update_conversation_stats")
    op.execute("DROP FUNCTION IF EXISTS trigger_set_updated_at")

    # =========================================================================
    # TABLES (reverse order respecting FK dependencies)
    # =========================================================================
    op.drop_table("memory_tag")
    op.drop_table("memory_log")
    op.drop_table("memory")
    op.drop_table("message")
    op.drop_table("conversation")
    op.drop_table("agent")
    op.drop_table("team_membership")
    op.drop_table("team")
    op.drop_table("user")

    # =========================================================================
    # ENUM TYPES
    # =========================================================================
    op.execute("DROP TYPE IF EXISTS conversation_status")
    op.execute("DROP TYPE IF EXISTS memory_source")
    op.execute("DROP TYPE IF EXISTS memory_tier")
    op.execute("DROP TYPE IF EXISTS memory_status")
    op.execute("DROP TYPE IF EXISTS memory_type_enum")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS agent_status")
    op.execute("DROP TYPE IF EXISTS user_role")
