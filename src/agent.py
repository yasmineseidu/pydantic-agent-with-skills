"""Main skill-based agent implementation with progressive disclosure."""

import logging
from typing import TYPE_CHECKING, Optional, Union

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from src.dependencies import AgentDependencies
from src.http_tools import http_get, http_post
from src.prompts import MAIN_SYSTEM_PROMPT
from src.providers import get_llm_model
from src.settings import Settings, load_settings
from src.skill_toolset import skill_tools

if TYPE_CHECKING:
    from src.models.agent_models import AgentDNA

logger = logging.getLogger(__name__)

_skill_agent: Optional[Agent[AgentDependencies, str]] = None
_logfire_configured: bool = False


class AgentState(BaseModel):
    """Minimal shared state for the skill agent."""

    pass


def _configure_logfire(settings: Settings) -> None:
    """Configure Logfire if token is present (one-time)."""
    global _logfire_configured
    if _logfire_configured:
        return

    if settings.logfire_token:
        try:
            import logfire

            logfire.configure(
                token=settings.logfire_token,
                send_to_logfire="if-token-present",
                service_name=settings.logfire_service_name,
                environment=settings.logfire_environment,
                console=logfire.ConsoleOptions(show_project_link=False),
            )

            # Instrument Pydantic AI
            logfire.instrument_pydantic_ai()

            # Instrument HTTP requests to LLM providers
            logfire.instrument_httpx(capture_all=True)

            logger.info(f"logfire_enabled: service={settings.logfire_service_name}")
        except Exception as e:
            logger.warning(f"logfire_initialization_failed: {str(e)}")
    else:
        logger.info("logfire_disabled: token not provided")

    _logfire_configured = True


def _build_skill_agent() -> Agent[AgentDependencies, str]:
    """Create the singleton skill agent with tools and system prompt."""
    agent = Agent(
        get_llm_model(),
        deps_type=AgentDependencies,
        system_prompt="",  # Will be set dynamically via decorator
        toolsets=[skill_tools],  # Register skill toolset here
    )

    @agent.system_prompt
    async def get_system_prompt(ctx: RunContext[AgentDependencies]) -> str:
        """
        Generate system prompt with skill metadata.

        This dynamically injects skill metadata into the system prompt,
        implementing Level 1 of progressive disclosure.

        Args:
            ctx: Agent runtime context with dependencies

        Returns:
            Complete system prompt with skill metadata injected
        """
        # Initialize dependencies (including skill loader)
        await ctx.deps.initialize()

        # Get skill metadata for prompt
        skill_metadata = ""
        if ctx.deps.skill_loader:
            skill_metadata = ctx.deps.skill_loader.get_skill_metadata_prompt()

        # Inject skill metadata into base prompt
        return MAIN_SYSTEM_PROMPT.format(skill_metadata=skill_metadata)

    @agent.tool
    async def http_get_tool(
        ctx: RunContext[AgentDependencies],
        url: str,
    ) -> str:
        """
        Make an HTTP GET request to fetch data from a URL.

        Use this tool when you need to:
        - Fetch data from an API (like weather, stock prices, etc.)
        - Retrieve content from a web page
        - Make any GET request to an external service

        Args:
            ctx: Agent runtime context with dependencies
            url: The full URL to fetch (e.g., "https://api.example.com/data")

        Returns:
            Response body (JSON is formatted nicely), or error message if request fails
        """
        return await http_get(ctx, url)

    @agent.tool
    async def http_post_tool(
        ctx: RunContext[AgentDependencies],
        url: str,
        body: Optional[str] = None,
    ) -> str:
        """
        Make an HTTP POST request to send data to a URL.

        Use this tool when you need to:
        - Send data to an API
        - Submit form data
        - Make any POST request to an external service

        Args:
            ctx: Agent runtime context with dependencies
            url: The full URL to post to
            body: Request body as a string (use JSON string for JSON APIs)

        Returns:
            Response body, or error message if request fails
        """
        return await http_post(ctx, url, body)

    return agent


def get_skill_agent() -> Agent[AgentDependencies, str]:
    """Get or create the singleton skill agent lazily."""
    global _skill_agent
    if _skill_agent is None:
        settings = load_settings()
        _configure_logfire(settings)
        _skill_agent = _build_skill_agent()
    return _skill_agent


