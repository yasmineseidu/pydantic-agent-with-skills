"""FastAPI routers for the Skill Agent API."""

from src.api.routers.agents import router as agents_router
from src.api.routers.auth import router as auth_router
from src.api.routers.chat import router as chat_router
from src.api.routers.collaboration import router as collaboration_router
from src.api.routers.conversations import router as conversations_router
from src.api.routers.health import router as health_router
from src.api.routers.memories import router as memories_router
from src.api.routers.teams import router as teams_router
from src.api.routers.webhooks import router as webhooks_router

__all__ = [
    "health_router",
    "auth_router",
    "agents_router",
    "teams_router",
    "chat_router",
    "memories_router",
    "conversations_router",
    "collaboration_router",
    "webhooks_router",
]
