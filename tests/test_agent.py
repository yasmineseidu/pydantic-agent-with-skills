"""Integration tests for the skill-based agent."""

import pytest
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict

from src.agent import skill_agent, get_system_prompt
from src.skill_loader import SkillLoader
from src.dependencies import AgentDependencies


def get_agent_tools() -> Dict[str, any]:
    """Get all registered tools from the agent (including toolsets)."""
    all_tools = {}
    for toolset in skill_agent.toolsets:
        if hasattr(toolset, "tools"):
            all_tools.update(toolset.tools)
        if hasattr(toolset, "_tools"):
            all_tools.update(toolset._tools)
    return all_tools


@dataclass
class MockSettings:
    """Mock settings for testing."""

    skills_dir: Path = Path("skills")
    llm_api_key: str = "test-key"
    llm_model: str = "test-model"
    llm_base_url: str = "https://test.example.com"


@dataclass
class MockDependencies:
    """Mock dependencies for testing agent tools."""

    skill_loader: Optional[SkillLoader] = None
    settings: Optional[MockSettings] = field(default_factory=MockSettings)
    session_id: Optional[str] = None
    user_preferences: dict = field(default_factory=dict)

    async def initialize(self) -> None:
        """Initialize mock dependencies."""
        if self.skill_loader is None:
            self.skill_loader = SkillLoader(self.settings.skills_dir)
            self.skill_loader.discover_skills()


@dataclass
class MockContext:
    """Mock RunContext for testing."""

    deps: MockDependencies = field(default_factory=MockDependencies)


class TestAgentToolRegistration:
    """Tests for agent tool registration."""

    def test_agent_has_load_skill_tool(self) -> None:
        """Verify load_skill_tool is registered."""
        tools = get_agent_tools()
        assert "load_skill_tool" in tools

    def test_agent_has_read_skill_file_tool(self) -> None:
        """Verify read_skill_file_tool is registered."""
        tools = get_agent_tools()
        assert "read_skill_file_tool" in tools

    def test_agent_has_list_skill_files_tool(self) -> None:
        """Verify list_skill_files_tool is registered."""
        tools = get_agent_tools()
        assert "list_skill_files_tool" in tools

    def test_agent_has_http_get_tool(self) -> None:
        """Verify http_get_tool is registered."""
        tools = get_agent_tools()
        assert "http_get_tool" in tools

    def test_agent_has_http_post_tool(self) -> None:
        """Verify http_post_tool is registered."""
        tools = get_agent_tools()
        assert "http_post_tool" in tools

    def test_agent_has_at_least_five_tools(self) -> None:
        """Verify agent has at least 5 tools registered."""
        tools = get_agent_tools()
        tool_count = len(tools)
        assert tool_count >= 5, f"Expected at least 5 tools, got {tool_count}"


class TestAgentInitialization:
    """Tests for agent initialization."""

    def test_agent_exists(self) -> None:
        """Verify skill_agent is created."""
        assert skill_agent is not None

    def test_agent_has_deps_type(self) -> None:
        """Verify agent has dependency type set."""
        assert skill_agent.deps_type is not None

    def test_agent_deps_type_is_agent_dependencies(self) -> None:
        """Verify agent uses AgentDependencies."""
        assert skill_agent.deps_type == AgentDependencies


class TestSystemPromptGeneration:
    """Tests for dynamic system prompt generation."""

    @pytest.mark.asyncio
    async def test_system_prompt_includes_weather_skill(self) -> None:
        """Verify system prompt includes weather skill metadata."""
        # Create mock context with real skill loader
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        # Call the system prompt function
        prompt = await get_system_prompt(ctx)

        assert "weather" in prompt.lower()

    @pytest.mark.asyncio
    async def test_system_prompt_includes_code_review_skill(self) -> None:
        """Verify system prompt includes code_review skill metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        prompt = await get_system_prompt(ctx)

        assert "code_review" in prompt.lower()

    @pytest.mark.asyncio
    async def test_system_prompt_contains_skill_descriptions(self) -> None:
        """Verify system prompt contains skill descriptions."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        prompt = await get_system_prompt(ctx)

        # Check for actual skill descriptions
        assert "weather" in prompt.lower()
        assert "review" in prompt.lower() or "code" in prompt.lower()


