# Phase 5: SSE Streaming + WebSocket -- Task Decomposition (v2 - Context-Safe)

> **Mode**: EXISTING | **Complexity Score**: 6 (Ambiguity=1, Integration=2, Novelty=1, Risk=1, Scale=1)
> **Tasks**: 25 atomic tasks | **Waves**: 10 | **Critical Path**: P5-01 -> P5-04 -> P5-08 -> P5-09 -> P5-18 -> P5-21 -> P5-22 -> P5-23 -> P5-24 -> P5-25 (depth 10)
> **Estimated Test Count**: ~55-65 new tests | **New Files**: 2 test files | **Modified Files**: 5 source files
> **Context Safety Rule**: Every task reads <=3 files, writes <=1 file, runs <=6 focused tests. Zero tasks exceed 100 lines of new code.

## Key Technical Findings

- `pydantic_ai.ui.UIAdapter` exists but requires its own request format -- doesn't support our 8-step chat flow (DB persistence, memory). **Decision: skip UIAdapter, keep `agent.iter()` + `node.stream()`**.
- Tool calls: `PartStartEvent` with `event.part.part_kind == "tool-call"` yields `ToolCallPart` (has `.tool_name`, `.args_as_dict()`, `.id`). No `ToolCallPartStartEvent`.
- `BaseHTTPMiddleware` does NOT apply to WebSocket. Rate limit manually in WS endpoint.
- WebSocket testing: `starlette.testclient.TestClient.websocket_connect()` (sync). Add `httpx-ws` dev dep.

## Integration Points (Verified via Code Read)

| Existing File | Line(s) | What Changes |
|---|---|---|
| `src/api/schemas/chat.py:55-68` | StreamChunk | MODIFY: Add tool_call/tool_result/memory_context fields |
| `src/api/schemas/chat.py` (append) | After L68 | NEW: WSClientMessage, WSServerMessage models |
| `src/api/routers/chat.py:529-888` | stream_chat() | MODIFY: Refactor into helper, add tool events |
| `src/api/routers/chat.py` (append) | After L937 | NEW: stream_chat_advanced(), agent_websocket() endpoints |
| `src/auth/dependencies.py` (append) | After L256 | NEW: authenticate_websocket() function |
| `src/api/middleware/rate_limit.py` | L160-161 | NO CHANGE: `/chat` pattern already covers new paths |
| `src/api/app.py:172-173` | chat_router mount | NO CHANGE: `/v1/agents` prefix covers new endpoints |
| `tests/test_api/conftest.py` | append | MODIFY: Add sync_client, ws_auth_token fixtures |
| `pyproject.toml` | dev deps | MODIFY: Add httpx-ws |

## Wave Plan

```
Wave 1  (3 parallel):  P5-01, P5-02, P5-03       Foundation: schemas, dep, helper extraction
Wave 2  (3 parallel):  P5-04, P5-05, P5-06       Tool events, advanced SSE, WS auth
Wave 3  (2 parallel):  P5-07, P5-11              WS skeleton, test conftest
Wave 4  (3 parallel):  P5-08, P5-10, P5-12       WS streaming, WS rate limit, SSE format tests
Wave 5  (4 parallel):  P5-09, P5-13, P5-14, P5-16  WS cancel, SSE lifecycle tests, SSE int basic, WS auth tests
Wave 6  (4 parallel):  P5-15, P5-17, P5-18, P5-19  SSE int advanced, WS protocol tests, WS cancel tests, WS rate tests
Wave 7  (2 parallel):  P5-20, P5-21              Advanced SSE tests, SSE edge cases
Wave 8  (1 task):      P5-22                      Regression tests
Wave 9  (1 task):      P5-23                      Full verification
Wave 10 (2 sequential): P5-24, P5-25             Regression check, LEARNINGS
```

## Dependency Graph

