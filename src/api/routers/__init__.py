"""FastAPI routers for the Skill Agent API."""

from src.api.routers.agents import router as agents_router
from src.api.routers.auth import router as auth_router
from src.api.routers.chat import router as chat_router
from src.api.routers.conversations import router as conversations_router
from src.api.routers.health import router as health_router
from src.api.routers.memories import router as memories_router
from src.api.routers.teams import router as teams_router

__all__ = [
    "health_router",
    "auth_router",
    "agents_router",
    "teams_router",
    "chat_router",
    "memories_router",
    "conversations_router",
]
