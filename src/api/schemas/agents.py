"""Agent CRUD schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Create a new agent request.

    Args:
        name: Human-readable agent name (1-100 characters)
        slug: URL-safe identifier (2-50 characters, lowercase alphanumeric with hyphens)
        tagline: Brief agent description (max 200 characters)
        avatar_emoji: Optional emoji avatar (max 10 characters for multi-codepoint emojis)
        personality: AgentPersonality dict (system prompt, tone, verbosity, etc.)
        model_config_data: AgentModelConfig dict (model name, temperature, max tokens, etc.)
        memory_config: AgentMemoryConfig dict (token budget, retrieval weights, etc.)
        boundaries: AgentBoundaries dict (can_do, cannot_do, escalates_to, etc.)
        shared_skill_names: List of team-level skill names to enable
        custom_skill_names: List of agent-specific skill names to enable
    """

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=50)
    tagline: str = Field(default="", max_length=200)
    avatar_emoji: str = Field(default="", max_length=10)
    personality: Optional[dict] = None
    model_config_data: Optional[dict] = None
    memory_config: Optional[dict] = None
    boundaries: Optional[dict] = None
    shared_skill_names: list[str] = Field(default_factory=list)
    custom_skill_names: list[str] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    """Update an existing agent request.

    Args:
        name: Updated human-readable name (1-100 characters)
        tagline: Updated brief description (max 200 characters)
        avatar_emoji: Updated emoji avatar (max 10 characters)
        personality: Updated AgentPersonality dict
        model_config_data: Updated AgentModelConfig dict
        memory_config: Updated AgentMemoryConfig dict
        boundaries: Updated AgentBoundaries dict
        status: Updated agent status (AgentStatus value: "draft", "active", "paused", "archived")
        shared_skill_names: Updated list of team-level skill names
        custom_skill_names: Updated list of agent-specific skill names
        disabled_skill_names: Updated list of skill names to disable

    Note:
        All fields are optional. Only provided fields will be updated.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tagline: Optional[str] = Field(default=None, max_length=200)
    avatar_emoji: Optional[str] = Field(default=None, max_length=10)
    personality: Optional[dict] = None
    model_config_data: Optional[dict] = None
    memory_config: Optional[dict] = None
    boundaries: Optional[dict] = None
    status: Optional[str] = None
    shared_skill_names: Optional[list[str]] = None
    custom_skill_names: Optional[list[str]] = None
    disabled_skill_names: Optional[list[str]] = None


class AgentResponse(BaseModel):
    """Agent representation in API responses.

    Args:
        id: Unique agent identifier
        team_id: ID of the team that owns this agent
        name: Human-readable agent name
        slug: URL-safe identifier
        tagline: Brief agent description
        avatar_emoji: Emoji avatar
        personality: AgentPersonality dict
        shared_skill_names: Team-level skill names enabled for this agent
        custom_skill_names: Agent-specific skill names enabled
        disabled_skill_names: Skill names explicitly disabled for this agent
        model_config_data: AgentModelConfig dict (serialized from model_config_json)
        memory_config: AgentMemoryConfig dict
        boundaries: AgentBoundaries dict
        status: Agent lifecycle status (AgentStatus value)
        created_by: ID of the user who created this agent (None for system agents)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: UUID
    team_id: UUID
    name: str
    slug: str
    tagline: str
    avatar_emoji: str
    personality: dict
    shared_skill_names: list[str]
    custom_skill_names: list[str]
    disabled_skill_names: list[str]
    model_config_data: dict
    memory_config: dict
    boundaries: dict
    status: str
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
