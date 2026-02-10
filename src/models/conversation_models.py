"""Pydantic models for conversations and messages."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationStatus(str, Enum):
    """Status of a conversation session."""

    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


class MessageRole(str, Enum):
    """Role of a message sender."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationCreate(BaseModel):
    """Request model for creating a conversation.

    Requires team, agent, and user identifiers. Title is optional
    and can be auto-generated from the first message.
    """

    team_id: UUID
    agent_id: UUID
    user_id: UUID
    title: Optional[str] = None


class ConversationRecord(BaseModel):
    """Full conversation record as returned from the database.

    Mirrors all columns in the conversation table including
    token counts, summary, and timing fields.
    """

    id: UUID
    team_id: UUID
    agent_id: UUID
    user_id: UUID
    title: Optional[str] = None
    status: ConversationStatus = ConversationStatus.ACTIVE
    message_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    summary: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class MessageCreate(BaseModel):
    """Request model for creating a message.

    Contains the content and role for a new message in a conversation.
    Tool call data and token count are optional.
    """

    conversation_id: UUID
    role: MessageRole
    content: str
    agent_id: Optional[UUID] = None
    tool_calls: Optional[dict[str, Any]] = None
    tool_results: Optional[dict[str, Any]] = None
    token_count: Optional[int] = None
    model: Optional[str] = None


class MessageRecord(BaseModel):
    """Full message record as returned from the database.

    Mirrors all columns in the message table including tool
    interactions, token usage, and feedback fields.
    """

    id: UUID
    conversation_id: UUID
    agent_id: Optional[UUID] = None
    role: MessageRole
    content: str
    tool_calls: Optional[dict[str, Any]] = None
    tool_results: Optional[dict[str, Any]] = None
    token_count: Optional[int] = None
    model: Optional[str] = None
    feedback_rating: Optional[str] = None
    feedback_comment: Optional[str] = None
    created_at: datetime
