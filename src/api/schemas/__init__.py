"""API request/response schemas."""

from src.api.schemas.agents import AgentCreate, AgentResponse, AgentUpdate
from src.api.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from src.api.schemas.chat import ChatRequest, ChatResponse, ChatUsage
from src.api.schemas.common import ErrorResponse, PaginatedResponse, SuccessResponse
from src.api.schemas.conversations import ConversationResponse, MessageResponse
from src.api.schemas.memories import (
    MemoryCreateRequest,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)
from src.api.schemas.teams import (
    MemberAdd,
    MemberResponse,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
    UsageSummary,
)

__all__ = [
    # Common
    "ErrorResponse",
    "SuccessResponse",
    "PaginatedResponse",
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "LoginResponse",
    "TokenPair",
    "RefreshRequest",
    "ApiKeyCreate",
    "ApiKeyResponse",
    "ApiKeyCreatedResponse",
    # Agents
    "AgentCreate",
    "AgentUpdate",
    "AgentResponse",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "ChatUsage",
    # Memories
    "MemoryCreateRequest",
    "MemoryResponse",
    "MemorySearchRequest",
    "MemorySearchResponse",
    # Conversations
    "ConversationResponse",
    "MessageResponse",
    # Teams
    "TeamCreate",
    "TeamUpdate",
    "TeamResponse",
    "MemberAdd",
    "MemberResponse",
    "UsageSummary",
]