def _create_model_for_provider(
    settings: Settings,
    model_name: str,
) -> Union[OpenAIChatModel, OpenRouterModel]:
    """Create a model instance based on provider settings and model name."""
    provider = settings.llm_provider
    if provider == "openrouter":
        openrouter = OpenRouterProvider(
            api_key=settings.llm_api_key,
            app_url=settings.openrouter_app_url,
            app_title=settings.openrouter_app_title,
        )
        return OpenRouterModel(model_name, provider=openrouter)
    if provider == "openai":
        openai_provider = OpenAIProvider(api_key=settings.llm_api_key)
        return OpenAIChatModel(model_name, provider=openai_provider)
    if provider == "ollama":
        ollama_provider = OpenAIProvider(
            base_url=settings.llm_base_url or "http://localhost:11434/v1",
            api_key="ollama",
        )
        return OpenAIChatModel(model_name, provider=ollama_provider)
    raise ValueError(f"Unsupported provider: {provider}")


def create_skill_agent(agent_dna: Optional["AgentDNA"] = None) -> Agent[AgentDependencies, str]:
    """
    Factory function to create skill-based agents with optional DNA configuration.

    When called without arguments, returns the default singleton skill_agent.
    When called with AgentDNA, creates a NEW Agent instance with:
    - Model from agent_dna.model.model_name
    - Memory-aware system prompt when memory services available
    - Effective skills computed from DNA
    - Same toolset as singleton (skill_tools + http tools)

    Args:
        agent_dna: Optional AgentDNA configuration for personalized agent

    Returns:
        Configured Agent instance (singleton or new instance)

    Examples:
        >>> # Get default singleton
        >>> agent = create_skill_agent()
        >>>
        >>> # Create personalized agent with DNA
        >>> dna = AgentDNA(...)
        >>> custom_agent = create_skill_agent(agent_dna=dna)
    """
    # If no DNA provided, return singleton
    if agent_dna is None:
        return get_skill_agent()

    # Create new Agent with DNA configuration
    settings = load_settings()
    _configure_logfire(settings)

    # Create model using DNA's model_name and configured provider
    model = _create_model_for_provider(settings, agent_dna.model.model_name)

    # Create new Agent instance
    new_agent = Agent(
        model,
        deps_type=AgentDependencies,
        system_prompt="",  # Will be set dynamically
        toolsets=[skill_tools],
    )

    # Register memory-aware system prompt
    @new_agent.system_prompt
    async def get_memory_aware_prompt(ctx: RunContext[AgentDependencies]) -> str:
        """
        Generate memory-aware system prompt using MemoryPromptBuilder if available.

        Falls back to MAIN_SYSTEM_PROMPT if memory services not configured.

        Args:
            ctx: Agent runtime context with dependencies

        Returns:
            Complete system prompt with memory context
        """
        await ctx.deps.initialize()

        # Build skill metadata for effective skills from DNA
        skill_metadata = ""
        if ctx.deps.skill_loader:
            # Filter to only effective skills from DNA
            effective_skills = agent_dna.effective_skills
            all_skills = ctx.deps.skill_loader.skills
            filtered_skills = {
                name: skill for name, skill in all_skills.items() if name in effective_skills
            }
            # Generate metadata for filtered skills
            if filtered_skills:
                skill_metadata = "\n\n## Available Skills\n\n"
                for skill in filtered_skills.values():
                    skill_metadata += f"**{skill.name}**: {skill.description}\n"

        # Use MemoryPromptBuilder if available
        if ctx.deps.prompt_builder and ctx.deps.memory_retriever:
            try:
                # Retrieve memories (empty query gets relevant context)
                retrieval_result = await ctx.deps.memory_retriever.retrieve(
                    query="", team_id=agent_dna.team_id, agent_id=agent_dna.id
                )

                # Build prompt with 7-layer structure
                return ctx.deps.prompt_builder.build(
                    agent_dna=agent_dna,
                    skill_metadata=skill_metadata,
                    retrieval_result=retrieval_result,
                    conversation_summary="",
                )
            except Exception as e:
                logger.warning(
                    f"memory_prompt_build_failed: agent={agent_dna.name}, error={str(e)}"
                )
                # Fall through to default prompt

        # Fallback to standard prompt
        return MAIN_SYSTEM_PROMPT.format(skill_metadata=skill_metadata)

    # Register HTTP tools on new agent
    @new_agent.tool
    async def http_get_tool_dna(ctx: RunContext[AgentDependencies], url: str) -> str:
        """Make an HTTP GET request to fetch data from a URL."""
        return await http_get(ctx, url)

    @new_agent.tool
    async def http_post_tool_dna(
        ctx: RunContext[AgentDependencies], url: str, body: Optional[str] = None
    ) -> str:
        """Make an HTTP POST request to send data to a URL."""
        return await http_post(ctx, url, body)

    logger.info(
        f"create_skill_agent: created agent with dna, name={agent_dna.name}, "
        f"model={agent_dna.model.model_name}, skills={len(agent_dna.effective_skills)}"
    )

    return new_agent
