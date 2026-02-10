"""Unit and integration tests for SSE streaming event format, ordering, and lifecycle."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPartDelta

import src.api.routers.chat as chat_module
from src.api.schemas.chat import ChatRequest
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.user import UserORM
from src.dependencies import AgentDependencies


def _setup_mock_db(agent_mock: Optional[MagicMock] = None) -> AsyncMock:
    """Create a mock DB session with configurable agent query result.

    Assigns UUIDs to objects added via db.add() to simulate database flush
    behavior (conversations get IDs, messages get IDs).

    Args:
        agent_mock: Optional AgentORM mock returned by the first query.

    Returns:
        AsyncMock configured as an async database session.
    """
    db = AsyncMock()

    def _mock_add(obj: object) -> None:
        """Assign IDs to ORM objects like a real database flush would."""
        if not hasattr(obj, "id") or obj.id is not None:
            return
        obj.id = uuid4()

    db.add = MagicMock(side_effect=_mock_add)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    if agent_mock is not None:
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=agent_mock)
        db.execute = AsyncMock(return_value=agent_result)

    return db


def _create_mock_agent(team_id: UUID) -> MagicMock:
    """Create a mock AgentORM for streaming tests.

    Args:
        team_id: Team UUID the agent belongs to.

    Returns:
        MagicMock configured as an active AgentORM.
    """
    agent = MagicMock(spec=AgentORM)
    agent.id = uuid4()
    agent.team_id = team_id
    agent.status = AgentStatusEnum.ACTIVE.value
    agent.name = "SSE Agent"
    agent.slug = "sse-agent"
    agent.personality = None
    agent.model_config_json = None
    agent.memory_config = None
    agent.boundaries = None
    agent.shared_skill_names = []
    agent.custom_skill_names = []
    agent.disabled_skill_names = []
    agent.created_by = None
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


def _create_streaming_mocks() -> tuple[MagicMock, MagicMock]:
    """Create mock agent.iter() context with text streaming events.

    Returns:
        Tuple of (mock_run, mock_node) for patching agent.iter().
    """
    # PartStartEvent with text content
    mock_text_part = MagicMock()
    mock_text_part.part_kind = "text"
    mock_text_part.content = "Hello "

    mock_start_event = MagicMock(spec=PartStartEvent)
    mock_start_event.part = mock_text_part

    # PartDeltaEvent with text delta
    mock_delta = MagicMock(spec=TextPartDelta)
    mock_delta.content_delta = "world!"

    mock_delta_event = MagicMock(spec=PartDeltaEvent)
    mock_delta_event.delta = mock_delta

    # Request stream that yields events
    mock_request_stream = MagicMock()
    mock_request_stream.__aenter__ = AsyncMock(return_value=mock_request_stream)
    mock_request_stream.__aexit__ = AsyncMock(return_value=None)

    async def _stream_events():
        yield mock_start_event
        yield mock_delta_event

    mock_request_stream.__aiter__ = lambda self: _stream_events()

    # Model request node
    mock_node = MagicMock()
    mock_node.stream = MagicMock(return_value=mock_request_stream)

    # Run context manager
    mock_run = MagicMock()
    mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=100, output_tokens=50))
    mock_run.__aenter__ = AsyncMock(return_value=mock_run)
    mock_run.__aexit__ = AsyncMock(return_value=None)
    mock_run.ctx = MagicMock()

    async def _run_nodes():
        yield mock_node

    mock_run.__aiter__ = lambda self: _run_nodes()

    return mock_run, mock_node


def _patched_isinstance(obj: object, cls: type) -> bool:
    """Route isinstance checks for mocked pydantic-ai event types.

    Args:
        obj: Object to check.
        cls: Type to check against.

    Returns:
        True if the mock matches the expected event type.
    """
    if cls is PartStartEvent and hasattr(obj, "part"):
        return True
    if cls is PartDeltaEvent and hasattr(obj, "delta"):
        return True
    if cls is TextPartDelta and hasattr(obj, "content_delta"):
        return True
    return type.__instancecheck__(cls, obj)


async def _consume_sse_raw(result) -> list[str]:
    """Consume SSE stream and return raw string chunks.

    Args:
        result: StreamingResponse from stream_chat().

    Returns:
        List of raw SSE string chunks.
    """
    chunks: list[str] = []
    async for chunk in result.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        chunks.append(text)
    return chunks


async def _consume_sse_events(result) -> list[dict]:
    """Consume SSE stream and parse JSON events.

    Args:
        result: StreamingResponse from stream_chat().

    Returns:
        List of parsed JSON dicts from SSE data lines.
    """
    events: list[dict] = []
    async for chunk in result.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for line in text.strip().split("\n\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                events.append(data)
    return events


class TestSSEFormat:
    """Tests for SSE event formatting and ordering."""

    @pytest.mark.asyncio
    async def test_sse_events_have_data_prefix(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Each raw SSE chunk must start with 'data: ' and end with two newlines."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        # Patches must remain active during stream consumption (lazy generator)
        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            # Consume within patch context since generator is lazy
            raw_chunks = await _consume_sse_raw(result)

        assert len(raw_chunks) > 0, "Expected at least one SSE chunk"
        for chunk in raw_chunks:
            assert chunk.startswith("data: "), f"Chunk missing 'data: ' prefix: {chunk!r}"
            assert chunk.endswith("\n\n"), f"Chunk missing trailing newlines: {chunk!r}"

    @pytest.mark.asyncio
    async def test_first_chunk_has_conversation_id(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """First content event must include conversation_id field."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        content_events = [e for e in events if e.get("type") == "content"]
        assert len(content_events) > 0, "Expected at least one content event"
        first_content = content_events[0]
        assert first_content.get("conversation_id") is not None, (
            "First content chunk must include conversation_id"
        )

    @pytest.mark.asyncio
    async def test_subsequent_chunks_no_conversation_id(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """After first content chunk, remaining content chunks must NOT have conversation_id."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        content_events = [e for e in events if e.get("type") == "content"]
        assert len(content_events) >= 2, (
            f"Expected at least 2 content events, got {len(content_events)}"
        )
        for subsequent in content_events[1:]:
            assert subsequent.get("conversation_id") is None, (
                f"Subsequent content chunk should not have conversation_id: {subsequent}"
            )

    @pytest.mark.asyncio
    async def test_usage_event_after_content(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Usage event must appear after all content events."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]

        assert "usage" in event_types, "Expected a usage event in the stream"
        assert "content" in event_types, "Expected content events in the stream"

        last_content_idx = max(i for i, t in enumerate(event_types) if t == "content")
        usage_idx = event_types.index("usage")
        assert usage_idx > last_content_idx, (
            f"Usage event (idx={usage_idx}) must come after last content (idx={last_content_idx})"
        )

    @pytest.mark.asyncio
    async def test_done_event_is_last(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Last event in the stream must have type='done'."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        assert len(events) > 0, "Expected at least one event"
        assert events[-1].get("type") == "done", (
            f"Last event must be 'done', got '{events[-1].get('type')}'"
        )

    @pytest.mark.asyncio
    async def test_error_on_agent_not_found(self, test_user: UserORM, test_team_id: UUID) -> None:
        """When agent slug doesn't exist, stream should contain an error event."""
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()

        # Agent query returns None
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=agent_result)

        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        result = await chat_module.stream_chat(
            agent_slug="nonexistent-agent",
            body=ChatRequest(message="Hello"),
            current_user=(test_user, test_team_id),
            db=db,
            settings=mock_settings,
            agent_deps=mock_deps,
        )

        assert result.media_type == "text/event-stream"

        events = await _consume_sse_events(result)
        assert len(events) > 0, "Expected at least one event for error case"
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) > 0, "Expected an error event when agent not found"
        assert "not found" in error_events[0].get("content", "").lower()


