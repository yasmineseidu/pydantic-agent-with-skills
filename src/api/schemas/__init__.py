"""API request/response schemas."""

from src.api.schemas.agents import AgentCreate, AgentResponse, AgentUpdate
from src.api.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserMeResponse,
)
from src.api.schemas.chat import ChatRequest, ChatResponse, ChatUsage, StreamChunk
from src.api.schemas.collaboration import (
    CollaborationParticipantsRequest,
    CollaborationRecommendRequest,
    CollaborationRouteRequest,
    CollaborationSessionCreateRequest,
    CollaborationStatusUpdateRequest,
    HandoffRecordResponse,
    HandoffRequest,
)
from src.api.schemas.common import (
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
    ServiceStatus,
    SuccessResponse,
)
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
    "ServiceStatus",
    "HealthResponse",
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "TokenPair",
    "RefreshRequest",
    "ApiKeyCreate",
    "ApiKeyResponse",
    "ApiKeyCreatedResponse",
    "UserMeResponse",
    # Agents
    "AgentCreate",
    "AgentUpdate",
    "AgentResponse",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "ChatUsage",
    "StreamChunk",
    # Collaboration
    "CollaborationRouteRequest",
    "CollaborationRecommendRequest",
    "HandoffRequest",
    "HandoffRecordResponse",
    "CollaborationSessionCreateRequest",
    "CollaborationParticipantsRequest",
    "CollaborationStatusUpdateRequest",
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