```
P5-01 (schemas) ──────────────────┐
P5-02 (httpx-ws) ────────────────┤
P5-03 (extract helper) ──────────┤
                                   │
  ┌────────────────────────────────┘
  │
  ├─> P5-04 (tool events) ──────────────────────────────────┐
  ├─> P5-05 (advanced SSE) ────────────────────────────────┤
  ├─> P5-06 (WS auth) ─────────────────────────────────────┤
  │                                                          │
  │   ┌──────────────────────────────────────────────────────┘
  │   │
  │   ├─> P5-07 (WS skeleton) ──────────────────────────────┐
  │   ├─> P5-11 (test conftest) ────────────────────────────┤
  │   │                                                      │
  │   │   ┌──────────────────────────────────────────────────┘
  │   │   │
  │   │   ├─> P5-08 (WS streaming) ──> P5-09 (WS cancel) ──┐
  │   │   ├─> P5-10 (WS rate limit) ───────────────────────┤
  │   │   ├─> P5-12 (SSE format tests) ────────────────────┤
  │   │   ├─> P5-13 (SSE lifecycle tests) ─────────────────┤
  │   │   ├─> P5-14 (SSE int basic) ───────────────────────┤
  │   │   ├─> P5-16 (WS auth tests) ──────────────────────┤
  │   │   │                                                  │
  │   │   │   ┌──────────────────────────────────────────────┘
  │   │   │   │
  │   │   │   ├─> P5-15 (SSE int advanced) ─────────────────┐
  │   │   │   ├─> P5-17 (WS protocol tests) ────────────────┤
  │   │   │   ├─> P5-18 (WS cancel tests) ──────────────────┤
  │   │   │   ├─> P5-19 (WS rate limit tests) ──────────────┤
  │   │   │   │                                               │
  │   │   │   │   ┌───────────────────────────────────────────┘
  │   │   │   │   │
  │   │   │   │   ├─> P5-20 (advanced SSE tests) ────────────┐
  │   │   │   │   ├─> P5-21 (SSE edge cases) ─────────────────┤
  │   │   │   │   │                                             │
  │   │   │   │   │   ┌─────────────────────────────────────────┘
  │   │   │   │   │   │
  │   │   │   │   │   ├─> P5-22 (regression) ─> P5-23 (verify) ─> P5-24 (regr check) ─> P5-25 (LEARNINGS)
```

---

## Wave 1: Foundation (3 parallel)

### P5-01: Extend StreamChunk Schema + Add WS Message Models

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `src/api/schemas/chat.py` (MODIFY)
- **Depends on**: None
- **Context budget**: Read 1 file (69 lines), write ~40 lines

**Description**: Add optional fields to `StreamChunk` for tool events and memory context. Add `WSClientMessage` and `WSServerMessage` Pydantic models below `StreamChunk`.

**StreamChunk additions** (add after existing fields):
- `tool_name: Optional[str] = None`
- `tool_args: Optional[dict] = None`
- `tool_call_id: Optional[str] = None`
- `tool_result_content: Optional[str] = None`
- `memory_count: Optional[int] = None`

**New models**: `WSClientMessage(type, content, conversation_id, token)` and `WSServerMessage(type, content, conversation_id, usage, tool_name, tool_args, tool_call_id, tool_result_content, error_code)`.

**Acceptance Criteria**:
- [ ] `StreamChunk(type="tool_call", tool_name="x", tool_args={})` validates
- [ ] `StreamChunk(type="content", content="hello")` still works (backward compat)
- [ ] `WSClientMessage` and `WSServerMessage` validate correctly
- [ ] `mypy src/api/schemas/chat.py` + `ruff check src/api/schemas/chat.py` clean

---

### P5-02: Add httpx-ws Dev Dependency

- **Agent**: builder | **Model**: haiku | **Complexity**: S
- **File(s)**: `pyproject.toml` (MODIFY)
- **Depends on**: None
- **Context budget**: Read 0 files, 1 command

**Description**: `uv add --dev "httpx-ws>=0.6.0"`

**Acceptance Criteria**:
- [ ] `.venv/bin/python -c "import httpx_ws; print('ok')"` succeeds
- [ ] `pyproject.toml` lists httpx-ws in dev dependencies

---

