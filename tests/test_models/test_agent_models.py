"""Unit tests for agent identity and configuration models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.agent_models import (
    AgentBoundaries,
    AgentDNA,
    AgentMemoryConfig,
    AgentModelConfig,
    AgentPersonality,
    AgentStatus,
    RetrievalWeights,
    VoiceExample,
)


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    @pytest.mark.unit
    def test_agent_status_values(self) -> None:
        """Test that all 4 enum values exist."""
        assert AgentStatus.DRAFT == "draft"
        assert AgentStatus.ACTIVE == "active"
        assert AgentStatus.PAUSED == "paused"
        assert AgentStatus.ARCHIVED == "archived"
        assert len(AgentStatus) == 4


class TestRetrievalWeights:
    """Tests for RetrievalWeights model."""

    @pytest.mark.unit
    def test_retrieval_weights_defaults(self) -> None:
        """Test that default weights match spec (0.35, 0.20, 0.20, 0.15, 0.10)."""
        weights = RetrievalWeights()
        assert weights.semantic == 0.35
        assert weights.recency == 0.20
        assert weights.importance == 0.20
        assert weights.continuity == 0.15
        assert weights.relationship == 0.10

    @pytest.mark.unit
    def test_retrieval_weights_constraints_valid(self) -> None:
        """Test that boundary values 0.0 and 1.0 are accepted."""
        weights = RetrievalWeights(
            semantic=0.0, recency=0.0, importance=0.0, continuity=0.0, relationship=1.0
        )
        assert weights.semantic == 0.0
        assert weights.relationship == 1.0

    @pytest.mark.unit
    def test_retrieval_weights_constraints_too_low(self) -> None:
        """Test that values below 0.0 raise ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalWeights(semantic=-0.1)

    @pytest.mark.unit
    def test_retrieval_weights_constraints_too_high(self) -> None:
        """Test that values above 1.0 raise ValidationError."""
        with pytest.raises(ValidationError):
            RetrievalWeights(recency=1.1)


class TestVoiceExample:
    """Tests for VoiceExample model."""

    @pytest.mark.unit
    def test_voice_example_creation(self) -> None:
        """Test basic creation with required and optional fields."""
        example = VoiceExample(
            user_message="Hello",
            agent_response="Hi there!",
            context="greeting",
        )
        assert example.user_message == "Hello"
        assert example.agent_response == "Hi there!"
        assert example.context == "greeting"

    @pytest.mark.unit
    def test_voice_example_default_context(self) -> None:
        """Test that context defaults to empty string."""
        example = VoiceExample(user_message="Hi", agent_response="Hey")
        assert example.context == ""


class TestAgentPersonality:
    """Tests for AgentPersonality model."""

    @pytest.mark.unit
    def test_agent_personality_defaults(self) -> None:
        """Test default values: tone=friendly, verbosity=balanced, etc."""
        personality = AgentPersonality(system_prompt_template="You are a helpful agent.")
        assert personality.tone == "friendly"
        assert personality.verbosity == "balanced"
        assert personality.formality == "adaptive"
        assert personality.language == "en"
        assert personality.traits == {}
        assert personality.voice_examples == []
        assert personality.always_rules == []
        assert personality.never_rules == []
        assert personality.custom_instructions == ""

    @pytest.mark.unit
    def test_agent_personality_missing_required(self) -> None:
        """Test that missing system_prompt_template raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentPersonality()


class TestAgentModelConfig:
    """Tests for AgentModelConfig model."""

    @pytest.mark.unit
    def test_agent_model_config_defaults(self) -> None:
        """Test default model_name and temperature=0.7."""
        config = AgentModelConfig()
        assert config.model_name == "anthropic/claude-sonnet-4.5"
        assert config.temperature == 0.7
        assert config.max_output_tokens == 4096
        assert config.provider_overrides == {}

    @pytest.mark.unit
    def test_agent_model_config_temperature_boundary_low(self) -> None:
        """Test that temperature=0.0 is valid."""
        config = AgentModelConfig(temperature=0.0)
        assert config.temperature == 0.0

    @pytest.mark.unit
    def test_agent_model_config_temperature_boundary_high(self) -> None:
        """Test that temperature=2.0 is valid."""
        config = AgentModelConfig(temperature=2.0)
        assert config.temperature == 2.0

    @pytest.mark.unit
    def test_agent_model_config_temperature_too_high(self) -> None:
        """Test that temperature > 2.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentModelConfig(temperature=2.1)

    @pytest.mark.unit
    def test_agent_model_config_temperature_too_low(self) -> None:
        """Test that temperature < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentModelConfig(temperature=-0.1)

    @pytest.mark.unit
    def test_agent_model_config_max_tokens_boundary_low(self) -> None:
        """Test that max_output_tokens=100 is valid."""
        config = AgentModelConfig(max_output_tokens=100)
        assert config.max_output_tokens == 100

    @pytest.mark.unit
    def test_agent_model_config_max_tokens_boundary_high(self) -> None:
        """Test that max_output_tokens=32000 is valid."""
        config = AgentModelConfig(max_output_tokens=32000)
        assert config.max_output_tokens == 32000

    @pytest.mark.unit
    def test_agent_model_config_max_tokens_too_low(self) -> None:
        """Test that max_output_tokens < 100 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentModelConfig(max_output_tokens=99)

    @pytest.mark.unit
    def test_agent_model_config_max_tokens_too_high(self) -> None:
        """Test that max_output_tokens > 32000 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentModelConfig(max_output_tokens=32001)


class TestAgentMemoryConfig:
    """Tests for AgentMemoryConfig model."""

    @pytest.mark.unit
    def test_agent_memory_config_defaults(self) -> None:
        """Test defaults: token_budget=2000, auto_extract=True."""
        config = AgentMemoryConfig()
        assert config.token_budget == 2000
        assert config.auto_extract is True
        assert config.auto_pin_preferences is True
        assert config.summarize_interval == 20
        assert isinstance(config.retrieval_weights, RetrievalWeights)
        assert len(config.remember_commands) == 4

    @pytest.mark.unit
    def test_agent_memory_config_token_budget_boundary(self) -> None:
        """Test that token_budget boundaries 100 and 8000 are valid."""
        low = AgentMemoryConfig(token_budget=100)
        high = AgentMemoryConfig(token_budget=8000)
        assert low.token_budget == 100
        assert high.token_budget == 8000

    @pytest.mark.unit
    def test_agent_memory_config_token_budget_too_low(self) -> None:
        """Test that token_budget < 100 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentMemoryConfig(token_budget=99)


