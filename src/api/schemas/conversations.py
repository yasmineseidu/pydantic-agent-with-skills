"""Conversation endpoint schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    """Conversation metadata in API responses.

    Args:
        id: Unique conversation identifier
        team_id: ID of the team that owns this conversation
        agent_id: ID of the agent in this conversation
        user_id: ID of the user in this conversation
        title: Optional conversation title (auto-generated or user-set)
        status: Conversation status ("active", "archived")
        message_count: Number of messages in this conversation
        total_input_tokens: Total input tokens across all messages
        total_output_tokens: Total output tokens across all messages
        summary: Optional conversation summary (auto-generated for long conversations)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        last_message_at: Timestamp of the most recent message
    """

    id: UUID
    team_id: UUID
    agent_id: UUID
    user_id: UUID
    title: Optional[str] = None
    status: str
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class MessageResponse(BaseModel):
    """Message representation in API responses.

    Args:
        id: Unique message identifier
        conversation_id: ID of the parent conversation
        agent_id: Optional agent ID (None for user messages)
        role: Message role ("user" or "assistant")
        content: Message text content
        token_count: Optional token count for this message
        model: Optional model identifier used to generate this message
        created_at: Creation timestamp
    """

    id: UUID
    conversation_id: UUID
    agent_id: Optional[UUID] = None
    role: str
    content: str
    token_count: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime
