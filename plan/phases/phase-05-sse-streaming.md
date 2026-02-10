# Phase 5: SSE Streaming + WebSocket

> **Timeline**: Week 3-4 | **Prerequisites**: Phase 4 (Auth + API) | **Status**: Not Started

## Goal

Add real-time streaming to the chat endpoint using Pydantic AI's built-in UIAdapter for SSE, and a WebSocket endpoint for bidirectional communication. SSE is for simple clients, WebSocket for clients needing cancel/typing indicators.

## Dependencies (Install)

```toml
# No new dependencies required.
# FastAPI (Phase 4) already has native SSE/WebSocket support.
# Pydantic AI (existing) provides UIAdapter for SSE encoding.
#
# Already installed:
#   "fastapi~=0.115.0"      -- SSE via StreamingResponse, WebSocket built-in
#   "pydantic-ai"           -- UIAdapter for SSE event formatting
```

## Settings Extensions

```python
# No new settings fields in Phase 5.
# Streaming configuration uses the existing agent/model settings.
```

## New Directories & Files

```
api/routers/
    chat.py               # MODIFIED - Add streaming endpoints to existing chat router
                          #   POST /v1/agents/{slug}/chat/stream          (SSE simple)
                          #   POST /v1/agents/{slug}/chat/stream/advanced (SSE custom events)
                          #   WS   /v1/agents/{slug}/ws                   (WebSocket)
```

No new directories are created. Phase 5 adds endpoints to the existing `api/routers/chat.py` from Phase 4 and adds test files.

## Database Tables Introduced

None -- this phase uses existing tables from Phase 1 (conversation, message) and Phase 4 (usage_log). No schema changes.

Reference: `plan/sql/schema.sql` (no Phase 5 section -- no new tables)

## Implementation Details

### SSE Streaming via Pydantic AI UIAdapter

Pydantic AI provides a built-in `UIAdapter` pattern that eliminates manual SSE event formatting. This is the recommended approach.

#### Simple Dispatch (recommended for most endpoints)

```python
from pydantic_ai.ui import UIAdapter
from fastapi import Request, Response

@router.post("/v1/agents/{agent_slug}/chat/stream")
async def chat_stream(
    agent_slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream agent response via SSE using Pydantic AI UIAdapter."""
    agent = resolve_agent(agent_slug, current_user.team_id)
    deps = build_deps(agent, current_user)

    # UIAdapter handles SSE encoding, streaming, and error handling
    return await UIAdapter.dispatch_request(
        request,
        agent=agent.pydantic_agent,
        deps=deps,
    )
```

> **Key insight**: Pydantic AI's UIAdapter handles the SSE protocol correctly (event formatting, keep-alive, error boundaries). Don't reinvent this.

#### Advanced Control (when we need custom events like memory_context)

```python
@router.post("/v1/agents/{agent_slug}/chat/stream/advanced")
async def chat_stream_advanced(
    agent_slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Fine-grained streaming with custom events.

    Uses UIAdapter's building blocks individually:
    1. build_run_input() - Parse request
    2. run_stream_events() - Get raw AgentStreamEvents
    3. Custom encoding - Add memory_context, usage events
    4. streaming_response() - Return SSE response
    """
    run_input = await UIAdapter.build_run_input(await request.body())
    adapter = UIAdapter(agent=agent.pydantic_agent, run_input=run_input)

    async def event_generator():
        # Inject memory context event before streaming
        yield f"data: {json.dumps({'type': 'memory_context', 'count': len(memories)})}\n\n"

        async for event in adapter.run_stream_events():
            yield adapter.encode_event(event)

        # Inject usage event after completion
        yield f"data: {json.dumps({'type': 'usage', ...})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

The advanced endpoint adds these custom SSE events that the simple dispatch does not include:

1. **`memory_context`** (before streaming) -- tells client how many memories were retrieved
2. **`usage`** (after completion) -- token counts and cost estimate
3. **`tool_call`** (during streaming) -- structured tool call events from Pydantic AI

### SSE Event Format

SSE events follow the standard `text/event-stream` format:

```
data: {"type": "text_delta", "content": "Hello"}\n\n
data: {"type": "text_delta", "content": " there"}\n\n
data: {"type": "tool_call", "name": "load_skill", "args": {"skill_name": "weather"}}\n\n
data: {"type": "tool_result", "name": "load_skill", "result": "..."}\n\n
data: {"type": "memory_context", "count": 5}\n\n
data: {"type": "done", "conversation_id": "abc-123", "usage": {"input_tokens": 500, "output_tokens": 200}}\n\n
data: {"type": "error", "message": "Rate limited", "code": "rate_limited"}\n\n
```

### WebSocket Endpoint (Optional Enhancement)

```python
@router.websocket("/v1/agents/{agent_slug}/ws")
async def agent_websocket(
    websocket: WebSocket,
    agent_slug: str,
):
    """
    Bidirectional WebSocket for agent chat.

    Client -> Server: {"type": "message", "content": "..."}
    Client -> Server: {"type": "cancel"}  # Cancel current generation
    Client -> Server: {"type": "ping"}

    Server -> Client: {"type": "text_delta", "content": "..."}
    Server -> Client: {"type": "tool_call", ...}
    Server -> Client: {"type": "done", ...}
    Server -> Client: {"type": "pong"}
    """
