"""Chat endpoint schemas."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Send a message to an agent.

    Args:
        message: User's message text (1-10,000 characters)
        conversation_id: Optional conversation ID (None creates a new conversation)
        context: Optional additional context for the agent (e.g., {"timezone": "America/New_York"})
    """

    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[UUID] = None
    context: Optional[dict] = None


class ChatUsage(BaseModel):
    """Token usage for a chat request/response.

    Args:
        input_tokens: Number of tokens in the input (user message + system prompt + context)
        output_tokens: Number of tokens generated in the response
        model: Model identifier used for generation (e.g., "anthropic/claude-sonnet-4.5")
    """

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class ChatResponse(BaseModel):
    """Agent's response to a chat message.

    Args:
        response: Agent's text response
        conversation_id: ID of the conversation (new or existing)
        message_id: ID of the agent's response message
        usage: Token usage statistics
        request_id: Unique request ID for tracing
    """

    response: str
    conversation_id: UUID
    message_id: UUID
    usage: ChatUsage
    request_id: str


class StreamChunk(BaseModel):
    """Server-Sent Events stream chunk for chat streaming.

    Args:
        type: Chunk type - "content" (text delta), "usage" (token stats), "done" (completion), "error"
        content: Text content for content chunks, error message for error chunks
        conversation_id: Conversation ID (sent in first chunk only)
        usage: Token usage statistics (sent in usage chunk only)
    """

    type: str  # "content", "usage", "done", "error"
    content: str = ""
    conversation_id: Optional[UUID] = None
    usage: Optional[ChatUsage] = None
