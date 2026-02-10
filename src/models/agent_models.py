"""Pydantic models for agent identity and configuration (AgentDNA)."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


class AgentStatus(str, Enum):
    """Lifecycle status of an agent."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class RetrievalWeights(BaseModel):
    """Weights for 5-signal memory retrieval scoring.

    All weights are floats in [0.0, 1.0] and should sum to 1.0
    for normalized scoring.
    """

    semantic: float = Field(default=0.35, ge=0.0, le=1.0)
    recency: float = Field(default=0.20, ge=0.0, le=1.0)
    importance: float = Field(default=0.20, ge=0.0, le=1.0)
    continuity: float = Field(default=0.15, ge=0.0, le=1.0)
    relationship: float = Field(default=0.10, ge=0.0, le=1.0)


class VoiceExample(BaseModel):
    """A sample interaction that demonstrates the agent's voice.

    Used to capture the agent's tone and style via concrete
    example exchanges.
    """

    user_message: str
    agent_response: str
    context: str = ""


class AgentPersonality(BaseModel):
    """How the agent thinks, speaks, and behaves.

    Contains the system prompt template, communication style settings,
    personality traits, voice examples, and behavioral rules.
    """

    system_prompt_template: str
    tone: Literal[
        "professional",
        "friendly",
        "casual",
        "academic",
        "playful",
        "empathetic",
        "direct",
        "custom",
    ] = "friendly"
    verbosity: Literal["concise", "balanced", "detailed", "verbose"] = "balanced"
    formality: Literal["formal", "semi-formal", "informal", "adaptive"] = "adaptive"
    language: str = "en"
    traits: dict[str, float] = {}
    voice_examples: list[VoiceExample] = []
    always_rules: list[str] = []
    never_rules: list[str] = []
    custom_instructions: str = ""


class AgentModelConfig(BaseModel):
    """LLM configuration per agent.

    Defines the model name, generation parameters, and any
    provider-specific overrides.
    """

    model_name: str = "anthropic/claude-sonnet-4.5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)
    provider_overrides: dict[str, Any] = {}


class AgentMemoryConfig(BaseModel):
    """Memory system configuration per agent.

    Controls token budget, retrieval signal weights, auto-extraction
    behavior, and explicit memory-save trigger phrases.
    """

    token_budget: int = Field(default=2000, ge=100, le=8000)
    retrieval_weights: RetrievalWeights = Field(default_factory=RetrievalWeights)
    auto_extract: bool = True
    auto_pin_preferences: bool = True
    summarize_interval: int = 20
    remember_commands: list[str] = [
        "remember this",
        "don't forget",
        "keep in mind",
        "note that",
    ]


class AgentBoundaries(BaseModel):
    """What the agent can and cannot do.

    Defines explicit capabilities, restrictions, escalation targets,
    autonomy level, domain allowlists, and tool-call limits.
    """

    can_do: list[str] = []
    cannot_do: list[str] = []
    escalates_to: Optional[str] = None
    max_autonomy: Literal["execute", "suggest", "ask"] = "execute"
    allowed_domains: list[str] = []
    max_tool_calls_per_turn: int = Field(default=10, ge=1, le=50)


class AgentDNA(BaseModel):
    """Complete identity document for a named agent.

    Combines identity, personality, skills, model configuration,
    memory settings, behavioral boundaries, and lifecycle status
    into a single portable document.
    """

    # Identity
    id: UUID
    team_id: UUID
    name: str
    slug: str
    tagline: str
    avatar_emoji: str = ""

    # Personality engine
    personality: AgentPersonality

    # Skills
    shared_skill_names: list[str]
    custom_skill_names: list[str]
    disabled_skill_names: list[str]

    # Model configuration
    model: AgentModelConfig

    # Memory configuration
    memory: AgentMemoryConfig

    # Behavioral boundaries
    boundaries: AgentBoundaries

    # Lifecycle
    status: AgentStatus
    created_at: datetime
    updated_at: datetime
    created_by: UUID

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_skills(self) -> list[str]:
        """All skills this agent can use (shared + custom - disabled).

        Returns:
            Deduplicated list of skill names excluding disabled ones.
        """
        return [
            s
            for s in (self.shared_skill_names + self.custom_skill_names)
            if s not in self.disabled_skill_names
        ]
