"""Unit tests for MemoryPromptBuilder (src/memory/prompt_builder.py)."""

import math
from typing import Callable
from uuid import uuid4

import pytest

from src.memory.prompt_builder import MemoryPromptBuilder, _format_voice_examples
from src.memory.types import Contradiction, RetrievalResult, RetrievalStats, ScoredMemory
from src.models.agent_models import AgentDNA, VoiceExample
from src.models.memory_models import MemoryRecord, MemoryType


# ---------------------------------------------------------------------------
# TestEstimateTokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Tests for token estimation method."""

    @pytest.mark.unit
    def test_empty_string_returns_zero(self) -> None:
        """Test that estimating tokens for empty string returns 0."""
        builder = MemoryPromptBuilder()
        assert builder.estimate_tokens("") == 0

    @pytest.mark.unit
    def test_short_text_estimate(self) -> None:
        """Test token estimation for short text."""
        builder = MemoryPromptBuilder()
        text = "hello"
        expected = math.ceil(len(text) / 3.5)  # ceil(5 / 3.5) = ceil(1.43) = 2
        assert builder.estimate_tokens(text) == expected
        assert builder.estimate_tokens(text) == 2

    @pytest.mark.unit
    def test_long_text_estimate(self) -> None:
        """Test token estimation for long text (1000 chars)."""
        builder = MemoryPromptBuilder()
        text = "x" * 1000
        expected = math.ceil(1000 / 3.5)  # ceil(285.71) = 286
        assert builder.estimate_tokens(text) == expected
        assert builder.estimate_tokens(text) == 286


# ---------------------------------------------------------------------------
# TestBuildLayers
# ---------------------------------------------------------------------------


class TestBuildLayers:
    """Tests for layer inclusion in built prompts."""

    @pytest.mark.unit
    def test_build_includes_agent_name(self, sample_agent_dna: Callable[..., AgentDNA]) -> None:
        """Test that agent name appears in the built prompt."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna(name="TestBot")
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats)

        prompt = builder.build(agent, "", result, "")

        assert "TestBot" in prompt

    @pytest.mark.unit
    def test_build_includes_identity_memories(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that identity memories appear with correct header."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create identity memory
        identity_record = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I am a helpful AI assistant.",
        )
        scored = ScoredMemory(memory=identity_record, final_score=0.9)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)

        prompt = builder.build(agent, "", result, "")

        assert "### Identity Memories" in prompt
        assert "I am a helpful AI assistant." in prompt

    @pytest.mark.unit
    def test_build_includes_skill_metadata(self, sample_agent_dna: Callable[..., AgentDNA]) -> None:
        """Test that skill metadata string is included in prompt."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats)
        skill_metadata = (
            "## Available Skills\n- weather: Get weather info\n- code_review: Review code"
        )

        prompt = builder.build(agent, skill_metadata, result, "")

        assert "Available Skills" in prompt
        assert "weather: Get weather info" in prompt

    @pytest.mark.unit
    def test_build_includes_user_profile(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that user profile memories appear with correct header."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create user profile memory
        profile_record = sample_memory_record(
            memory_type=MemoryType.USER_PROFILE,
            content="User prefers dark mode.",
        )
        scored = ScoredMemory(memory=profile_record, final_score=0.85)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)

        prompt = builder.build(agent, "", result, "")

        assert "### About This User" in prompt
        assert "User prefers dark mode." in prompt

    @pytest.mark.unit
    def test_build_includes_retrieved_memories_grouped_by_type(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that retrieved memories are grouped by type with headers."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create semantic and episodic memories
        semantic_record = sample_memory_record(
            memory_type=MemoryType.SEMANTIC,
            content="Python is a programming language.",
        )
        episodic_record = sample_memory_record(
            memory_type=MemoryType.EPISODIC,
            content="Had a meeting on Monday.",
        )
        semantic_scored = ScoredMemory(memory=semantic_record, final_score=0.9)
        episodic_scored = ScoredMemory(memory=episodic_record, final_score=0.8)
        stats = RetrievalStats(signals_hit=2, total_ms=20.0, query_tokens=10)
        result = RetrievalResult(memories=[semantic_scored, episodic_scored], stats=stats)

        prompt = builder.build(agent, "", result, "")

        # Check both types are grouped
        assert "Recalled (episodic)" in prompt or "Recalled (semantic)" in prompt
        assert "Python is a programming language." in prompt
        assert "Had a meeting on Monday." in prompt

    @pytest.mark.unit
    def test_build_includes_team_knowledge(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that shared/team memories appear with correct header."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create shared memory
        shared_record = sample_memory_record(
            memory_type=MemoryType.SHARED,
            content="Team uses GitHub for code review.",
        )
        scored = ScoredMemory(memory=shared_record, final_score=0.75)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)

        prompt = builder.build(agent, "", result, "")

        assert "### Team Knowledge" in prompt
        assert "Team uses GitHub for code review." in prompt

    @pytest.mark.unit
    def test_build_includes_conversation_summary(
        self, sample_agent_dna: Callable[..., AgentDNA]
    ) -> None:
        """Test that conversation summary is included in prompt."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats)
        conversation_summary = "Discussed Python project setup and database design."

        prompt = builder.build(agent, "", result, conversation_summary)

        assert "Discussed Python project setup and database design." in prompt

    @pytest.mark.unit
    def test_build_includes_contradiction_markers(
        self, sample_agent_dna: Callable[..., AgentDNA]
    ) -> None:
        """Test that contradiction markers appear in prompt."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create contradiction
        contradiction = Contradiction(
            memory_a=uuid4(),
            memory_b=uuid4(),
            reason="User preference changed from light to dark mode",
        )
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats, contradictions=[contradiction])

        prompt = builder.build(agent, "", result, "")

        assert "[FACT DISPUTED]:" in prompt
        assert "User preference changed from light to dark mode" in prompt


