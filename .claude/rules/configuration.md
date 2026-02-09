---
paths: ["src/settings.py", "src/providers.py", ".env*"]
---

# Configuration Management

## Environment Variables

ALL configuration in `.env` file:

```bash
# LLM Provider
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_BASE_URL=https://openrouter.ai/api/v1

# Skills Configuration
SKILLS_DIR=skills

# Application Settings
APP_ENV=development
LOG_LEVEL=INFO
```

## Pydantic Settings

Use Pydantic Settings for type-safe configuration:

```python
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
from pathlib import Path

class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    skills_dir: Path = Field(default=Path("skills"))
    llm_api_key: str = Field(..., description="LLM provider API key")
    llm_model: str = Field(default="anthropic/claude-sonnet-4.5")
```

## Rules

- ALL secrets in `.env` only, access via `Settings(BaseSettings)` -- never `os.getenv()` directly
- `.env.example` must use PLACEHOLDER values, never real keys
- Pydantic Settings validates all config at startup