class TestAgentBoundaries:
    """Tests for AgentBoundaries model."""

    @pytest.mark.unit
    def test_agent_boundaries_defaults(self) -> None:
        """Test defaults: max_autonomy=execute, max_tool_calls=10."""
        boundaries = AgentBoundaries()
        assert boundaries.max_autonomy == "execute"
        assert boundaries.max_tool_calls_per_turn == 10
        assert boundaries.can_do == []
        assert boundaries.cannot_do == []
        assert boundaries.escalates_to is None
        assert boundaries.allowed_domains == []

    @pytest.mark.unit
    def test_agent_boundaries_tool_calls_boundary(self) -> None:
        """Test that max_tool_calls_per_turn boundaries 1 and 50 are valid."""
        low = AgentBoundaries(max_tool_calls_per_turn=1)
        high = AgentBoundaries(max_tool_calls_per_turn=50)
        assert low.max_tool_calls_per_turn == 1
        assert high.max_tool_calls_per_turn == 50

    @pytest.mark.unit
    def test_agent_boundaries_tool_calls_too_low(self) -> None:
        """Test that max_tool_calls_per_turn < 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentBoundaries(max_tool_calls_per_turn=0)

    @pytest.mark.unit
    def test_agent_boundaries_tool_calls_too_high(self) -> None:
        """Test that max_tool_calls_per_turn > 50 raises ValidationError."""
        with pytest.raises(ValidationError):
            AgentBoundaries(max_tool_calls_per_turn=51)


def _make_agent_dna(**overrides: object) -> AgentDNA:
    """Create a minimal valid AgentDNA for tests.

    Args:
        **overrides: Field overrides applied on top of defaults.

    Returns:
        A fully populated AgentDNA instance.
    """
    now = datetime.now(tz=timezone.utc)
    defaults: dict[str, object] = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "Test Agent",
        "slug": "test-agent",
        "tagline": "A test agent",
        "personality": AgentPersonality(system_prompt_template="You are a test agent."),
        "shared_skill_names": ["search", "calendar"],
        "custom_skill_names": ["private_tool"],
        "disabled_skill_names": ["calendar"],
        "model": AgentModelConfig(),
        "memory": AgentMemoryConfig(),
        "boundaries": AgentBoundaries(),
        "status": AgentStatus.ACTIVE,
        "created_at": now,
        "updated_at": now,
        "created_by": uuid4(),
    }
    defaults.update(overrides)
    return AgentDNA(**defaults)  # type: ignore[arg-type]


class TestAgentDNA:
    """Tests for AgentDNA model."""

    @pytest.mark.unit
    def test_agent_dna_creation(self) -> None:
        """Test creating a full AgentDNA with all fields."""
        dna = _make_agent_dna()
        assert dna.name == "Test Agent"
        assert dna.slug == "test-agent"
        assert dna.status == AgentStatus.ACTIVE

    @pytest.mark.unit
    def test_agent_dna_effective_skills(self) -> None:
        """Test computed property: shared + custom - disabled."""
        dna = _make_agent_dna(
            shared_skill_names=["search", "calendar"],
            custom_skill_names=["private_tool"],
            disabled_skill_names=["calendar"],
        )
        assert dna.effective_skills == ["search", "private_tool"]

    @pytest.mark.unit
    def test_agent_dna_effective_skills_empty(self) -> None:
        """Test edge case: all empty lists yields empty effective_skills."""
        dna = _make_agent_dna(
            shared_skill_names=[],
            custom_skill_names=[],
            disabled_skill_names=[],
        )
        assert dna.effective_skills == []

    @pytest.mark.unit
    def test_agent_dna_effective_skills_no_disabled(self) -> None:
        """Test that all skills pass through when disabled list is empty."""
        dna = _make_agent_dna(
            shared_skill_names=["a", "b"],
            custom_skill_names=["c"],
            disabled_skill_names=[],
        )
        assert dna.effective_skills == ["a", "b", "c"]

    @pytest.mark.unit
    def test_agent_dna_effective_skills_all_disabled(self) -> None:
        """Test that disabling all skills yields empty list."""
        dna = _make_agent_dna(
            shared_skill_names=["a"],
            custom_skill_names=["b"],
            disabled_skill_names=["a", "b"],
        )
        assert dna.effective_skills == []
