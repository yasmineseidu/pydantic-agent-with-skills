"""Integration tests for end-to-end memory pipeline flow."""

import pytest
from typing import Callable
from unittest.mock import AsyncMock, MagicMock

from src.dependencies import AgentDependencies
from src.memory.prompt_builder import MemoryPromptBuilder
from src.memory.types import RetrievalResult, RetrievalStats, ScoredMemory
from src.models.agent_models import AgentDNA
from src.models.memory_models import MemoryRecord, MemoryType


class TestMemoryPipelineIntegration:
    """Test full memory pipeline: retrieve -> build prompt."""

    @pytest.mark.unit
    def test_dependencies_accept_all_memory_services(self) -> None:
        """AgentDependencies can hold all Phase 2 service references."""
        deps = AgentDependencies()
        # Verify all memory fields exist and default to None
        assert deps.embedding_service is None
        assert deps.memory_repo is None
        assert deps.audit_log is None
        assert deps.contradiction_detector is None
        assert deps.tier_manager is None
        assert deps.token_budget is None
        assert deps.memory_retriever is None
        assert deps.memory_extractor is None
        assert deps.compaction_shield is None
        assert deps.prompt_builder is None
        assert deps.complexity_scorer is None
        assert deps.model_router is None
        assert deps.cost_guard is None

    @pytest.mark.unit
    def test_dependencies_with_mock_memory_services(self) -> None:
        """AgentDependencies works with mock memory services."""
        deps = AgentDependencies(
            embedding_service=MagicMock(),
            memory_retriever=MagicMock(),
            prompt_builder=MagicMock(),
        )
        assert deps.embedding_service is not None
        assert deps.memory_retriever is not None
        assert deps.prompt_builder is not None

    @pytest.mark.unit
    def test_retrieve_and_build_prompt(
        self,
        sample_memory_record: Callable[..., MemoryRecord],
        sample_agent_dna: Callable[..., AgentDNA],
    ) -> None:
        """Memories from retrieval appear in built prompt."""
        # Create memory records
        identity = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I am a helpful assistant named TestBot",
            importance=10,
        )
        user_prof = sample_memory_record(
            memory_type=MemoryType.USER_PROFILE,
            content="User prefers dark mode",
            importance=7,
        )

        # Build retrieval result
        scored = [
            ScoredMemory(memory=identity, final_score=1.0, signal_scores={}),
            ScoredMemory(memory=user_prof, final_score=0.8, signal_scores={}),
        ]
        result = RetrievalResult(
            memories=scored,
            formatted_prompt="",
            stats=RetrievalStats(signals_hit=2, cache_hit=False, total_ms=50.0, query_tokens=10),
            contradictions=[],
        )

        # Build prompt
        builder = MemoryPromptBuilder(token_budget=4000)
        dna = sample_agent_dna()
        prompt = builder.build(dna, "## Skills\nweather: Get weather", result)

        assert "I am a helpful assistant named TestBot" in prompt
        assert "User prefers dark mode" in prompt

    @pytest.mark.unit
    def test_identity_memory_always_in_prompt(
        self,
        sample_memory_record: Callable[..., MemoryRecord],
        sample_agent_dna: Callable[..., AgentDNA],
    ) -> None:
        """Identity memories appear in prompt even with tiny budget."""
        identity = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="Core identity fact",
            importance=10,
        )
        result = RetrievalResult(
            memories=[ScoredMemory(memory=identity, final_score=1.0, signal_scores={})],
            formatted_prompt="",
            stats=RetrievalStats(signals_hit=1, cache_hit=False, total_ms=10.0, query_tokens=5),
            contradictions=[],
        )

        builder = MemoryPromptBuilder(token_budget=200)  # Very small budget
        dna = sample_agent_dna()
        prompt = builder.build(dna, "", result)

        assert "Core identity fact" in prompt

    @pytest.mark.asyncio
    async def test_cli_mode_no_memory_services(self) -> None:
        """initialize() works without memory services for CLI mode."""
        deps = AgentDependencies()
        # In CLI mode, no DB/memory services are provided
        await deps.initialize()  # Should not raise
        assert deps.skill_loader is not None  # Skills still work
        assert deps.memory_retriever is None  # No memory in CLI mode

    @pytest.mark.asyncio
    async def test_retriever_mock_pipeline(
        self,
        sample_memory_record: Callable[..., MemoryRecord],
        sample_agent_dna: Callable[..., AgentDNA],
    ) -> None:
        """Mock retriever returns memories that appear in prompt."""
        # Set up mock retriever
        identity = sample_memory_record(
            memory_type=MemoryType.IDENTITY,
            content="I am Atlas, your research assistant",
            importance=10,
        )
        semantic = sample_memory_record(
            memory_type=MemoryType.SEMANTIC,
            content="Python 3.12 was released in October 2023",
            importance=6,
        )

        mock_result = RetrievalResult(
            memories=[
                ScoredMemory(memory=identity, final_score=1.0, signal_scores={}),
                ScoredMemory(memory=semantic, final_score=0.75, signal_scores={}),
            ],
            formatted_prompt="",
            stats=RetrievalStats(signals_hit=3, cache_hit=False, total_ms=100.0, query_tokens=20),
            contradictions=[],
        )

        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_result)

        # Build prompt
        builder = MemoryPromptBuilder(token_budget=4000)
        dna = sample_agent_dna(name="Atlas", tagline="Your research assistant")

        result = await mock_retriever.retrieve(query="python", team_id=dna.team_id)
        prompt = builder.build(dna, "## Skills\nresearch: Search the web", result)

        # Identity should be in prompt
        assert "I am Atlas, your research assistant" in prompt
        # Semantic memory should be in prompt
        assert "Python 3.12 was released" in prompt
        # Agent name should be in prompt
        assert "Atlas" in prompt

    @pytest.mark.unit
    def test_empty_retrieval_still_builds_prompt(
        self, sample_agent_dna: Callable[..., AgentDNA]
    ) -> None:
        """Prompt builds correctly even with no memories."""
        result = RetrievalResult(
            memories=[],
            formatted_prompt="",
            stats=RetrievalStats(signals_hit=0, cache_hit=False, total_ms=5.0, query_tokens=0),
            contradictions=[],
        )
        builder = MemoryPromptBuilder(token_budget=4000)
        dna = sample_agent_dna()
        prompt = builder.build(dna, "## Skills\nweather: Get weather", result)
        # Should still contain agent name and skills
        assert dna.name in prompt

    @pytest.mark.unit
    def test_create_skill_agent_singleton(self) -> None:
        """create_skill_agent() returns singleton."""
        from src.agent import create_skill_agent, get_skill_agent

        assert create_skill_agent() is get_skill_agent()

    @pytest.mark.unit
    def test_create_skill_agent_with_dna(self, sample_agent_dna: Callable[..., AgentDNA]) -> None:
        """create_skill_agent(dna) creates new agent."""
        from src.agent import create_skill_agent, get_skill_agent

        dna = sample_agent_dna()
        agent = create_skill_agent(agent_dna=dna)
        assert agent is not get_skill_agent()
