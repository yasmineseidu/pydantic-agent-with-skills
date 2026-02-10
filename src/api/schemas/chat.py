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
        type: Chunk type - "content" (text delta), "usage" (token stats),
            "done" (completion), "error", "tool_call", "tool_result",
            "memory_context"
        content: Text content for content chunks, error message for error chunks
        conversation_id: Conversation ID (sent in first chunk only)
        usage: Token usage statistics (sent in usage chunk only)
        tool_name: Name of the tool being called (tool_call chunks)
        tool_args: Arguments passed to the tool (tool_call chunks)
        tool_call_id: Unique identifier for a tool call/result pair
        tool_result_content: Result returned by the tool (tool_result chunks)
        memory_count: Number of memory entries loaded (memory_context chunks)
    """

    type: str  # "content", "usage", "done", "error", "tool_call", "tool_result", "memory_context"
    content: str = ""
    conversation_id: Optional[UUID] = None
    usage: Optional[ChatUsage] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_call_id: Optional[str] = None
    tool_result_content: Optional[str] = None
    memory_count: Optional[int] = None


class WSClientMessage(BaseModel):
    """WebSocket message from client to server.

    Args:
        type: Message type - "auth", "message", "ping", "cancel"
        content: Message text content (for "message" type)
        conversation_id: Conversation to continue (for "message" type)
        token: Authentication token (for "auth" type)
    """

    type: str  # "auth", "message", "ping", "cancel"
    content: Optional[str] = None
    conversation_id: Optional[UUID] = None
    token: Optional[str] = None


class WSServerMessage(BaseModel):
    """WebSocket message from server to client.

    Args:
        type: Message type - "auth_ok", "text_delta", "tool_call",
            "tool_result", "memory_context", "typing", "usage", "done",
            "error", "pong"
        content: Text content or error message
        conversation_id: Conversation ID for this message stream
        usage: Token usage statistics (sent in "usage" type)
        tool_name: Name of the tool being called ("tool_call" type)
        tool_args: Arguments passed to the tool ("tool_call" type)
        tool_call_id: Unique identifier for a tool call/result pair
        tool_result_content: Result returned by the tool ("tool_result" type)
        error_code: HTTP-style error code ("error" type)
    """

    type: str  # "auth_ok", "text_delta", "tool_call", "tool_result", "memory_context", "typing", "usage", "done", "error", "pong"
    content: str = ""
    conversation_id: Optional[UUID] = None
    usage: Optional[ChatUsage] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_call_id: Optional[str] = None
    tool_result_content: Optional[str] = None
    error_code: Optional[int] = None