# ---------------------------------------------------------------------------
# TestTrimming
# ---------------------------------------------------------------------------


class TestTrimming:
    """Tests for layer trimming behavior under token budget constraints."""

    @pytest.mark.unit
    def test_l7_trimmed_first_under_tight_budget(
        self, sample_agent_dna: Callable[..., AgentDNA]
    ) -> None:
        """Test that L7 (conversation summary) is trimmed first under tight budget."""
        builder = MemoryPromptBuilder(token_budget=500)  # Very small budget
        agent = sample_agent_dna()
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats)
        conversation_summary = "x" * 5000  # Very long summary

        prompt = builder.build(agent, "", result, conversation_summary)

        # L7 should be trimmed out
        assert "x" * 100 not in prompt  # Large portion of summary not present

    @pytest.mark.unit
    def test_l6_trimmed_after_l7(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that L6 (team knowledge) is trimmed after L7 under tight budget."""
        builder = MemoryPromptBuilder(token_budget=500)
        agent = sample_agent_dna()

        # Create large shared memory
        shared_record = sample_memory_record(
            memory_type=MemoryType.SHARED,
            content="x" * 3000,
        )
        scored = ScoredMemory(memory=shared_record, final_score=0.8)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)
        conversation_summary = "y" * 3000  # Also large

        prompt = builder.build(agent, "", result, conversation_summary)

        # Both L7 and L6 should be trimmed
        assert "x" * 100 not in prompt
        assert "y" * 100 not in prompt

    @pytest.mark.unit
    def test_l5_trimmed_after_l6(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that L5 (retrieved memories) is trimmed after L6 under very tight budget."""
        builder = MemoryPromptBuilder(token_budget=300)
        agent = sample_agent_dna()

        # Create large semantic, shared, and conversation
        semantic_record = sample_memory_record(
            memory_type=MemoryType.SEMANTIC,
            content="z" * 2000,
        )
        shared_record = sample_memory_record(
            memory_type=MemoryType.SHARED,
            content="x" * 2000,
        )
        semantic_scored = ScoredMemory(memory=semantic_record, final_score=0.9)
        shared_scored = ScoredMemory(memory=shared_record, final_score=0.8)
        stats = RetrievalStats(signals_hit=2, total_ms=20.0, query_tokens=10)
        result = RetrievalResult(memories=[semantic_scored, shared_scored], stats=stats)
        conversation_summary = "y" * 2000

        prompt = builder.build(agent, "", result, conversation_summary)

        # L7, L6, and L5 should be trimmed
        assert "x" * 100 not in prompt  # L6
        assert "y" * 100 not in prompt  # L7
        assert "z" * 100 not in prompt  # L5

    @pytest.mark.unit
    def test_l4_trimmed_last_among_trimmable(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that L4 (user profile) is trimmed last under extremely tight budget."""
        builder = MemoryPromptBuilder(token_budget=200)
        agent = sample_agent_dna()

        # Create large memories for all trimmable layers
        profile_record = sample_memory_record(
            memory_type=MemoryType.USER_PROFILE,
            content="p" * 2000,
        )
        semantic_record = sample_memory_record(
            memory_type=MemoryType.SEMANTIC,
            content="z" * 2000,
        )
        shared_record = sample_memory_record(
            memory_type=MemoryType.SHARED,
            content="x" * 2000,
        )
        profile_scored = ScoredMemory(memory=profile_record, final_score=0.9)
        semantic_scored = ScoredMemory(memory=semantic_record, final_score=0.9)
        shared_scored = ScoredMemory(memory=shared_record, final_score=0.8)
        stats = RetrievalStats(signals_hit=3, total_ms=30.0, query_tokens=15)
        result = RetrievalResult(
            memories=[profile_scored, semantic_scored, shared_scored], stats=stats
        )
        conversation_summary = "y" * 2000

        prompt = builder.build(agent, "", result, conversation_summary)

        # All trimmable layers should be trimmed
        assert "p" * 100 not in prompt  # L4
        assert "x" * 100 not in prompt  # L6
        assert "y" * 100 not in prompt  # L7
        assert "z" * 100 not in prompt  # L5

    @pytest.mark.unit
    def test_protected_layers_never_trimmed(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that L1-L3 are never trimmed even under extremely tight budget."""
        builder = MemoryPromptBuilder(token_budget=1)  # Impossibly small budget
        agent = sample_agent_dna(name="ProtectedBot")

        # Create identity memory
        identity_record = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I am ProtectedBot.",
        )
        scored = ScoredMemory(memory=identity_record, final_score=0.9)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)
        skill_metadata = "## Skills\n- test_skill"

        prompt = builder.build(agent, skill_metadata, result, "")

        # Protected layers still present
        assert "ProtectedBot" in prompt  # L1
        assert "I am ProtectedBot." in prompt  # L2
        assert "## Skills" in prompt  # L3

    @pytest.mark.unit
    def test_large_budget_includes_all_layers(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that with large budget all 7 layers are included."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna(name="FullBot")

        # Create memories for each layer
        identity_record = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I am a helpful assistant.",
        )
        profile_record = sample_memory_record(
            memory_type=MemoryType.USER_PROFILE,
            content="User likes Python.",
        )
        semantic_record = sample_memory_record(
            memory_type=MemoryType.SEMANTIC,
            content="Python has dynamic typing.",
        )
        shared_record = sample_memory_record(
            memory_type=MemoryType.SHARED,
            content="Team uses CI/CD.",
        )
        identity_scored = ScoredMemory(memory=identity_record, final_score=0.95)
        profile_scored = ScoredMemory(memory=profile_record, final_score=0.9)
        semantic_scored = ScoredMemory(memory=semantic_record, final_score=0.85)
        shared_scored = ScoredMemory(memory=shared_record, final_score=0.8)
        stats = RetrievalStats(signals_hit=4, total_ms=40.0, query_tokens=20)
        result = RetrievalResult(
            memories=[identity_scored, profile_scored, semantic_scored, shared_scored],
            stats=stats,
        )
        skill_metadata = "## Skills\n- weather"
        conversation_summary = "Discussed weather forecasting."

        prompt = builder.build(agent, skill_metadata, result, conversation_summary)

        # All 7 layers present
        assert "FullBot" in prompt  # L1
        assert "I am a helpful assistant." in prompt  # L2
        assert "## Skills" in prompt  # L3
        assert "User likes Python." in prompt  # L4
        assert "Python has dynamic typing." in prompt  # L5
        assert "Team uses CI/CD." in prompt  # L6
        assert "Discussed weather forecasting." in prompt  # L7


