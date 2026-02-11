"""Enhanced provider support with direct integrations for OpenRouter, OpenAI, and Ollama."""

from typing import Union
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from src.settings import load_settings, Settings


def get_llm_model() -> Union[OpenAIChatModel, OpenRouterModel]:
    """
    Get model with proper provider integration.

    Returns the appropriate model based on the configured provider.
    Supports OpenRouter, OpenAI, and Ollama.

    Returns:
        Configured model with provider-specific integration
    """
    settings = load_settings()
    provider = settings.llm_provider

    if provider == "openrouter":
        return _create_openrouter_model(settings)
    elif provider == "openai":
        return _create_openai_model(settings)
    elif provider == "ollama":
        return _create_ollama_model(settings)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _create_openrouter_model(settings: Settings) -> OpenRouterModel:
    """
    Create OpenRouter model with direct integration and app attribution.

    Supports OpenRouter-specific features like app attribution for analytics.

    Args:
        settings: Application settings

    Returns:
        Configured OpenRouter model
    """
    kwargs: dict[str, str] = {"api_key": settings.llm_api_key}
    if settings.openrouter_app_url is not None:
        kwargs["app_url"] = settings.openrouter_app_url
    if settings.openrouter_app_title is not None:
        kwargs["app_title"] = settings.openrouter_app_title
    provider = OpenRouterProvider(**kwargs)
    return OpenRouterModel(settings.llm_model, provider=provider)


def _create_openai_model(settings: Settings) -> OpenAIChatModel:
    """
    Create OpenAI model with direct integration.

    Args:
        settings: Application settings

    Returns:
        Configured OpenAI model
    """
    provider = OpenAIProvider(api_key=settings.llm_api_key)
    return OpenAIChatModel(settings.llm_model, provider=provider)


def _create_ollama_model(settings: Settings) -> OpenAIChatModel:
    """
    Create Ollama model via OpenAI-compatible API.

    Ollama provides an OpenAI-compatible API endpoint.

    Args:
        settings: Application settings

    Returns:
        Configured Ollama model via OpenAI provider
    """
    provider = OpenAIProvider(
        base_url=settings.llm_base_url or "http://localhost:11434/v1",
        api_key="ollama",  # Required but unused by Ollama
    )
    return OpenAIChatModel(settings.llm_model, provider=provider)


def get_model_info() -> dict:
    """
    Get information about current model configuration.

    Returns:
        Dictionary with model configuration info
    """
    settings = load_settings()

    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
    }


def validate_llm_configuration() -> bool:
    """
    Validate that LLM configuration is properly set.

    Returns:
        True if configuration is valid
    """
    try:
        # Check if we can create a model instance
        get_llm_model()
        return True
    except Exception as e:
        print(f"LLM configuration validation failed: {e}")
        return False