### P5-03: Extract Shared Streaming Helper from stream_chat()

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/api/routers/chat.py` (MODIFY)
- **Depends on**: None
- **Context budget**: Read 1 file (only lines 529-888 via offset/limit), write refactored helper

**Description**: Extract the inner `event_generator()` from `stream_chat()` into a standalone `_stream_agent_response()` async generator that yields `StreamChunk` objects. Then simplify `stream_chat()` to call the helper and format each chunk as SSE (`data: {json}\n\n`).

**Signature**:
```python
async def _stream_agent_response(
    agent_slug: str, body: ChatRequest, user: UserORM, team_id: UUID,
    db: AsyncSession, settings: Settings, agent_deps: AgentDependencies,
    request_id: str, *, include_tool_events: bool = False,
    include_memory_context: bool = False,
) -> AsyncIterator[StreamChunk]:
```

**CONSTRAINT**: Pure refactor. `stream_chat()` output must be byte-identical. Run ONLY the 3 existing `TestStreamChat` tests, not the full suite.

**Acceptance Criteria**:
- [ ] `_stream_agent_response()` exists with documented Args/Yields
- [ ] `stream_chat()` is now a thin SSE wrapper calling the helper
- [ ] `.venv/bin/python -m pytest tests/test_api/test_chat.py::TestStreamChat -v` passes (3 tests)
- [ ] `ruff check src/api/routers/chat.py` clean

---

## Wave 2: Endpoint Implementation (3 parallel)

### P5-04: Add Tool Call Events to Streaming Helper

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `src/api/routers/chat.py` (MODIFY)
- **Depends on**: P5-01, P5-03
- **Context budget**: Read helper function only (~80 lines), add ~15 lines

**Description**: Inside `_stream_agent_response()`, handle `PartStartEvent` with `part.part_kind == "tool-call"` to yield `StreamChunk(type="tool_call")` when `include_tool_events=True`. Add import for `ToolCallPart`, `ToolCallPartDelta`.

**New conditional** (inside the `node.stream()` event loop):
```python
elif isinstance(event, PartStartEvent) and event.part.part_kind == "tool-call":
    if include_tool_events:
        yield StreamChunk(type="tool_call", tool_name=event.part.tool_name,
                          tool_args=event.part.args_as_dict(), tool_call_id=event.part.id)
```

**Acceptance Criteria**:
- [ ] Tool call events emitted when `include_tool_events=True`
- [ ] No tool events when `include_tool_events=False` (default)
- [ ] Existing `TestStreamChat` 3 tests still pass
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-05: Implement Advanced SSE Endpoint

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/api/routers/chat.py` (MODIFY -- append)
- **Depends on**: P5-01, P5-03
- **Context budget**: Read helper signature (~10 lines), write ~40 lines new endpoint

**Description**: Add `POST /{agent_slug}/chat/stream/advanced` endpoint. It calls `_stream_agent_response(include_tool_events=True, include_memory_context=True)` and wraps each `StreamChunk` as SSE. Identical auth/deps pattern as `stream_chat()`.

**SSE event sequence**: memory_context -> typing -> text_delta* -> tool_call* -> usage -> done

**Acceptance Criteria**:
- [ ] `POST /v1/agents/{slug}/chat/stream/advanced` returns `text/event-stream`
- [ ] Calls helper with `include_tool_events=True, include_memory_context=True`
- [ ] Error events on failure (not broken stream)
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-06: Implement WebSocket Authentication Helper

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/auth/dependencies.py` (MODIFY -- append)
- **Depends on**: P5-01
- **Context budget**: Read 1 file (256 lines), write ~60 lines new function

**Description**: Add `authenticate_websocket(websocket, db, settings) -> tuple[UserORM, UUID]`. Two auth methods: (1) query param `?token=jwt` decoded before accept, (2) first message `{"type":"auth","token":"..."}` with 10s timeout after accept. On failure: close with code 4001.

**Acceptance Criteria**:
- [ ] Query param auth: extracts token, decodes JWT, returns (user, team_id)
- [ ] Message auth: accepts, waits for auth msg, decodes JWT, sends auth_ok, returns
- [ ] Auth failure closes with code 4001
- [ ] 10s timeout if no auth message received
- [ ] `mypy src/auth/dependencies.py` + `ruff check` clean

---

## Wave 3: WebSocket Skeleton + Test Infra (2 parallel)

### P5-07: WebSocket Skeleton -- Auth, Ping/Pong, Disconnect

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/api/routers/chat.py` (MODIFY -- append)
- **Depends on**: P5-01, P5-06
- **Context budget**: Read auth helper sig (~5 lines) + schema (~15 lines), write ~50 lines

