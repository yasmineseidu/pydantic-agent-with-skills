"""Agent ORM model."""

import enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.conversation import ConversationORM
    from src.db.models.user import TeamORM, UserORM


class AgentStatusEnum(str, enum.Enum):
    """Lifecycle status of an agent.

    Maps to the ``agent_status`` PostgreSQL enum type.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


_MODEL_CONFIG_DEFAULT = (
    '{"model_name": "anthropic/claude-sonnet-4.5", "temperature": 0.7, "max_output_tokens": 4096}'
)

_MEMORY_CONFIG_DEFAULT = (
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

_BOUNDARIES_DEFAULT = '{"max_autonomy": "execute", "max_tool_calls_per_turn": 10}'


class AgentORM(Base, UUIDMixin, TimestampMixin):
    """Agent identity and configuration (AgentDNA).

    Each row is a complete agent identity scoped to a team.
    Maps to the ``agent`` table.
    """

    __tablename__ = "agent"
    __table_args__ = (
        UniqueConstraint("team_id", "slug", name="uq_agent_team_slug"),
        CheckConstraint(
            r"slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$'",
            name="ck_agent_slug_format",
        ),
    )

    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)

    # Identity
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    tagline: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    avatar_emoji: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))

    # Personality
    personality: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Skills
    shared_skill_names: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    custom_skill_names: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    disabled_skill_names: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    # Model config (named model_config_json to avoid Pydantic reserved name)
    model_config_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(f"'{_MODEL_CONFIG_DEFAULT}'::jsonb"),
    )

    # Memory config
    memory_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(f"'{_MEMORY_CONFIG_DEFAULT}'::jsonb"),
    )

    # Boundaries
    boundaries: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(f"'{_BOUNDARIES_DEFAULT}'::jsonb"),
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        Enum(AgentStatusEnum, name="agent_status", native_enum=True, create_constraint=False),
        nullable=False,
        server_default=text("'draft'"),
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("user.id"), nullable=True)

    # Relationships
    team: Mapped["TeamORM"] = relationship("TeamORM", back_populates="agents")
    creator: Mapped[Optional["UserORM"]] = relationship("UserORM", foreign_keys=[created_by])
    conversations: Mapped[List["ConversationORM"]] = relationship(
        "ConversationORM", back_populates="agent"
    )
