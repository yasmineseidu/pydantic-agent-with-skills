"""Pydantic models for users, teams, and team memberships."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """Role of a user within a team (RBAC)."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserCreate(BaseModel):
    """Request model for creating a user.

    Password is accepted as plaintext and must be hashed (bcrypt,
    min 12 rounds) before storage.
    """

    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str


class UserRecord(BaseModel):
    """Full user record as returned from the database.

    Password hash is included for auth verification but must
    never be serialized to API responses.
    """

    id: UUID
    email: str
    password_hash: str = Field(exclude=True)
    display_name: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class TeamCreate(BaseModel):
    """Request model for creating a team.

    Slug must be URL-safe and unique across the platform.
    """

    name: str
    slug: str
    owner_id: UUID


class TeamRecord(BaseModel):
    """Full team record as returned from the database.

    Includes settings, shared skills, webhook config, and
    data retention settings.
    """

    id: UUID
    name: str
    slug: str
    owner_id: UUID
    settings: dict[str, Any] = Field(default_factory=dict)
    shared_skill_names: list[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    conversation_retention_days: int = 90
    created_at: datetime
    updated_at: datetime


class TeamMembershipCreate(BaseModel):
    """Request model for adding a user to a team.

    Unique constraint on (user_id, team_id) is enforced at the
    database level.
    """

    user_id: UUID
    team_id: UUID
    role: UserRole = UserRole.MEMBER


class TeamMembershipRecord(BaseModel):
    """Full team membership record as returned from the database."""

    id: UUID
    user_id: UUID
    team_id: UUID
    role: UserRole
    created_at: datetime