**Description**: Add `@router.websocket("/{agent_slug}/ws")` endpoint with:
1. Call `authenticate_websocket()` for auth
2. Main message loop: `while True: data = await websocket.receive_json()`
3. Handle `"ping"` -> send `{"type":"pong"}`
4. Handle `"message"` -> send placeholder `{"type":"text_delta","content":"Echo: ..."}` then `{"type":"done"}`
5. Catch `WebSocketDisconnect` -> log and exit cleanly

**NOTE**: The "message" handler is a PLACEHOLDER. Real streaming wired in P5-08.

**Acceptance Criteria**:
- [ ] `WS /v1/agents/{slug}/ws?token=<jwt>` accepts and authenticates
- [ ] `{"type":"ping"}` receives `{"type":"pong"}`
- [ ] `{"type":"message","content":"hi"}` receives placeholder echo + done
- [ ] Client disconnect doesn't crash server
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-11: Add WebSocket Test Fixtures to Conftest

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `tests/test_api/conftest.py` (MODIFY)
- **Depends on**: P5-02
- **Context budget**: Read 1 file (229 lines), write ~30 lines (3 fixtures)

**Description**: Add to existing conftest:
1. `sync_client(app) -> TestClient` -- Starlette TestClient for WS testing
2. `ws_auth_token(test_user_id, test_team_id) -> str` -- valid JWT string
3. `mock_agent_for_streaming(test_team_id) -> MagicMock` -- mock AgentORM

**Acceptance Criteria**:
- [ ] 3 new fixtures importable and functional
- [ ] Existing fixtures unchanged
- [ ] `ruff check tests/test_api/conftest.py` clean

---

## Wave 4: WS Streaming + Rate Limit + First Tests (3 parallel)

### P5-08: Wire WebSocket Message Handler to Agent Streaming

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/api/routers/chat.py` (MODIFY)
- **Depends on**: P5-03, P5-04, P5-07
- **Context budget**: Read WS endpoint + helper sig (~30 lines), write ~50 lines

**Description**: Replace the placeholder echo in P5-07's "message" handler with real streaming. Create `_handle_ws_message()` that:
1. Sends `{"type":"typing"}`
2. Builds `ChatRequest` from WS message
3. Iterates `_stream_agent_response(include_tool_events=True, include_memory_context=True)`
4. Forwards each `StreamChunk` as `WSServerMessage` via `websocket.send_json()`

**Does NOT include cancel support** -- that's P5-09.

**Acceptance Criteria**:
- [ ] WS message triggers real agent streaming (not echo)
- [ ] `typing` event sent before text_delta events
- [ ] `done` event includes conversation_id and usage
- [ ] Error events on failure
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-10: WebSocket Rate Limiting (Manual Pre-Accept Check)

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `src/api/routers/chat.py` (MODIFY)
- **Depends on**: P5-07
- **Context budget**: Read WS endpoint top (~20 lines), write ~20 lines

**Description**: Add rate limit check at the top of `agent_websocket()` before auth:
- Get `rate_limiter` from `websocket.app.state`
- If available: check rate limit using client IP hash as UUID
- If exceeded: `websocket.close(code=4029, reason="Rate limit exceeded")` and return
- Also add per-message rate check in message loop (using team_id after auth)

**Acceptance Criteria**:
- [ ] Connection rejected with code 4029 when rate limited (pre-auth)
- [ ] Message rejected with error event when team rate limited (post-auth)
- [ ] Graceful degradation when Redis unavailable (allow all)
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-12: SSE Unit Tests -- Format + Event Ordering (6 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_streaming.py` (CREATE)
- **Depends on**: P5-04, P5-11
- **Context budget**: Read test_chat.py mock patterns (~50 lines for reference), write 6 tests

**Test class**: `TestSSEFormat`

**Tests (6)**:
1. `test_sse_events_have_data_prefix` -- each chunk starts with `data: ` and ends with `\n\n`
2. `test_first_chunk_has_conversation_id` -- first content chunk includes conversation_id
3. `test_subsequent_chunks_no_conversation_id` -- later chunks omit conversation_id
4. `test_usage_event_after_content` -- usage chunk after all text deltas
5. `test_done_event_is_last` -- done is the final event
6. `test_error_on_agent_not_found` -- error SSE event for missing agent slug

