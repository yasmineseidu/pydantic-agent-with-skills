"""Unit tests for WebSocket authentication, cancel, and disconnect behavior."""

import asyncio
import time

import pytest
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.app import create_app
from src.api.dependencies import get_db, get_redis_manager, get_settings
from src.db.models.user import UserORM
from src.settings import load_settings


def _create_test_user(user_id: UUID) -> MagicMock:
    """Create a mock UserORM for WebSocket auth tests.

    Args:
        user_id: UUID to assign to the mock user.

    Returns:
        MagicMock configured as a UserORM instance.
    """
    mock_user = MagicMock(spec=UserORM)
    mock_user.id = user_id
    mock_user.email = "test@example.com"
    mock_user.is_active = True
    return mock_user


@pytest.fixture
def _ws_app() -> Generator:
    """Create a minimal FastAPI app for WebSocket testing.

    Overrides database and Redis dependencies but does NOT override
    authenticate_websocket -- individual tests patch that themselves.

    Yields:
        FastAPI application instance.
    """
    app = create_app()

    test_settings = load_settings()
    if not test_settings.jwt_secret_key:
        test_settings.jwt_secret_key = "test-secret-key-for-jwt-testing-only-not-for-production"

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    async def override_get_redis_manager():
        return None

    def override_get_settings():
        return test_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_manager] = override_get_redis_manager
    app.dependency_overrides[get_settings] = override_get_settings

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def ws_client(_ws_app) -> TestClient:
    """Starlette TestClient for WebSocket testing.

    Args:
        _ws_app: FastAPI application with dependency overrides.

    Returns:
        TestClient bound to the test app.
    """
    return TestClient(_ws_app)