class TestSkillDiscoveryIntegration:
    """Integration tests for skill discovery with the agent."""

    @pytest.mark.asyncio
    async def test_both_skills_discovered(self) -> None:
        """Verify both weather and code_review skills are discovered."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill_names = list(mock_deps.skill_loader.skills.keys())

        assert "weather" in skill_names
        assert "code_review" in skill_names

    @pytest.mark.asyncio
    async def test_skill_count_at_least_five(self) -> None:
        """Verify at least 5 skills are discovered."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill_count = len(mock_deps.skill_loader.skills)

        assert skill_count >= 5, f"Expected at least 5 skills, got {skill_count}"

    @pytest.mark.asyncio
    async def test_all_five_skills_discovered(self) -> None:
        """Verify all 5 skills are discovered."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill_names = list(mock_deps.skill_loader.skills.keys())

        assert "weather" in skill_names
        assert "code_review" in skill_names
        assert "research_assistant" in skill_names
        assert "recipe_finder" in skill_names
        assert "world_clock" in skill_names

    @pytest.mark.asyncio
    async def test_weather_skill_has_correct_metadata(self) -> None:
        """Verify weather skill has expected metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        weather_skill = mock_deps.skill_loader.skills.get("weather")

        assert weather_skill is not None
        assert weather_skill.name == "weather"
        assert "weather" in weather_skill.description.lower()

    @pytest.mark.asyncio
    async def test_code_review_skill_has_correct_metadata(self) -> None:
        """Verify code_review skill has expected metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        code_review_skill = mock_deps.skill_loader.skills.get("code_review")

        assert code_review_skill is not None
        assert code_review_skill.name == "code_review"
        assert (
            "review" in code_review_skill.description.lower()
            or "code" in code_review_skill.description.lower()
        )

    @pytest.mark.asyncio
    async def test_research_assistant_skill_has_correct_metadata(self) -> None:
        """Verify research_assistant skill has expected metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill = mock_deps.skill_loader.skills.get("research_assistant")

        assert skill is not None
        assert skill.name == "research_assistant"
        assert "research" in skill.description.lower() or "paper" in skill.description.lower()

    @pytest.mark.asyncio
    async def test_recipe_finder_skill_has_correct_metadata(self) -> None:
        """Verify recipe_finder skill has expected metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill = mock_deps.skill_loader.skills.get("recipe_finder")

        assert skill is not None
        assert skill.name == "recipe_finder"
        assert "recipe" in skill.description.lower() or "food" in skill.description.lower()

    @pytest.mark.asyncio
    async def test_world_clock_skill_has_correct_metadata(self) -> None:
        """Verify world_clock skill has expected metadata."""
        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        skill = mock_deps.skill_loader.skills.get("world_clock")

        assert skill is not None
        assert skill.name == "world_clock"
        assert "time" in skill.description.lower() or "timezone" in skill.description.lower()


class TestLoadSkillToolIntegration:
    """Integration tests for load_skill_tool."""

    @pytest.mark.asyncio
    async def test_load_weather_skill_returns_instructions(self) -> None:
        """Test loading weather skill returns skill instructions."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "weather")

        # Should contain skill body content
        assert "Weather" in result
        assert "Open-Meteo" in result or "weather" in result.lower()

    @pytest.mark.asyncio
    async def test_load_code_review_skill_returns_instructions(self) -> None:
        """Test loading code_review skill returns skill instructions."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "code_review")

        # Should contain skill body content
        assert "Code Review" in result or "code review" in result.lower()
        assert "reference" in result.lower() or "best_practices" in result.lower()

    @pytest.mark.asyncio
    async def test_load_nonexistent_skill_returns_error(self) -> None:
        """Test loading nonexistent skill returns error message."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "nonexistent_skill")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_load_research_assistant_skill_returns_instructions(self) -> None:
        """Test loading research_assistant skill returns skill instructions."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "research_assistant")

        assert "Research" in result or "research" in result.lower()
        assert "Semantic Scholar" in result or "paper" in result.lower()

    @pytest.mark.asyncio
    async def test_load_recipe_finder_skill_returns_instructions(self) -> None:
        """Test loading recipe_finder skill returns skill instructions."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "recipe_finder")

        assert "Recipe" in result or "recipe" in result.lower()
        assert "ingredient" in result.lower() or "meal" in result.lower()

    @pytest.mark.asyncio
    async def test_load_world_clock_skill_returns_instructions(self) -> None:
        """Test loading world_clock skill returns skill instructions."""
        from src.skill_tools import load_skill

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await load_skill(ctx, "world_clock")

        assert "Clock" in result or "time" in result.lower()
        assert "timezone" in result.lower() or "Timezone" in result


