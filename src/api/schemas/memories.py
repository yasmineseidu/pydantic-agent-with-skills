"""Memory endpoint schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreateRequest(BaseModel):
    """Create a new memory request.

    Args:
        content: Memory content text (1-5,000 characters)
        memory_type: Type of memory ("semantic", "episodic", "procedural", etc.)
        importance: Importance score (1-10, default 5)
        subject: Optional subject/topic for filtering
        agent_id: Optional agent ID (None for user/team-level memory)
    """

    content: str = Field(..., min_length=1, max_length=5000)
    memory_type: str = "semantic"
    importance: int = Field(default=5, ge=1, le=10)
    subject: Optional[str] = None
    agent_id: Optional[UUID] = None


class MemoryResponse(BaseModel):
    """Memory record in API responses.

    Args:
        id: Unique memory identifier
        team_id: ID of the team that owns this memory
        agent_id: Optional agent ID (None for user/team-level memory)
        user_id: Optional user ID (None for agent/team-level memory)
        memory_type: Type of memory (MemoryType value)
        content: Memory content text
        subject: Optional subject/topic
        importance: Importance score (1-10)
        confidence: Confidence score (0.0-1.0)
        is_pinned: Whether this memory is pinned (always retrieved)
        status: Memory status (MemoryStatus value: "active", "superseded", "archived", "disputed")
        tier: Storage tier (MemoryTier value: "hot", "warm", "cold")
        access_count: Number of times this memory has been retrieved
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: UUID
    team_id: UUID
    agent_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    memory_type: str
    content: str
    subject: Optional[str] = None
    importance: int
    confidence: float
    is_pinned: bool
    status: str
    tier: str
    access_count: int
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(BaseModel):
    """Search memories by semantic similarity.

    Args:
        query: Search query text (1-1,000 characters)
        agent_id: Optional agent ID filter (None searches all team/user memories)
        memory_type: Optional memory type filter (e.g., "semantic", "episodic")
        limit: Max results to return (1-50, default 10)
    """

    query: str = Field(..., min_length=1, max_length=1000)
    agent_id: Optional[UUID] = None
    memory_type: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


class MemorySearchResponse(BaseModel):
    """Memory search results.

    Args:
        memories: List of matching memories (sorted by relevance score)
        query: Original search query
        total: Total number of matching memories
    """

    memories: list[MemoryResponse]
    query: str
    total: int
