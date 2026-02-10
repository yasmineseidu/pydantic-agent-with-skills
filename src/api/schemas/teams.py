"""Team management schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    """Create a new team request.

    Args:
        name: Team name (1-100 characters)
        slug: URL-safe identifier (2-50 characters, lowercase alphanumeric with hyphens)
    """

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=50)


class TeamUpdate(BaseModel):
    """Update an existing team request.

    Args:
        name: Updated team name (1-100 characters)
        settings: Updated team settings dict (e.g., {"max_tokens": 8000, "default_model": "..."})
        shared_skill_names: Updated list of team-level skill names

    Note:
        All fields are optional. Only provided fields will be updated.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    settings: Optional[dict] = None
    shared_skill_names: Optional[list[str]] = None


class TeamResponse(BaseModel):
    """Team representation in API responses.

    Args:
        id: Unique team identifier
        name: Team name
        slug: URL-safe identifier
        owner_id: ID of the team owner (user with full admin rights)
        settings: Team settings dict
        shared_skill_names: List of team-level skill names available to all agents
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: UUID
    name: str
    slug: str
    owner_id: UUID
    settings: dict
    shared_skill_names: list[str]
    created_at: datetime
    updated_at: datetime


class MemberAdd(BaseModel):
    """Add a new team member request.

    Args:
        email: Email address of the user to invite (RFC 5322 simplified pattern)
        role: User role in the team (UserRole value: "owner", "admin", "member", "viewer")
    """

    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    role: str = Field(default="member")


class MemberResponse(BaseModel):
    """Team member representation in API responses.

    Args:
        user_id: ID of the user
        team_id: ID of the team
        role: User's role in the team (UserRole value)
        display_name: User's display name
        email: User's email address
        created_at: Membership creation timestamp
    """

    user_id: UUID
    team_id: UUID
    role: str
    display_name: str
    email: str
    created_at: datetime


class UsageSummary(BaseModel):
    """Team usage statistics for a time period.

    Args:
        team_id: ID of the team
        total_input_tokens: Total input tokens consumed
        total_output_tokens: Total output tokens generated
        total_embedding_tokens: Total embedding tokens generated
        estimated_cost_usd: Estimated cost in USD (based on provider pricing)
        request_count: Total number of API requests
        period_start: Start of the reporting period
        period_end: End of the reporting period
    """

    team_id: UUID
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_embedding_tokens: int = 0
    estimated_cost_usd: float = 0.0
    request_count: int = 0
    period_start: datetime
    period_end: datetime