class TestSSELifecycle:
    """Tests for SSE streaming lifecycle: agent state, conversations, persistence, and auth."""

    @pytest.mark.asyncio
    async def test_error_on_inactive_agent(self, test_user: UserORM, test_team_id: UUID) -> None:
        """When agent status is not ACTIVE, stream should contain an error event."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        mock_agent_orm.status = AgentStatusEnum.DRAFT.value

        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        result = await chat_module.stream_chat(
            agent_slug="sse-agent",
            body=ChatRequest(message="Hello"),
            current_user=(test_user, test_team_id),
            db=db,
            settings=mock_settings,
            agent_deps=mock_deps,
        )

        events = await _consume_sse_events(result)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) > 0, "Expected an error event for inactive agent"
        assert "not active" in error_events[0].get("content", "").lower()

    @pytest.mark.asyncio
    async def test_new_conversation_created(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Without conversation_id, stream should complete with a done event."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Hello, new conversation"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]
        assert "done" in event_types, "Expected a done event for new conversation"
        # No error events should appear
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 0, f"Unexpected error events: {error_events}"

    @pytest.mark.asyncio
    async def test_existing_conversation_used(self, test_user: UserORM, test_team_id: UUID) -> None:
        """With conversation_id, stream should complete using existing conversation."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        conv_id = uuid4()

        # Mock conversation
        mock_conv = MagicMock()
        mock_conv.id = conv_id
        mock_conv.team_id = test_team_id
        mock_conv.message_count = 5
        mock_conv.total_input_tokens = 0
        mock_conv.total_output_tokens = 0
        mock_conv.last_message_at = None

        # First db.execute returns agent, second returns conversation
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent_orm)
        conv_result = MagicMock()
        conv_result.scalar_one_or_none = MagicMock(return_value=mock_conv)

        db = _setup_mock_db()
        db.execute = AsyncMock(side_effect=[agent_result, conv_result])

        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Continue chat", conversation_id=conv_id),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]
        assert "done" in event_types, "Expected a done event for existing conversation"
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 0, f"Unexpected error events: {error_events}"

    @pytest.mark.asyncio
    async def test_messages_persisted_after_stream(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """After streaming, db.add() should be called for user and assistant messages."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Persist test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            await _consume_sse_events(result)

        # db.add is called for: conversation (new), user_message, assistant_message,
        # conversation update — at least 3 calls
        assert db.add.call_count >= 3, (
            f"Expected at least 3 db.add() calls (conversation + user msg + assistant msg), "
            f"got {db.add.call_count}"
        )

    @pytest.mark.asyncio
    async def test_memory_extraction_triggered(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """When memory_extractor is set, asyncio.create_task should be called after stream."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = MagicMock()

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
            patch("src.api.routers.chat.asyncio.create_task") as mock_create_task,
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Memory test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            await _consume_sse_events(result)

        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_requires_team_context(self, test_user: UserORM) -> None:
        """When team_id is None, stream_chat should raise HTTPException 401."""
        db = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="No team"),
                current_user=(test_user, None),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

        assert exc_info.value.status_code == 401