```

WebSocket adds capabilities beyond SSE:
- **Client can cancel mid-generation** -- send `{"type": "cancel"}` to stop the agent
- **Typing indicators** -- server can send `{"type": "typing"}` before generation starts
- **Real-time memory notifications** -- `{"type": "memory_notification", "content": "I remembered something relevant..."}`
- **Bidirectional** -- client can send messages without establishing a new connection

### WebSocket Protocol

#### Client-to-Server Messages

| Type | Payload | Description |
|------|---------|-------------|
| `message` | `{"type": "message", "content": "...", "conversation_id": "..."}` | Send a chat message |
| `cancel` | `{"type": "cancel"}` | Cancel current generation |
| `ping` | `{"type": "ping"}` | Keep-alive |

#### Server-to-Client Messages

| Type | Payload | Description |
|------|---------|-------------|
| `text_delta` | `{"type": "text_delta", "content": "..."}` | Streamed text chunk |
| `tool_call` | `{"type": "tool_call", "name": "...", "args": {...}}` | Tool invocation |
| `tool_result` | `{"type": "tool_result", "name": "...", "result": "..."}` | Tool result |
| `done` | `{"type": "done", "conversation_id": "...", "usage": {...}}` | Generation complete |
| `error` | `{"type": "error", "message": "...", "code": "..."}` | Error occurred |
| `typing` | `{"type": "typing"}` | Agent is preparing response |
| `memory_notification` | `{"type": "memory_notification", "content": "..."}` | Memory-related notification |
| `pong` | `{"type": "pong"}` | Keep-alive response |

### WebSocket Authentication

WebSocket connections authenticate via:
1. Query parameter: `?token=<jwt_access_token>`
2. Or first message: `{"type": "auth", "token": "<jwt_access_token>"}`

The connection is rejected if auth fails.

### Integration with Existing Chat Flow

Both SSE and WebSocket endpoints follow the same core flow as the non-streaming chat endpoint from Phase 4:

```
1. Resolve agent by slug + team
2. Load/create conversation
3. Retrieve relevant memories
4. Build memory-aware prompt
5. Run agent with Pydantic AI (stream mode)
6. Stream response to client (SSE events or WS messages)
7. Persist messages (after stream completes)
8. Trigger async memory extraction (Celery task in Phase 6, or inline)
9. Send done/usage event
```

The key difference is step 5-6: instead of waiting for the full response, we stream token-by-token using Pydantic AI's streaming API.

### Error Handling During Streaming

Errors during streaming are sent as structured events, not HTTP error codes (since the response has already started):

```python
# SSE
yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'code': 'internal_error'})}\n\n"

# WebSocket
await websocket.send_json({"type": "error", "message": str(e), "code": "internal_error"})
```

Pre-streaming errors (auth failure, agent not found, rate limited) still return standard HTTP error responses.

## Tests

```
tests/test_api/
    test_streaming.py     # SSE event format, ordering, error handling
    test_websocket.py     # WS connect, message, cancel, disconnect
```

### Key Test Scenarios

- SSE simple endpoint streams text_delta events token-by-token
- SSE advanced endpoint includes memory_context event before streaming
- SSE advanced endpoint includes usage event after streaming completes
- Tool calls emit structured tool_call events during SSE stream
- SSE error events are sent on failure (stream not broken silently)
- SSE response has correct Content-Type: `text/event-stream`
- SSE events follow standard format: `data: {...}\n\n`
- Usage stats (input_tokens, output_tokens) sent in `done` event
- WebSocket connects successfully with valid JWT token
- WebSocket rejects connection with invalid/expired token
- WebSocket receives text_delta events during streaming
- WebSocket client can cancel mid-generation with `{"type": "cancel"}`
- WebSocket cancel actually stops the LLM generation
- WebSocket handles client disconnect gracefully (no server crash)
- WebSocket ping/pong keep-alive works
- WebSocket error events sent on failure
- Conversation is persisted after streaming completes (both SSE and WS)
- Memory extraction triggers after streaming completes
- Multiple concurrent SSE streams work without interference
- Rate limiting applies to streaming endpoints (checked before streaming starts)
- Non-streaming chat endpoint (Phase 4) still works unchanged
- All existing tests pass
- CLI still works

## Acceptance Criteria

- [ ] SSE endpoint streams token-by-token (text_delta events)
- [ ] Tool calls emit structured events during stream
- [ ] Usage stats sent in `done` event after stream completes
- [ ] Error events sent on failure (not a broken/silent stream)
- [ ] WebSocket connects and exchanges messages bidirectionally
- [ ] Client cancel stops generation (WebSocket)
- [ ] Non-streaming chat endpoint (Phase 4) unaffected
- [ ] All existing tests pass
- [ ] CLI still works

## Rollback Strategy

**Rollback Method**: Remove streaming endpoints from `api/routers/chat.py`. The non-streaming chat endpoint from Phase 4 remains functional.

**Detailed steps**:
1. Remove the `/chat/stream`, `/chat/stream/advanced`, and `/ws` endpoint functions from `api/routers/chat.py`
2. Remove `tests/test_api/test_streaming.py` and `tests/test_api/test_websocket.py`
3. Verify: non-streaming `POST /v1/agents/{slug}/chat` still works
4. Verify: `.venv/bin/python -m pytest tests/ -v` passes
5. Verify: `python -m src.cli` still works

No database changes to revert. No new tables or migrations in this phase.

## Links to Main Plan

- Section 4, Phase 5 (SSE Streaming + WebSocket) -- primary spec
- Section 5.1 (SSE Streaming via Pydantic AI UIAdapter) -- UIAdapter pattern
- Section 5.2 (WebSocket Optional Enhancement) -- WebSocket protocol
- Section 10 (Performance Targets) -- First SSE token < 2s target
- Section 16 (API Design Conventions) -- error response format, rate limits
- Section 23 (Rollback Strategy) -- Phase 5 rollback method
- ADR-3 (FastAPI) -- native SSE/WebSocket support rationale