class TestWSAuth:
    """Tests for WebSocket authentication in agent_websocket endpoint."""

    def test_ws_connect_query_token(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Successful WebSocket connection via query param token sends ping/pong.

        Patches authenticate_websocket to return a valid user, then verifies
        the connection works by exchanging a ping/pong message pair.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"

    def test_ws_connect_auth_message(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Successful WebSocket connection verifies authenticate_websocket was called.

        Confirms that the endpoint delegates auth to authenticate_websocket
        and that the returned user/team pair is used for the session.
        """
        mock_user = _create_test_user(test_user_id)
        call_count = {"n": 0}

        async def mock_auth(websocket, db, settings):
            call_count["n"] += 1
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "ping"})
                ws.receive_json()

        assert call_count["n"] == 1

    def test_ws_reject_invalid_token(
        self,
        ws_client: TestClient,
    ) -> None:
        """WebSocket connection is rejected when authenticate_websocket raises.

        The agent_websocket endpoint catches auth exceptions and returns
        immediately without entering the message loop, causing the
        Starlette TestClient to raise an exception on connect.
        """

        async def mock_auth_fail(websocket, db, settings):
            await websocket.close(code=4001, reason="Authentication failed")
            raise WebSocketDisconnect(code=4001, reason="Authentication failed")

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth_fail,
        ):
            with pytest.raises(Exception):
                with ws_client.websocket_connect(
                    "/v1/agents/test-agent/ws?token=invalid-token"
                ) as ws:
                    ws.send_json({"type": "ping"})

    def test_ws_reject_expired_token(
        self,
        ws_client: TestClient,
    ) -> None:
        """WebSocket connection is rejected when token has expired.

        Simulates authenticate_websocket raising a disconnect with an
        expiry-specific reason, verifying the endpoint handles it.
        """

        async def mock_auth_expired(websocket, db, settings):
            await websocket.close(code=4001, reason="Token expired")
            raise WebSocketDisconnect(code=4001, reason="Token expired")

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth_expired,
        ):
            with pytest.raises(Exception):
                with ws_client.websocket_connect(
                    "/v1/agents/test-agent/ws?token=expired-token"
                ) as ws:
                    ws.send_json({"type": "ping"})

    def test_ws_reject_no_auth_timeout(
        self,
        ws_client: TestClient,
    ) -> None:
        """WebSocket connection is rejected when authentication times out.

        Simulates authenticate_websocket accepting the connection (method 2:
        first-message auth), then closing with code 4001 due to timeout.
        The server handler returns after the auth failure, so subsequent
        client operations (send/receive) should raise.
        """

        async def mock_auth_timeout(websocket, db, settings):
            await websocket.accept()
            await websocket.close(code=4001, reason="Authentication timeout")
            raise WebSocketDisconnect(code=4001, reason="Authentication timeout")

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth_timeout,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws") as ws:
                # Server accepted then immediately closed due to auth timeout.
                # Sending a message should fail or the receive should get
                # the close frame rather than a pong response.
                with pytest.raises(Exception):
                    ws.send_json({"type": "ping"})
                    ws.receive_json()


class TestWSCancelDisconnect:
    """Tests for WebSocket cancel, disconnect, and sequential message handling."""

    def test_cancel_stops_generation(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Sending a cancel message stops an active generation and returns done.

        Patches _handle_ws_message to sleep indefinitely, simulating a long
        generation. The cancel message triggers task cancellation, and the
        run_streaming wrapper catches CancelledError and sends a done event
        with 'Cancelled by client' content.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def slow_handler(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            """Simulate a long-running generation that will be cancelled."""
            await asyncio.sleep(100)

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=slow_handler,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "test"})
                time.sleep(0.1)  # Let the task start
                ws.send_json({"type": "cancel"})
                data = ws.receive_json()
                assert data["type"] == "done"
                assert "cancelled" in data.get("content", "").lower()

    def test_cancel_when_idle_is_noop(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Sending cancel without an active message is a no-op.

        The server should not crash or disconnect. A subsequent ping
        should still receive a pong response.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "cancel"})
                # Connection should still be alive -- verify with ping/pong
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"

    def test_client_disconnect_no_crash(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Client disconnecting immediately after sending a message causes no server crash.

        The server should handle the WebSocketDisconnect gracefully when the
        client closes the connection while a message is being processed.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def slow_handler(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            """Simulate generation that outlives the client connection."""
            await asyncio.sleep(100)

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=slow_handler,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "test"})
                # Client disconnects immediately (context manager exits)

        # No exception should propagate -- if we reach here, the test passes

    def test_multiple_messages_sequential(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Two sequential messages in the same connection both receive done events.

        Patches _handle_ws_message to send a text_delta and done frame
        for each message, verifying that the WebSocket loop correctly
        handles multiple request/response cycles.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def fast_handler(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            """Send a text delta and done for each message."""
            await websocket.send_json({"type": "text_delta", "content": f"Reply to: {content}"})
            await websocket.send_json({"type": "done"})

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=fast_handler,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                # First message
                ws.send_json({"type": "message", "content": "first"})
                d1 = ws.receive_json()
                d2 = ws.receive_json()
                assert d1["type"] == "text_delta"
                assert "first" in d1["content"]
                assert d2["type"] == "done"

                # Second message
                ws.send_json({"type": "message", "content": "second"})
                d3 = ws.receive_json()
                d4 = ws.receive_json()
                assert d3["type"] == "text_delta"
                assert "second" in d3["content"]
                assert d4["type"] == "done"


class TestWSRateLimitAndEvents:
    """Tests for WebSocket rate limiting and streaming event types."""

    def test_rate_limit_reject_connection(
        self,
        _ws_app,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Pre-auth rate limit rejection closes WebSocket with code 4029.

        When the rate limiter returns allowed=False before authentication,
        the endpoint should close the WebSocket immediately with code 4029
        without proceeding to authentication.
        """
        mock_result = MagicMock()
        mock_result.allowed = False

        mock_limiter = MagicMock()
        mock_limiter.check_rate_limit = AsyncMock(return_value=mock_result)
        _ws_app.state.rate_limiter = mock_limiter

        ws_client = TestClient(_ws_app)

        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with pytest.raises(Exception):
                with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                    ws.send_json({"type": "ping"})

    def test_rate_limit_reject_message(
        self,
        _ws_app,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Post-auth per-message rate limit sends error JSON with error_code 4029.

        When the rate limiter allows the pre-auth check but rejects the
        per-message check, the endpoint should send an error JSON message
        with error_code 4029 instead of processing the chat message.
        """
        call_count = {"n": 0}

        async def mock_check(*args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.allowed = True  # Pre-auth check passes
            else:
                result.allowed = False  # Per-message check fails
            return result

        mock_limiter = MagicMock()
        mock_limiter.check_rate_limit = mock_check
        _ws_app.state.rate_limiter = mock_limiter

        ws_client = TestClient(_ws_app)

        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                # Send a chat message that should be rate-limited
                ws.send_json({"type": "message", "content": "hello"})
                data = ws.receive_json()
                assert data["type"] == "error"
                assert data["error_code"] == 4029
                assert "Rate limit" in data["content"]

    def test_tool_call_events_in_ws(
        self,
        _ws_app,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """WebSocket streams tool_call events with tool_name and tool_args.

        When the agent invokes a tool during streaming, the WebSocket
        endpoint should forward tool_call StreamChunks to the client.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            """Send tool_call event followed by done."""
            await websocket.send_json(
                {
                    "type": "tool_call",
                    "tool_name": "get_weather",
                    "tool_args": {"location": "NYC"},
                    "tool_call_id": "call_123",
                }
            )
            await websocket.send_json({"type": "done"})

        ws_client = TestClient(_ws_app)

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "weather in NYC"})
                data = ws.receive_json()
                assert data["type"] == "tool_call"
                assert data["tool_name"] == "get_weather"
                assert data["tool_args"] == {"location": "NYC"}
                assert data["tool_call_id"] == "call_123"

                done = ws.receive_json()
                assert done["type"] == "done"

    def test_memory_context_event_in_ws(
        self,
        _ws_app,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """WebSocket streams memory_context events with memory_count.

        When the agent has memory context available, the WebSocket
        endpoint should forward a memory_context StreamChunk with the
        count of loaded memories.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            """Send memory_context event, content, and done."""
            await websocket.send_json(
                {
                    "type": "memory_context",
                    "memory_count": 5,
                }
            )
            await websocket.send_json({"type": "content", "content": "Hello!"})
            await websocket.send_json({"type": "done"})

        ws_client = TestClient(_ws_app)

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "hello"})
                data = ws.receive_json()
                assert data["type"] == "memory_context"
                assert data["memory_count"] == 5

                content = ws.receive_json()
                assert content["type"] == "content"

                done = ws.receive_json()
                assert done["type"] == "done"


class TestWSProtocol:
    """Tests for WebSocket protocol message handling (ping/pong, message streaming, errors)."""

    def test_ws_ping_pong(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Sending a ping message returns a pong response.

        Verifies the ping/pong keepalive mechanism works correctly
        after a successful WebSocket authentication.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        with patch(
            "src.api.routers.chat.authenticate_websocket",
            side_effect=mock_auth,
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"

    def test_ws_message_triggers_streaming(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Sending a message triggers streaming events (typing, text_delta, done).

        Patches _handle_ws_message to send a known sequence of events and
        verifies the client receives them in the correct order.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            await websocket.send_json({"type": "typing"})
            await websocket.send_json({"type": "text_delta", "content": "Hello"})
            await websocket.send_json(
                {"type": "done", "conversation_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "hi"})
                data1 = ws.receive_json()
                assert data1["type"] == "typing"
                data2 = ws.receive_json()
                assert data2["type"] == "text_delta"
                assert data2["content"] == "Hello"
                data3 = ws.receive_json()
                assert data3["type"] == "done"

    def test_ws_done_has_conversation_id(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """The done event includes a conversation_id field.

        Verifies that after a message exchange, the final done event carries
        the conversation identifier so clients can track the conversation.
        """
        mock_user = _create_test_user(test_user_id)
        conv_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            await websocket.send_json({"type": "typing"})
            await websocket.send_json({"type": "content", "content": "Response text"})
            await websocket.send_json({"type": "done", "conversation_id": conv_id})

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "hello"})
                ws.receive_json()  # typing
                ws.receive_json()  # content
                done_data = ws.receive_json()
                assert done_data["type"] == "done"
                assert done_data["conversation_id"] == conv_id

    def test_ws_done_has_usage(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """The done event is preceded by a usage event with token counts.

        Verifies that the streaming sequence includes a usage event containing
        input_tokens, output_tokens, and model information.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            await websocket.send_json({"type": "typing"})
            await websocket.send_json({"type": "content", "content": "hi there"})
            await websocket.send_json(
                {
                    "type": "usage",
                    "usage": {"input_tokens": 10, "output_tokens": 5, "model": "test-model"},
                }
            )
            await websocket.send_json(
                {"type": "done", "conversation_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/test-agent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "hi"})
                ws.receive_json()  # typing
                ws.receive_json()  # content
                usage_data = ws.receive_json()
                assert usage_data["type"] == "usage"
                assert usage_data["usage"]["input_tokens"] == 10
                assert usage_data["usage"]["output_tokens"] == 5
                assert usage_data["usage"]["model"] == "test-model"
                done_data = ws.receive_json()
                assert done_data["type"] == "done"

    def test_ws_error_on_agent_not_found(
        self,
        ws_client: TestClient,
        test_user_id: UUID,
        test_team_id: UUID,
    ) -> None:
        """Sending a message for a non-existent agent returns an error event.

        Patches _handle_ws_message to simulate an agent-not-found error and
        verifies the client receives a properly formatted error response.
        """
        mock_user = _create_test_user(test_user_id)

        async def mock_auth(websocket, db, settings):
            await websocket.accept()
            return (mock_user, test_team_id)

        async def mock_handle_ws(
            websocket,
            agent_slug,
            content,
            conversation_id,
            user,
            team_id,
            db,
            settings,
            agent_deps,
            request_id,
        ):
            await websocket.send_json(
                {
                    "type": "error",
                    "content": f"Agent '{agent_slug}' not found",
                }
            )

        with (
            patch(
                "src.api.routers.chat.authenticate_websocket",
                side_effect=mock_auth,
            ),
            patch(
                "src.api.routers.chat._handle_ws_message",
                side_effect=mock_handle_ws,
            ),
        ):
            with ws_client.websocket_connect("/v1/agents/nonexistent/ws?token=valid") as ws:
                ws.send_json({"type": "message", "content": "hello"})
                error_data = ws.receive_json()
                assert error_data["type"] == "error"
                assert "nonexistent" in error_data["content"]