class TestSSEIntegrationBasic:
    """Integration tests for SSE endpoints using httpx AsyncClient."""

    @pytest.mark.asyncio
    async def test_stream_returns_event_stream_content_type(
        self,
        auth_client: AsyncClient,
        db_session: AsyncMock,
        mock_agent_for_streaming: MagicMock,
    ) -> None:
        """Basic stream endpoint returns correct content type."""
        # Mock DB to return the agent
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent_for_streaming)
        db_session.execute = AsyncMock(return_value=agent_result)

        # Mock the agent streaming
        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_run = MagicMock()
            mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=10, output_tokens=5))
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)

            async def _empty_stream():
                return
                yield  # type: ignore[misc]  # makes this an async generator

            mock_run.__aiter__ = lambda self: _empty_stream()
            mock_skill.iter = MagicMock(return_value=mock_run)

            response = await auth_client.post(
                "/v1/agents/test-streamer/chat/stream",
                json={"message": "Hello"},
            )

        assert response.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_stream_requires_auth(
        self,
        app: MagicMock,
        db_session: AsyncMock,
    ) -> None:
        """Stream endpoint returns 401 without auth."""
        # Remove auth override to test real auth
        from src.auth.dependencies import get_current_user

        original_override = None
        if get_current_user in app.dependency_overrides:
            original_override = app.dependency_overrides.pop(get_current_user)

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/v1/agents/test/chat/stream",
                    json={"message": "Hello"},
                )

            # Without auth, expect 401 (missing header) or 422 (validation error)
            assert response.status_code in (401, 422)
        finally:
            # Restore override to avoid affecting other tests
            if original_override is not None:
                app.dependency_overrides[get_current_user] = original_override

    @pytest.mark.asyncio
    async def test_existing_basic_stream_unchanged(
        self,
        auth_client: AsyncClient,
        db_session: AsyncMock,
        mock_agent_for_streaming: MagicMock,
    ) -> None:
        """Basic /chat/stream endpoint remains backward-compatible."""
        # Mock DB to return the agent
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent_for_streaming)
        db_session.execute = AsyncMock(return_value=agent_result)

        # Mock the agent streaming with text content
        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_run = MagicMock()
            mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=10, output_tokens=5))
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)

            async def _empty_stream():
                return
                yield  # type: ignore[misc]  # makes this an async generator

            mock_run.__aiter__ = lambda self: _empty_stream()
            mock_skill.iter = MagicMock(return_value=mock_run)

            response = await auth_client.post(
                "/v1/agents/test-streamer/chat/stream",
                json={"message": "Backward compat test"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_advanced_endpoint_exists(
        self,
        auth_client: AsyncClient,
        db_session: AsyncMock,
        mock_agent_for_streaming: MagicMock,
    ) -> None:
        """Advanced stream endpoint exists and returns text/event-stream."""
        # Mock DB to return the agent
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent_for_streaming)
        db_session.execute = AsyncMock(return_value=agent_result)

        # Mock the agent streaming
        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_run = MagicMock()
            mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=10, output_tokens=5))
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)

            async def _empty_stream():
                return
                yield  # type: ignore[misc]  # makes this an async generator

            mock_run.__aiter__ = lambda self: _empty_stream()
            mock_skill.iter = MagicMock(return_value=mock_run)

            response = await auth_client.post(
                "/v1/agents/test-streamer/chat/stream/advanced",
                json={"message": "Advanced test"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")


class TestSSEIntegrationAdvanced:
    """Advanced integration tests for SSE streaming: concurrency, context, team isolation, memory."""

    @pytest.mark.asyncio
    async def test_concurrent_streams_no_interference(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Two concurrent stream_chat() calls should both return valid StreamingResponses."""
        mock_agent_orm = _create_mock_agent(test_team_id)

        def _make_db() -> AsyncMock:
            return _setup_mock_db(agent_mock=mock_agent_orm)

        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"

        async def _run_stream(message: str) -> list[dict]:
            db = _make_db()
            mock_deps = MagicMock(spec=AgentDependencies)
            mock_deps.memory_retriever = None
            mock_deps.memory_extractor = None

            mock_run, _mock_node = _create_streaming_mocks()

            with (
                patch("src.api.routers.chat.skill_agent") as mock_skill,
                patch("src.api.routers.chat.Agent") as MockAgent,
                patch("src.api.routers.chat.isinstance", _patched_isinstance),
            ):
                mock_skill.iter = MagicMock(return_value=mock_run)
                MockAgent.is_model_request_node = MagicMock(return_value=True)

                result = await chat_module.stream_chat(
                    agent_slug="sse-agent",
                    body=ChatRequest(message=message),
                    current_user=(test_user, test_team_id),
                    db=db,
                    settings=mock_settings,
                    agent_deps=mock_deps,
                )

                return await _consume_sse_events(result)

        results = await asyncio.gather(
            _run_stream("Stream A"),
            _run_stream("Stream B"),
        )

        for i, events in enumerate(results):
            event_types = [e.get("type") for e in events]
            assert "done" in event_types, f"Stream {i} missing done event"
            assert "content" in event_types, f"Stream {i} missing content event"
            error_events = [e for e in events if e.get("type") == "error"]
            assert len(error_events) == 0, f"Stream {i} had unexpected errors: {error_events}"

    @pytest.mark.asyncio
    async def test_stream_with_context_param(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Passing context dict in ChatRequest should not break the stream."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(
                    message="Hello with context",
                    context={"timezone": "America/New_York", "locale": "en-US"},
                ),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]
        assert "done" in event_types, "Expected done event with context param"
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 0, f"Unexpected errors with context: {error_events}"

    @pytest.mark.asyncio
    async def test_conversation_wrong_team_error(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Conversation belonging to a different team should yield an error event."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        conv_id = uuid4()
        other_team_id = uuid4()

        # Mock conversation with different team_id
        mock_conv = MagicMock()
        mock_conv.id = conv_id
        mock_conv.team_id = other_team_id  # Different team
        mock_conv.message_count = 3
        mock_conv.total_input_tokens = 0
        mock_conv.total_output_tokens = 0
        mock_conv.last_message_at = None

        # First db.execute returns agent, second returns the wrong-team conversation
        agent_result = MagicMock()
        agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent_orm)
        conv_result = MagicMock()
        conv_result.scalar_one_or_none = MagicMock(return_value=mock_conv)

        db = _setup_mock_db()
        db.execute = AsyncMock(side_effect=[agent_result, conv_result])

        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        result = await chat_module.stream_chat(
            agent_slug="sse-agent",
            body=ChatRequest(message="Wrong team test", conversation_id=conv_id),
            current_user=(test_user, test_team_id),
            db=db,
            settings=mock_settings,
            agent_deps=mock_deps,
        )

        events = await _consume_sse_events(result)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) > 0, "Expected error event for wrong team conversation"
        assert "not found" in error_events[0].get("content", "").lower(), (
            f"Error should mention 'not found', got: {error_events[0].get('content')}"
        )

    @pytest.mark.asyncio
    async def test_advanced_has_memory_context_event(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """stream_chat_advanced() with memory_retriever should emit a memory_context event."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None

        # Configure memory_retriever to return 2 memories
        mock_deps.memory_retriever = MagicMock()
        mock_retrieval = MagicMock()
        mock_retrieval.memories = [MagicMock(), MagicMock()]
        mock_deps.memory_retriever.retrieve = AsyncMock(return_value=mock_retrieval)

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Memory test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        memory_events = [e for e in events if e.get("type") == "memory_context"]
        assert len(memory_events) > 0, (
            f"Expected memory_context event, got types: {[e.get('type') for e in events]}"
        )
        assert memory_events[0].get("memory_count") == 2, (
            f"Expected memory_count=2, got {memory_events[0].get('memory_count')}"
        )


def _create_streaming_mocks_with_tool_call() -> tuple[MagicMock, MagicMock]:
    """Create mock agent.iter() context with text streaming and a tool-call event.

    Returns:
        Tuple of (mock_run, mock_node) for patching agent.iter().
    """
    # PartStartEvent with text content
    mock_text_part = MagicMock()
    mock_text_part.part_kind = "text"
    mock_text_part.content = "Hello "

    mock_start_event = MagicMock(spec=PartStartEvent)
    mock_start_event.part = mock_text_part

    # PartDeltaEvent with text delta
    mock_delta = MagicMock(spec=TextPartDelta)
    mock_delta.content_delta = "world!"

    mock_delta_event = MagicMock(spec=PartDeltaEvent)
    mock_delta_event.delta = mock_delta

    # PartStartEvent with tool-call
    mock_tool_part = MagicMock()
    mock_tool_part.part_kind = "tool-call"
    mock_tool_part.tool_name = "get_weather"
    mock_tool_part.args_as_dict = MagicMock(return_value={"city": "NYC"})
    mock_tool_part.tool_call_id = "call_123"

    mock_tool_event = MagicMock(spec=PartStartEvent)
    mock_tool_event.part = mock_tool_part

    # Request stream that yields events (text + tool-call)
    mock_request_stream = MagicMock()
    mock_request_stream.__aenter__ = AsyncMock(return_value=mock_request_stream)
    mock_request_stream.__aexit__ = AsyncMock(return_value=None)

    async def _stream_events():
        yield mock_start_event
        yield mock_delta_event
        yield mock_tool_event

    mock_request_stream.__aiter__ = lambda self: _stream_events()

    # Model request node
    mock_node = MagicMock()
    mock_node.stream = MagicMock(return_value=mock_request_stream)

    # Run context manager
    mock_run = MagicMock()
    mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=100, output_tokens=50))
    mock_run.__aenter__ = AsyncMock(return_value=mock_run)
    mock_run.__aexit__ = AsyncMock(return_value=None)
    mock_run.ctx = MagicMock()

    async def _run_nodes():
        yield mock_node

    mock_run.__aiter__ = lambda self: _run_nodes()

    return mock_run, mock_node


class TestAdvancedSSE:
    """Tests for advanced SSE endpoint event ordering and content."""

    @pytest.mark.asyncio
    async def test_memory_context_is_first_event(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """stream_chat_advanced() with memory_retriever should emit memory_context first."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None

        # Configure memory_retriever to return 2 memories
        mock_deps.memory_retriever = MagicMock()
        mock_retrieval = MagicMock()
        mock_retrieval.memories = [MagicMock(), MagicMock()]
        mock_deps.memory_retriever.retrieve = AsyncMock(return_value=mock_retrieval)

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Memory test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        assert len(events) > 0, "Expected at least one event"
        assert events[0].get("type") == "memory_context", (
            f"First event must be memory_context, got '{events[0].get('type')}'"
        )
        assert events[0].get("memory_count") == 2, (
            f"Expected memory_count=2, got {events[0].get('memory_count')}"
        )

    @pytest.mark.asyncio
    async def test_typing_event_before_text(self, test_user: UserORM, test_team_id: UUID) -> None:
        """stream_chat_advanced() should emit typing before any text_delta."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None
        mock_deps.memory_retriever = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Typing test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]

        assert "typing" in event_types, "Expected a typing event in the stream"
        assert "content" in event_types, "Expected content events in the stream"

        typing_idx = event_types.index("typing")
        first_content_idx = event_types.index("content")
        assert typing_idx < first_content_idx, (
            f"typing (idx={typing_idx}) must appear before first content (idx={first_content_idx})"
        )

    @pytest.mark.asyncio
    async def test_tool_call_event_with_fields(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Tool call events must include tool_name, tool_args, tool_call_id fields."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None
        mock_deps.memory_retriever = None

        mock_run, _mock_node = _create_streaming_mocks_with_tool_call()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Tool call test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) > 0, (
            f"Expected tool_call event, got types: {[e.get('type') for e in events]}"
        )
        tool_event = tool_events[0]
        assert tool_event.get("tool_name") == "get_weather", (
            f"Expected tool_name='get_weather', got {tool_event.get('tool_name')!r}"
        )
        assert tool_event.get("tool_args") == {"city": "NYC"}, (
            f"Expected tool_args={{'city': 'NYC'}}, got {tool_event.get('tool_args')!r}"
        )
        assert tool_event.get("tool_call_id") == "call_123", (
            f"Expected tool_call_id='call_123', got {tool_event.get('tool_call_id')!r}"
        )

    @pytest.mark.asyncio
    async def test_usage_event_before_done(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Usage event must appear immediately before done event."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None
        mock_deps.memory_retriever = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Usage ordering test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]

        assert "usage" in event_types, "Expected a usage event"
        assert "done" in event_types, "Expected a done event"

        usage_idx = event_types.index("usage")
        done_idx = event_types.index("done")
        assert usage_idx == done_idx - 1, (
            f"Usage (idx={usage_idx}) must be immediately before done (idx={done_idx}), "
            f"full order: {event_types}"
        )

    @pytest.mark.asyncio
    async def test_full_event_ordering(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Full advanced stream order: memory_context -> typing -> content* -> usage -> done."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_extractor = None

        # Configure memory_retriever to return 1 memory
        mock_deps.memory_retriever = MagicMock()
        mock_retrieval = MagicMock()
        mock_retrieval.memories = [MagicMock()]
        mock_deps.memory_retriever.retrieve = AsyncMock(return_value=mock_retrieval)

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat_advanced(
                agent_slug="sse-agent",
                body=ChatRequest(message="Full ordering test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]

        # Verify expected event types are present
        assert "memory_context" in event_types, f"Missing memory_context in {event_types}"
        assert "typing" in event_types, f"Missing typing in {event_types}"
        assert "content" in event_types, f"Missing content in {event_types}"
        assert "usage" in event_types, f"Missing usage in {event_types}"
        assert "done" in event_types, f"Missing done in {event_types}"

        # Verify ordering: memory_context < typing < content < usage < done
        mem_idx = event_types.index("memory_context")
        typing_idx = event_types.index("typing")
        first_content_idx = event_types.index("content")
        last_content_idx = max(i for i, t in enumerate(event_types) if t == "content")
        usage_idx = event_types.index("usage")
        done_idx = event_types.index("done")

        assert mem_idx < typing_idx, (
            f"memory_context (idx={mem_idx}) must precede typing (idx={typing_idx})"
        )
        assert typing_idx < first_content_idx, (
            f"typing (idx={typing_idx}) must precede first content (idx={first_content_idx})"
        )
        assert last_content_idx < usage_idx, (
            f"last content (idx={last_content_idx}) must precede usage (idx={usage_idx})"
        )
        assert usage_idx < done_idx, f"usage (idx={usage_idx}) must precede done (idx={done_idx})"


class TestSSEEdgeCases:
    """Tests for SSE edge cases: empty responses, long text, mid-stream errors, format compliance."""

    @pytest.mark.asyncio
    async def test_empty_response_still_sends_done(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """When agent produces no text events, done event must still be emitted."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        # Create a run that yields zero model request nodes (no text events)
        mock_run = MagicMock()
        mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=5, output_tokens=0))
        mock_run.__aenter__ = AsyncMock(return_value=mock_run)
        mock_run.__aexit__ = AsyncMock(return_value=None)

        async def _empty_nodes():
            return
            yield  # type: ignore[misc]

        mock_run.__aiter__ = lambda self: _empty_nodes()

        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_skill.iter = MagicMock(return_value=mock_run)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Empty response test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        event_types = [e.get("type") for e in events]
        assert "done" in event_types, f"Expected done event even with no text, got: {event_types}"

    @pytest.mark.asyncio
    async def test_long_response_streams_completely(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """A 1000+ character text delta must arrive fully in the stream."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        long_text = "A" * 1500

        # Create a PartDeltaEvent with a large text delta
        mock_delta = MagicMock(spec=TextPartDelta)
        mock_delta.content_delta = long_text

        mock_delta_event = MagicMock(spec=PartDeltaEvent)
        mock_delta_event.delta = mock_delta

        # Request stream yielding the single long delta
        mock_request_stream = MagicMock()
        mock_request_stream.__aenter__ = AsyncMock(return_value=mock_request_stream)
        mock_request_stream.__aexit__ = AsyncMock(return_value=None)

        async def _long_stream():
            yield mock_delta_event

        mock_request_stream.__aiter__ = lambda self: _long_stream()

        # Model request node
        mock_node = MagicMock()
        mock_node.stream = MagicMock(return_value=mock_request_stream)

        # Run context manager
        mock_run = MagicMock()
        mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=50, output_tokens=200))
        mock_run.__aenter__ = AsyncMock(return_value=mock_run)
        mock_run.__aexit__ = AsyncMock(return_value=None)
        mock_run.ctx = MagicMock()

        async def _run_nodes():
            yield mock_node

        mock_run.__aiter__ = lambda self: _run_nodes()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Long response test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        content_events = [e for e in events if e.get("type") == "content"]
        total_text = "".join(e.get("content", "") for e in content_events)
        assert len(total_text) >= 1000, (
            f"Expected at least 1000 chars streamed, got {len(total_text)}"
        )
        assert total_text == long_text, "Full long text must arrive intact"

    @pytest.mark.asyncio
    async def test_agent_error_mid_stream(self, test_user: UserORM, test_team_id: UUID) -> None:
        """When agent.iter() raises mid-stream, an error event must be emitted."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        # Run context manager that raises during iteration
        mock_run = MagicMock()
        mock_run.__aenter__ = AsyncMock(return_value=mock_run)
        mock_run.__aexit__ = AsyncMock(return_value=None)

        async def _error_nodes():
            raise RuntimeError("Model inference failed")
            yield  # type: ignore[misc]

        mock_run.__aiter__ = lambda self: _error_nodes()

        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_skill.iter = MagicMock(return_value=mock_run)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Error mid-stream test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            events = await _consume_sse_events(result)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) > 0, (
            f"Expected error event after mid-stream exception, got types: "
            f"{[e.get('type') for e in events]}"
        )
        assert "Model inference failed" in error_events[0].get("content", ""), (
            f"Error content should mention the exception: {error_events[0].get('content')}"
        )

    @pytest.mark.asyncio
    async def test_sse_format_compliance(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Every SSE event must match 'data: {valid_json}\\n\\n' format."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        mock_run, _mock_node = _create_streaming_mocks()

        with (
            patch("src.api.routers.chat.skill_agent") as mock_skill,
            patch("src.api.routers.chat.Agent") as MockAgent,
            patch("src.api.routers.chat.isinstance", _patched_isinstance),
        ):
            mock_skill.iter = MagicMock(return_value=mock_run)
            MockAgent.is_model_request_node = MagicMock(return_value=True)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Format compliance test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            raw_chunks = await _consume_sse_raw(result)

        assert len(raw_chunks) > 0, "Expected at least one SSE chunk"
        for i, chunk in enumerate(raw_chunks):
            # Every chunk must start with "data: " and end with "\n\n"
            assert chunk.startswith("data: "), f"Chunk {i} missing 'data: ' prefix: {chunk!r}"
            assert chunk.endswith("\n\n"), f"Chunk {i} missing trailing '\\n\\n': {chunk!r}"
            # Extract JSON payload and verify it parses
            json_payload = chunk[6:].rstrip("\n")
            try:
                parsed = json.loads(json_payload)
            except json.JSONDecodeError as e:
                pytest.fail(f"Chunk {i} has invalid JSON: {json_payload!r} -- {e}")
            assert isinstance(parsed, dict), f"Chunk {i} JSON is not a dict: {type(parsed)}"
            assert "type" in parsed, f"Chunk {i} JSON missing 'type' field: {parsed}"


class TestPhase5Regression:
    """Regression tests ensuring Phase 5 streaming changes don't break existing functionality."""

    @pytest.mark.asyncio
    async def test_nonstreaming_chat_still_works(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Non-streaming chat() endpoint must still return a ChatResponse."""
        from src.api.schemas.chat import ChatResponse

        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        # Mock agent.run() for non-streaming
        mock_result = MagicMock()
        mock_result.output = "Hello from agent"
        mock_result.usage = MagicMock(return_value=MagicMock(input_tokens=10, output_tokens=5))

        with patch("src.api.routers.chat.skill_agent") as mock_agent:
            mock_agent.run = AsyncMock(return_value=mock_result)

            result = await chat_module.chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Hi"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

        assert isinstance(result, ChatResponse)
        assert result.response == "Hello from agent"
        assert result.conversation_id is not None
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5

    def test_cli_still_launches(self) -> None:
        """CLI module must be importable and expose a callable main()."""
        import importlib

        mod = importlib.import_module("src.cli")
        assert hasattr(mod, "main"), "CLI module must expose a main() function"
        assert callable(mod.main), "main must be callable"

    @pytest.mark.asyncio
    async def test_conversation_persisted_after_stream_error(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Conversation must be created in DB even if agent raises mid-stream."""
        mock_agent_orm = _create_mock_agent(test_team_id)
        db = _setup_mock_db(agent_mock=mock_agent_orm)
        mock_settings = MagicMock()
        mock_settings.llm_model = "test-model"
        mock_deps = MagicMock(spec=AgentDependencies)
        mock_deps.memory_retriever = None
        mock_deps.memory_extractor = None

        # Run context manager that raises during iteration
        mock_run = MagicMock()
        mock_run.__aenter__ = AsyncMock(return_value=mock_run)
        mock_run.__aexit__ = AsyncMock(return_value=None)

        async def _error_nodes():
            raise RuntimeError("Backend crashed")
            yield  # type: ignore[misc]

        mock_run.__aiter__ = lambda self: _error_nodes()

        with patch("src.api.routers.chat.skill_agent") as mock_skill:
            mock_skill.iter = MagicMock(return_value=mock_run)

            result = await chat_module.stream_chat(
                agent_slug="sse-agent",
                body=ChatRequest(message="Error persistence test"),
                current_user=(test_user, test_team_id),
                db=db,
                settings=mock_settings,
                agent_deps=mock_deps,
            )

            await _consume_sse_events(result)

        # Conversation should have been created before the error occurred
        # db.add is called for the conversation ORM, then db.flush for the ID
        assert db.add.call_count >= 1, (
            f"Expected at least 1 db.add() call for conversation creation, got {db.add.call_count}"
        )