**Pattern**: Call `chat_module.stream_chat()` directly. Mock `skill_agent.iter()`. Consume `body_iterator`.

**Acceptance Criteria**:
- [ ] All 6 tests pass: `.venv/bin/python -m pytest tests/test_api/test_streaming.py::TestSSEFormat -v`
- [ ] Mock agent used (no real LLM calls)
- [ ] SSE format verified (`data: {...}\n\n`)
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

## Wave 5: WS Cancel + More Tests (4 parallel)

### P5-09: Add WebSocket Cancel Support

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `src/api/routers/chat.py` (MODIFY)
- **Depends on**: P5-08
- **Context budget**: Read WS message handler (~30 lines), write ~25 lines

**Description**: Wrap the streaming coroutine in `_handle_ws_message()` inside an `asyncio.Task`. Store in `active_task = {"current": None}`. In the main message loop, when `type == "cancel"`: if `active_task["current"]` is not None, call `.cancel()`. In the streaming coroutine, catch `asyncio.CancelledError` and send `WSServerMessage(type="done", content="Cancelled by client")`.

**Acceptance Criteria**:
- [ ] `{"type":"cancel"}` cancels active streaming task
- [ ] CancelledError caught cleanly, sends done event (not error)
- [ ] Cancel when no active task is a no-op (no crash)
- [ ] `ruff check src/api/routers/chat.py` clean

---

### P5-13: SSE Unit Tests -- Persistence + Lifecycle (6 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-04, P5-11
- **Context budget**: Read existing test_streaming.py (~100 lines from P5-12), write 6 tests

**Test class**: `TestSSELifecycle`

**Tests (6)**:
1. `test_error_on_inactive_agent` -- error event for paused agent
2. `test_new_conversation_created` -- no conversation_id in request creates new one
3. `test_existing_conversation_used` -- conversation_id in request reuses it
4. `test_messages_persisted_after_stream` -- user + assistant messages added to DB
5. `test_memory_extraction_triggered` -- memory extractor called after stream
6. `test_requires_team_context` -- 401 when team_id is None

**Acceptance Criteria**:
- [ ] All 6 tests pass: `.venv/bin/python -m pytest tests/test_api/test_streaming.py::TestSSELifecycle -v`
- [ ] DB mock verifies add/commit calls
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

### P5-14: SSE Integration Tests -- Basic (4 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-05, P5-11
- **Context budget**: Read conftest client fixture (~20 lines), write 4 tests

**Test class**: `TestSSEIntegrationBasic`

**Tests (4)**:
1. `test_stream_returns_event_stream_content_type` -- Content-Type header check
2. `test_stream_requires_auth` -- 401 without auth (use non-override client)
3. `test_existing_basic_stream_unchanged` -- basic `/chat/stream` still works (regression)
4. `test_advanced_endpoint_exists` -- `/chat/stream/advanced` returns 200

**Pattern**: Use `auth_client.post()` from conftest.

**Acceptance Criteria**:
- [ ] All 4 tests pass
- [ ] Uses httpx AsyncClient (integration style)
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

### P5-16: WebSocket Unit Tests -- Auth (5 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_websocket.py` (CREATE)
- **Depends on**: P5-07, P5-11
- **Context budget**: Write 5 tests with WS connect/auth patterns

**Test class**: `TestWSAuth`

**Tests (5)**:
1. `test_ws_connect_query_token` -- `?token=<jwt>` connects successfully
2. `test_ws_connect_auth_message` -- first message auth, receives auth_ok
3. `test_ws_reject_invalid_token` -- connection closed with 4001
4. `test_ws_reject_expired_token` -- connection closed with 4001
5. `test_ws_reject_no_auth_timeout` -- closed after timeout (mock asyncio.wait_for)

**Pattern**: Use `sync_client.websocket_connect()` from conftest.

**Acceptance Criteria**:
- [ ] All 5 tests pass: `.venv/bin/python -m pytest tests/test_api/test_websocket.py::TestWSAuth -v`
- [ ] WS close codes verified (4001)
- [ ] `ruff check tests/test_api/test_websocket.py` clean

---

## Wave 6: More Tests (4 parallel)

