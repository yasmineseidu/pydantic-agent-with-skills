"""User, Team, and TeamMembership ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.db.models.agent import AgentORM
    from src.db.models.conversation import ConversationORM


class UserRole(str, enum.Enum):
    """Role a user can hold within a team.

    Maps to the ``user_role`` PostgreSQL enum type.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserORM(Base, UUIDMixin, TimestampMixin):
    """Platform user account.

    Each user belongs to one or more teams via TeamMembershipORM.
    Maps to the ``user`` table.
    """

    __tablename__ = "user"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Relationships
    memberships: Mapped[List["TeamMembershipORM"]] = relationship(
        "TeamMembershipORM", back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["ConversationORM"]] = relationship(
        "ConversationORM", back_populates="user"
    )


class TeamORM(Base, UUIDMixin, TimestampMixin):
    """Multi-tenant root entity.

    All data is scoped to a team. Maps to the ``team`` table.
    """

    __tablename__ = "team"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    shared_skill_names: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("90")
    )

    # Relationships
    owner: Mapped["UserORM"] = relationship("UserORM", foreign_keys=[owner_id])
    memberships: Mapped[List["TeamMembershipORM"]] = relationship(
        "TeamMembershipORM", back_populates="team", cascade="all, delete-orphan"
    )
    agents: Mapped[List["AgentORM"]] = relationship(
        "AgentORM", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMembershipORM(Base, UUIDMixin):
    """RBAC join table linking users to teams with a role.

    Maps to the ``team_membership`` table.
    """

    __tablename__ = "team_membership"
    __table_args__ = (UniqueConstraint("user_id", "team_id", name="uq_team_membership"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True, create_constraint=False),
        nullable=False,
        server_default=text("'member'"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["UserORM"] = relationship("UserORM", back_populates="memberships")
    team: Mapped["TeamORM"] = relationship("TeamORM", back_populates="memberships")
