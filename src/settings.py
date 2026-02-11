"""Settings configuration for Skill-Based Agent."""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
from typing import Optional, Literal

# Load environment variables from .env file
load_dotenv()


class FeatureFlags(BaseModel):
    """Simple boolean feature flags via environment variables.

    Controls which platform features are active. Each flag maps to
    a FEATURE_FLAGS__<FLAG_NAME> environment variable.
    """

    enable_memory: bool = Field(default=True, description="Phase 2: Full memory system")
    enable_compaction_shield: bool = Field(
        default=True, description="Phase 2: Double-pass extraction"
    )
    enable_contradiction_detection: bool = Field(
        default=True, description="Phase 2: Conflict detection"
    )
    enable_agent_collaboration: bool = Field(default=False, description="Phase 7: Router, handoff")
    enable_expert_gate: bool = Field(default=False, description="Phase 7: MoE 4-signal scoring")
    enable_ensemble_mode: bool = Field(default=False, description="Phase 7: Multi-expert responses")
    enable_task_delegation: bool = Field(default=False, description="Phase 7: AgentTask system")
    enable_collaboration: bool = Field(
        default=False, description="Phase 7: Full collaboration sessions"
    )
    enable_webhooks: bool = Field(default=False, description="Phase 9: Outbound webhooks")
    enable_integrations: bool = Field(default=False, description="Phase 9: Telegram/Slack")
    enable_redis_cache: bool = Field(default=False, description="Phase 3: Redis caching layer")
    enable_api: bool = Field(default=False, description="Phase 4: FastAPI REST API")
    enable_background_processing: bool = Field(
        default=False, description="Phase 6: Celery background tasks"
    )


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Skills Configuration
    skills_dir: Path = Field(
        default=Path("skills"), description="Directory containing skill definitions"
    )

    # LLM Configuration (OpenAI-compatible)
    llm_provider: Literal["openrouter", "openai", "ollama"] = Field(
        default="openrouter", description="LLM provider to use"
    )

    llm_api_key: str = Field(..., description="API key for the LLM provider")

    llm_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        description="Model to use for agent",
    )

    llm_base_url: Optional[str] = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for the LLM API (for OpenAI-compatible providers)",
    )

    # OpenRouter-Specific (Optional)
    openrouter_app_url: Optional[str] = Field(
        default=None, description="App URL for OpenRouter analytics (optional)"
    )
    openrouter_app_title: Optional[str] = Field(
        default=None, description="App title for OpenRouter tracking (optional)"
    )

    # Application Settings
    app_env: str = Field(default="development", description="Application environment")
    log_level: str = Field(default="INFO", description="Logging level")

    # Logfire (Optional)
    logfire_token: Optional[str] = Field(
        default=None, description="Logfire API token from 'logfire auth' (optional)"
    )
    logfire_service_name: str = Field(default="skill-agent", description="Service name in Logfire")
    logfire_environment: str = Field(
        default="development", description="Environment (development, production, etc.)"
    )

    # Database (Optional - enables persistence)
    database_url: Optional[str] = Field(
        default=None, description="PostgreSQL connection URL (postgresql+asyncpg://...)"
    )
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_pool_overflow: int = Field(default=10, ge=0, le=100)

    # Embeddings (Optional - enables semantic search)
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key for embeddings (defaults to llm_api_key)"
    )
    embedding_dimensions: int = Field(default=1536)

    # Redis (Optional - enables caching layer)
    redis_url: Optional[str] = Field(
        default=None, description="Redis connection URL (redis://localhost:6379/0)"
    )
    redis_key_prefix: str = Field(default="ska:", description="Redis key namespace prefix")

    # JWT Authentication (Phase 4)
    jwt_secret_key: Optional[str] = Field(default=None, description="Secret key for JWT signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30, ge=1, description="Access token expiry in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, ge=1, description="Refresh token expiry in days"
    )

    # Admin Bootstrap (Phase 4)
    admin_email: Optional[str] = Field(default=None, description="Bootstrap admin email")
    admin_password: Optional[str] = Field(default=None, description="Bootstrap admin password")

    # CORS (Phase 4)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"], description="CORS allowed origins"
    )

    # Langfuse Observability (Phase 4)
    langfuse_public_key: Optional[str] = Field(
        default=None, description="Langfuse public key for LLM tracing"
    )
    langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret key")
    langfuse_host: Optional[str] = Field(default=None, description="Langfuse host URL")

    # Platform Integration Credentials (Phase 9)
    telegram_bot_token: Optional[str] = Field(
        default=None, description="Telegram bot token (per-connection, encrypted in DB)"
    )
    slack_signing_secret: Optional[str] = Field(
        default=None, description="Slack signing secret for webhook validation"
    )
    slack_bot_token: Optional[str] = Field(
        default=None, description="Slack bot token for API calls (xoxb-...)"
    )
    webhook_signing_secret: Optional[str] = Field(
        default=None, description="HMAC secret for signing outbound webhooks"
    )

    # Feature Flags
    feature_flags: FeatureFlags = Field(
        default_factory=FeatureFlags, description="Platform feature toggles"
    )


def load_settings() -> Settings:
    """Load settings with proper error handling."""
    try:
        return Settings()
    except Exception as e:
        error_msg = f"Failed to load settings: {e}"
        if "llm_api_key" in str(e).lower():
            error_msg += "\nMake sure to set LLM_API_KEY in your .env file"
        raise ValueError(error_msg) from e