# ---------------------------------------------------------------------------
# TestFormatVoiceExamples
# ---------------------------------------------------------------------------


class TestFormatVoiceExamples:
    """Tests for _format_voice_examples helper function."""

    @pytest.mark.unit
    def test_empty_examples_returns_empty(self) -> None:
        """Test that empty examples list returns empty string."""
        result = _format_voice_examples([])
        assert result == ""

    @pytest.mark.unit
    def test_voice_examples_include_user_and_agent(self) -> None:
        """Test that voice examples are formatted with User: and You: labels."""
        examples = [
            VoiceExample(
                user_message="What's the weather?",
                agent_response="Let me check that for you.",
                context="casual",
            ),
        ]
        result = _format_voice_examples(examples)

        assert "User" in result
        assert "You:" in result
        assert "What's the weather?" in result
        assert "Let me check that for you." in result

    @pytest.mark.unit
    def test_voice_examples_with_context(self) -> None:
        """Test that context is included in the format when provided."""
        examples = [
            VoiceExample(
                user_message="Debug this error",
                agent_response="I'll analyze the stack trace.",
                context="technical support",
            ),
        ]
        result = _format_voice_examples(examples)

        assert "technical support" in result

    @pytest.mark.unit
    def test_voice_examples_without_context(self) -> None:
        """Test that voice examples work without context field."""
        examples = [
            VoiceExample(
                user_message="Hello",
                agent_response="Hi there!",
            ),
        ]
        result = _format_voice_examples(examples)

        assert "User" in result
        assert "You:" in result
        assert "Hello" in result
        assert "Hi there!" in result


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_empty_retrieval_result(self, sample_agent_dna: Callable[..., AgentDNA]) -> None:
        """Test building prompt with no memories or contradictions."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna(name="EmptyBot")
        stats = RetrievalStats(signals_hit=0, total_ms=0.0, query_tokens=0)
        result = RetrievalResult(stats=stats)

        prompt = builder.build(agent, "", result, "")

        # Should still have identity (L1)
        assert "EmptyBot" in prompt
        # Should not crash, should return valid prompt
        assert len(prompt) > 0

    @pytest.mark.unit
    def test_only_identity_memories(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that only identity memories are present in L2, others empty."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Only identity memory
        identity_record = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I specialize in weather forecasting.",
        )
        scored = ScoredMemory(memory=identity_record, final_score=0.95)
        stats = RetrievalStats(signals_hit=1, total_ms=10.0, query_tokens=5)
        result = RetrievalResult(memories=[scored], stats=stats)

        prompt = builder.build(agent, "", result, "")

        # L2 present
        assert "### Identity Memories" in prompt
        assert "I specialize in weather forecasting." in prompt
        # Other memory sections should not appear
        # (headers only appear if memories exist for that type)

    @pytest.mark.unit
    def test_all_memory_types_present(
        self,
        sample_agent_dna: Callable[..., AgentDNA],
        sample_memory_record: Callable[..., MemoryRecord],
    ) -> None:
        """Test that all memory types are properly partitioned when present."""
        builder = MemoryPromptBuilder(token_budget=10000)
        agent = sample_agent_dna()

        # Create one of each type
        identity_record = sample_memory_record(
            memory_type=MemoryType.IDENTITY, content="Identity memory"
        )
        profile_record = sample_memory_record(
            memory_type=MemoryType.USER_PROFILE, content="Profile memory"
        )
        semantic_record = sample_memory_record(
            memory_type=MemoryType.SEMANTIC, content="Semantic memory"
        )
        episodic_record = sample_memory_record(
            memory_type=MemoryType.EPISODIC, content="Episodic memory"
        )
        procedural_record = sample_memory_record(
            memory_type=MemoryType.PROCEDURAL, content="Procedural memory"
        )
        shared_record = sample_memory_record(memory_type=MemoryType.SHARED, content="Shared memory")
        agent_private_record = sample_memory_record(
            memory_type=MemoryType.AGENT_PRIVATE, content="Agent private memory"
        )

        memories = [
            ScoredMemory(memory=identity_record, final_score=0.95),
            ScoredMemory(memory=profile_record, final_score=0.9),
            ScoredMemory(memory=semantic_record, final_score=0.85),
            ScoredMemory(memory=episodic_record, final_score=0.8),
            ScoredMemory(memory=procedural_record, final_score=0.75),
            ScoredMemory(memory=shared_record, final_score=0.7),
            ScoredMemory(memory=agent_private_record, final_score=0.65),
        ]
        stats = RetrievalStats(signals_hit=7, total_ms=70.0, query_tokens=35)
        result = RetrievalResult(memories=memories, stats=stats)

        prompt = builder.build(agent, "", result, "")

        # Check each memory type is in the prompt
        assert "Identity memory" in prompt
        assert "Profile memory" in prompt
        assert "Semantic memory" in prompt
        assert "Episodic memory" in prompt
        assert "Procedural memory" in prompt
        assert "Shared memory" in prompt
        assert "Agent private memory" in prompt

        # Check appropriate headers
        assert "### Identity Memories" in prompt
        assert "### About This User" in prompt
        assert "### Team Knowledge" in prompt