class TestReadSkillFileIntegration:
    """Integration tests for read_skill_file_tool."""

    @pytest.mark.asyncio
    async def test_read_weather_api_reference(self) -> None:
        """Test reading weather skill's API reference file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "weather", "references/api_reference.md")

        assert "Open-Meteo" in result or "API" in result

    @pytest.mark.asyncio
    async def test_read_code_review_best_practices(self) -> None:
        """Test reading code_review skill's best practices file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "code_review", "references/best_practices.md")

        assert "Best Practices" in result or "best practices" in result.lower()

    @pytest.mark.asyncio
    async def test_read_code_review_security_checklist(self) -> None:
        """Test reading code_review skill's security checklist file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "code_review", "references/security_checklist.md")

        assert "Security" in result or "security" in result.lower()

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_returns_error(self) -> None:
        """Test reading nonexistent file returns error message."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "weather", "nonexistent.md")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_read_research_assistant_api_reference(self) -> None:
        """Test reading research_assistant skill's API reference file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "research_assistant", "references/api_reference.md")

        assert "Semantic Scholar" in result or "API" in result

    @pytest.mark.asyncio
    async def test_read_recipe_finder_api_reference(self) -> None:
        """Test reading recipe_finder skill's API reference file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "recipe_finder", "references/api_reference.md")

        assert "MealDB" in result or "Spoonacular" in result or "recipe" in result.lower()

    @pytest.mark.asyncio
    async def test_read_recipe_finder_dietary_guide(self) -> None:
        """Test reading recipe_finder skill's dietary guide file."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await read_skill_file(ctx, "recipe_finder", "references/dietary_guide.md")

        assert "diet" in result.lower() or "vegetarian" in result.lower()


class TestListSkillFilesIntegration:
    """Integration tests for list_skill_files_tool."""

    @pytest.mark.asyncio
    async def test_list_weather_skill_files(self) -> None:
        """Test listing files in weather skill."""
        from src.skill_tools import list_skill_files

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await list_skill_files(ctx, "weather")

        assert "SKILL.md" in result
        assert "api_reference.md" in result

    @pytest.mark.asyncio
    async def test_list_code_review_skill_files(self) -> None:
        """Test listing files in code_review skill."""
        from src.skill_tools import list_skill_files

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await list_skill_files(ctx, "code_review")

        assert "SKILL.md" in result
        assert "best_practices.md" in result
        assert "security_checklist.md" in result
        assert "common_antipatterns.md" in result

    @pytest.mark.asyncio
    async def test_list_research_assistant_skill_files(self) -> None:
        """Test listing files in research_assistant skill."""
        from src.skill_tools import list_skill_files

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await list_skill_files(ctx, "research_assistant")

        assert "SKILL.md" in result
        assert "api_reference.md" in result
        assert "search_tips.md" in result

    @pytest.mark.asyncio
    async def test_list_recipe_finder_skill_files(self) -> None:
        """Test listing files in recipe_finder skill."""
        from src.skill_tools import list_skill_files

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await list_skill_files(ctx, "recipe_finder")

        assert "SKILL.md" in result
        assert "api_reference.md" in result
        assert "dietary_guide.md" in result

    @pytest.mark.asyncio
    async def test_list_world_clock_skill_files(self) -> None:
        """Test listing files in world_clock skill."""
        from src.skill_tools import list_skill_files

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        result = await list_skill_files(ctx, "world_clock")

        assert "SKILL.md" in result


class TestReferenceFileSizes:
    """Tests to verify reference files have substantial content."""

    @pytest.mark.asyncio
    async def test_best_practices_file_size(self) -> None:
        """Verify best_practices.md is substantial (~10KB+)."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        content = await read_skill_file(ctx, "code_review", "references/best_practices.md")

        # Should be at least 8KB
        assert len(content) >= 8000, f"best_practices.md too small: {len(content)} bytes"

    @pytest.mark.asyncio
    async def test_security_checklist_file_size(self) -> None:
        """Verify security_checklist.md is substantial (~15KB+)."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        content = await read_skill_file(ctx, "code_review", "references/security_checklist.md")

        # Should be at least 12KB
        assert len(content) >= 12000, f"security_checklist.md too small: {len(content)} bytes"

    @pytest.mark.asyncio
    async def test_common_antipatterns_file_size(self) -> None:
        """Verify common_antipatterns.md is substantial (~20KB+)."""
        from src.skill_tools import read_skill_file

        mock_deps = MockDependencies(settings=MockSettings())
        await mock_deps.initialize()

        ctx = MockContext(deps=mock_deps)

        content = await read_skill_file(ctx, "code_review", "references/common_antipatterns.md")

        # Should be at least 15KB
        assert len(content) >= 15000, f"common_antipatterns.md too small: {len(content)} bytes"