### P5-15: SSE Integration Tests -- Advanced (4 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-05, P5-11, P5-14
- **Context budget**: Read existing test classes for pattern (~30 lines), write 4 tests

**Test class**: `TestSSEIntegrationAdvanced`

**Tests (4)**:
1. `test_concurrent_streams_no_interference` -- two simultaneous streams via asyncio.gather
2. `test_stream_with_context_param` -- ChatRequest.context dict passed through
3. `test_conversation_wrong_team_error` -- SSE error for cross-team conversation access
4. `test_advanced_has_memory_context_event` -- advanced endpoint's first event is memory_context

**Acceptance Criteria**:
- [ ] All 4 tests pass
- [ ] Concurrent test uses `asyncio.gather()` (not sequential)
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

### P5-17: WebSocket Unit Tests -- Protocol (5 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_websocket.py` (MODIFY -- add class)
- **Depends on**: P5-08, P5-11
- **Context budget**: Read test_websocket.py from P5-16 (~80 lines), write 5 tests

**Test class**: `TestWSProtocol`

**Tests (5)**:
1. `test_ws_ping_pong` -- send ping, receive pong
2. `test_ws_message_triggers_streaming` -- send message, receive typing + text_delta + done
3. `test_ws_done_has_conversation_id` -- done event includes conversation_id
4. `test_ws_done_has_usage` -- done event includes usage with tokens
5. `test_ws_error_on_agent_not_found` -- error event for non-existent agent

**Acceptance Criteria**:
- [ ] All 5 tests pass: `.venv/bin/python -m pytest tests/test_api/test_websocket.py::TestWSProtocol -v`
- [ ] Mock agent streaming (no real LLM)
- [ ] `ruff check tests/test_api/test_websocket.py` clean

---

### P5-18: WebSocket Integration Tests -- Cancel + Disconnect (4 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_websocket.py` (MODIFY -- add class)
- **Depends on**: P5-09, P5-11
- **Context budget**: Read existing test classes (~50 lines), write 4 tests

**Test class**: `TestWSCancelDisconnect`

**Tests (4)**:
1. `test_cancel_stops_generation` -- send cancel during stream, receive done with "Cancelled"
2. `test_cancel_when_idle_is_noop` -- cancel with no active task doesn't crash
3. `test_client_disconnect_no_crash` -- close client mid-stream, server handles gracefully
4. `test_multiple_messages_sequential` -- send 2 messages in same connection, both get responses

**Acceptance Criteria**:
- [ ] All 4 tests pass
- [ ] Cancel test verifies streaming stops (not just done sent)
- [ ] Disconnect test verifies no server exceptions
- [ ] `ruff check tests/test_api/test_websocket.py` clean

---

### P5-19: WebSocket Integration Tests -- Rate Limit + Events (4 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_websocket.py` (MODIFY -- add class)
- **Depends on**: P5-10, P5-11
- **Context budget**: Read rate limit middleware patterns (~20 lines), write 4 tests

**Test class**: `TestWSRateLimitAndEvents`

**Tests (4)**:
1. `test_rate_limit_reject_connection` -- WS closed with 4029 when rate limited pre-auth
2. `test_rate_limit_reject_message` -- error event when team rate limit exceeded post-auth
3. `test_tool_call_events_in_ws` -- tool_call event with name, args sent during streaming
4. `test_memory_context_event_in_ws` -- memory_context event sent before streaming starts

**Acceptance Criteria**:
- [ ] All 4 tests pass
- [ ] Rate limit tests mock the rate limiter
- [ ] Tool/memory events verified with mocked agent
- [ ] `ruff check tests/test_api/test_websocket.py` clean

---

## Wave 7: Advanced + Edge Case Tests (2 parallel)

### P5-20: Advanced SSE Endpoint Tests (5 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: M
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-05, P5-14
- **Context budget**: Read test patterns (~30 lines), write 5 tests

**Test class**: `TestAdvancedSSE`

**Tests (5)**:
1. `test_memory_context_is_first_event` -- first SSE = memory_context with count
2. `test_typing_event_before_text` -- typing event before text_delta
3. `test_tool_call_event_with_fields` -- tool_call has name, args, call_id
4. `test_usage_event_before_done` -- usage with tokens before done
5. `test_full_event_ordering` -- memory_context -> typing -> text_delta -> usage -> done

