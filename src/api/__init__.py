"""FastAPI REST API package."""

from src.api.app import create_app, lifespan
from src.api.dependencies import (
    get_agent_deps,
    get_db,
    get_rate_limiter,
    get_redis_manager,
    get_settings,
)

__all__ = [
    "create_app",
    "lifespan",
    "get_db",
    "get_settings",
    "get_redis_manager",
    "get_rate_limiter",
    "get_agent_deps",
]