**Acceptance Criteria**:
- [ ] All 5 tests pass
- [ ] Event ordering strictly verified
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

### P5-21: SSE Edge Case Tests (4 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-12, P5-13
- **Context budget**: Write 4 simple smoke tests

**Test class**: `TestSSEEdgeCases`

**Tests (4)**:
1. `test_empty_response_still_sends_done` -- agent returns empty text, done event still sent
2. `test_long_response_streams_completely` -- 1000+ char response arrives fully
3. `test_agent_error_mid_stream` -- agent exception yields error event
4. `test_sse_format_compliance` -- every event matches `data: {valid_json}\n\n`

**Acceptance Criteria**:
- [ ] All 4 tests pass
- [ ] Edge cases don't crash the stream
- [ ] `ruff check tests/test_api/test_streaming.py` clean

---

## Wave 8: Regression (1 task)

### P5-22: Regression Tests -- Non-Streaming + CLI (3 tests)

- **Agent**: builder | **Model**: sonnet | **Complexity**: S
- **File(s)**: `tests/test_api/test_streaming.py` (MODIFY -- add class)
- **Depends on**: P5-21
- **Context budget**: Write 3 simple regression tests

**Test class**: `TestPhase5Regression`

**Tests (3)**:
1. `test_nonstreaming_chat_still_works` -- Phase 4 `POST /chat` returns ChatResponse
2. `test_cli_still_launches` -- `python -m src.cli --help` exits 0
3. `test_conversation_persisted_after_stream_error` -- partial stream error still saves to DB

**Acceptance Criteria**:
- [ ] All 3 tests pass
- [ ] Non-streaming endpoint regression verified
- [ ] CLI regression verified

---

## Wave 9: Full Verification (1 task)

### P5-23: Full Verification Pass

- **Agent**: tester | **Model**: sonnet | **Complexity**: S
- **File(s)**: None (verification only)
- **Depends on**: P5-20, P5-21, P5-22
- **Context budget**: Run 4 commands, read output

**Commands**:
```bash
.venv/bin/python -m pytest tests/ -v                       # ALL tests pass
ruff check src/ tests/                                      # Clean
ruff format --check src/ tests/                             # Formatted
mypy src/                                                   # Types pass
```

**Acceptance Criteria**:
- [ ] `pytest tests/ -v` passes ALL tests (0 failures)
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` no new errors
- [ ] Total test count: ~840-850

---

## Wave 10: Regression Check + LEARNINGS (2 sequential)

### P5-24: Regression Check -- Existing Tests Untouched

- **Agent**: tester | **Model**: haiku | **Complexity**: S
- **File(s)**: None (verification only)
- **Depends on**: P5-23

**Commands**:
```bash
git diff --name-only tests/test_api/test_chat.py          # No changes
git diff --name-only tests/test_api/test_auth.py          # No changes
.venv/bin/python -m pytest tests/test_api/test_chat.py::TestStreamChat -v  # 3 original tests pass
```

**Acceptance Criteria**:
- [ ] Phase 4 test files unmodified (except conftest additions)
- [ ] `TestStreamChat` 3 original tests pass unchanged

---

### P5-25: Update LEARNINGS.md

- **Agent**: builder | **Model**: haiku | **Complexity**: S
- **File(s)**: `LEARNINGS.md` (MODIFY)
- **Depends on**: P5-24
- **Context budget**: Append ~12 lines

**Learnings to add**:
```
PATTERN: shared streaming helper → _stream_agent_response() async gen reused by SSE + WS
PATTERN: PartStartEvent part_kind → event.part.part_kind == "tool-call" for ToolCallPart
PATTERN: WS auth dual method → query param ?token=jwt or first message auth
PATTERN: WS cancel → wrap streaming in asyncio.Task, cancel on client message
PATTERN: WS rate limit → manual check before accept (code 4029)
GOTCHA: BaseHTTPMiddleware does NOT apply to WebSocket connections
GOTCHA: httpx AsyncClient has no WS support → starlette TestClient for WS tests
GOTCHA: ToolCallPartDelta not useful for events → use PartStartEvent ToolCallPart instead
GOTCHA: UIAdapter exists but needs its own request format → skip for 8-step chat flow
DECISION: UIAdapter skipped → agent.iter() + node.stream() gives full control
DECISION: No new DB tables, settings, or deps in Phase 5 (except httpx-ws dev)
```

**Acceptance Criteria**:
- [ ] LEARNINGS.md has Phase 5 section
- [ ] All entries 1-line, max 120 chars

---

## Summary

| Wave | Tasks | Max Parallel | Description |
|------|-------|-------------|-------------|
| 1 | P5-01, P5-02, P5-03 | 3 | Schemas, dep, helper extraction |
| 2 | P5-04, P5-05, P5-06 | 3 | Tool events, advanced SSE, WS auth |
| 3 | P5-07, P5-11 | 2 | WS skeleton, test conftest |
| 4 | P5-08, P5-10, P5-12 | 3 | WS streaming, WS rate limit, SSE format tests |
| 5 | P5-09, P5-13, P5-14, P5-16 | 4 | WS cancel, SSE lifecycle tests, SSE int basic, WS auth tests |
| 6 | P5-15, P5-17, P5-18, P5-19 | 4 | SSE int advanced, WS protocol tests, WS cancel tests, WS rate tests |
| 7 | P5-20, P5-21 | 2 | Advanced SSE tests, edge cases |
| 8 | P5-22 | 1 | Regression tests |
| 9 | P5-23 | 1 | Full verification |
| 10 | P5-24, P5-25 | 2 seq | Regression check, LEARNINGS |

**Total**: 25 tasks, 10 waves, max 4 agents per wave
**Critical Path**: 10 deep (P5-01 → P5-04 → P5-08 → P5-09 → P5-18 → P5-21 → P5-22 → P5-23 → P5-24 → P5-25)
**New Tests**: ~55-65 across 2 new test files
**New Source Files**: 0 (all modifications to existing)
**Modified Files**: 5 (schemas/chat.py, routers/chat.py, auth/dependencies.py, conftest.py, pyproject.toml)

## Context Budget per Task (enforced)

| Task | Files Read | Lines Written | Tests Run | Debug Risk |
|------|-----------|---------------|-----------|------------|
| P5-01 | 1 (69L) | ~40 | lint only | Low |
| P5-02 | 0 | 0 | 1 cmd | None |
| P5-03 | 1 (360L via offset) | ~100 refactor | 3 focused | Medium |
| P5-04 | 1 (~80L helper) | ~15 | 3 focused | Low |
| P5-05 | 1 (~10L sig) | ~40 | lint only | Low |
| P5-06 | 1 (256L) | ~60 | lint only | Low |
| P5-07 | 2 (~20L total) | ~50 | lint only | Low |
| P5-08 | 1 (~30L endpoint) | ~50 | lint only | Medium |
| P5-09 | 1 (~30L handler) | ~25 | lint only | Medium |
| P5-10 | 1 (~20L endpoint) | ~20 | lint only | Low |
| P5-11 | 1 (229L) | ~30 | lint only | Low |
| P5-12 | 1 (~50L patterns) | ~120 (6 tests) | 6 focused | Medium |
| P5-13 | 1 (~100L file) | ~120 (6 tests) | 6 focused | Medium |
| P5-14 | 1 (~30L patterns) | ~80 (4 tests) | 4 focused | Low |
| P5-15 | 1 (~30L patterns) | ~80 (4 tests) | 4 focused | Medium |
| P5-16 | 0 | ~100 (5 tests) | 5 focused | Medium |
| P5-17 | 1 (~80L file) | ~100 (5 tests) | 5 focused | Medium |
| P5-18 | 1 (~50L file) | ~80 (4 tests) | 4 focused | High |
| P5-19 | 1 (~20L middleware) | ~80 (4 tests) | 4 focused | Medium |
| P5-20 | 1 (~30L patterns) | ~100 (5 tests) | 5 focused | Medium |
| P5-21 | 0 | ~60 (4 tests) | 4 focused | Low |
| P5-22 | 0 | ~50 (3 tests) | 3 focused | Low |
| P5-23 | 0 | 0 | full suite | Low |
| P5-24 | 0 | 0 | 3 cmds | None |
| P5-25 | 1 (LEARNINGS) | ~12 | 0 | None |
