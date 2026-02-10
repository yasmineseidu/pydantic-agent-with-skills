"""Unit tests for conversation management endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from httpx import AsyncClient

from src.db.models.conversation import ConversationORM, MessageORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

_TEST_TEAM_ID = UUID("87654321-4321-8765-4321-876543218765")
_TEST_USER_ID = UUID("12345678-1234-5678-1234-567812345678")
_TEST_AGENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_conversation_mock(
    conversation_id: UUID,
    *,
    team_id: UUID = _TEST_TEAM_ID,
    agent_id: UUID = _TEST_AGENT_ID,
    user_id: UUID = _TEST_USER_ID,
    title: str = "Test conversation",
    status: str = "active",
    message_count: int = 5,
    total_input_tokens: int = 100,
    total_output_tokens: int = 200,
    summary: str | None = None,
    created_at: datetime = _NOW,
    updated_at: datetime = _NOW,
    last_message_at: datetime = _NOW,
) -> MagicMock:
    """Build a MagicMock that quacks like ConversationORM."""
    conv = MagicMock(spec=ConversationORM)
    conv.id = conversation_id
    conv.team_id = team_id
    conv.agent_id = agent_id
    conv.user_id = user_id
    conv.title = title
    conv.status = status
    conv.message_count = message_count
    conv.total_input_tokens = total_input_tokens
    conv.total_output_tokens = total_output_tokens
    conv.summary = summary
    conv.created_at = created_at
    conv.updated_at = updated_at
    conv.last_message_at = last_message_at
    return conv


def _make_message_mock(
    message_id: UUID,
    conversation_id: UUID,
    *,
    agent_id: UUID | None = _TEST_AGENT_ID,
    role: str = "assistant",
    content: str = "Hello world",
    token_count: int | None = 10,
    model: str | None = "test-model",
    created_at: datetime = _NOW,
) -> MagicMock:
    """Build a MagicMock that quacks like MessageORM."""
    msg = MagicMock(spec=MessageORM)
    msg.id = message_id
    msg.conversation_id = conversation_id
    msg.agent_id = agent_id
    msg.role = role
    msg.content = content
    msg.token_count = token_count
    msg.model = model
    msg.created_at = created_at
    return msg


def _list_execute_side_effect(total: int, conversations: list) -> list:
    """Build the two MagicMock results for list_conversations (count + query).

    Args:
        total: Integer value returned by scalar_one (count query).
        conversations: List of conversation mocks returned by scalars().all().

    Returns:
        List of two MagicMock objects suitable for AsyncMock side_effect.
    """
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total)

    query_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=conversations)
    query_result.scalars = MagicMock(return_value=scalars_mock)

    return [count_result, query_result]


def _scalar_one_or_none_result(value):
    """Build a MagicMock result whose scalar_one_or_none() returns *value*.

    Args:
        value: The value (or None) to be returned.

    Returns:
        MagicMock with scalar_one_or_none configured.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _messages_execute_side_effect(conversation_mock, total_messages: int, messages: list) -> list:
    """Build three MagicMock results for get_conversation_messages.

    The endpoint does:
      1. scalar_one_or_none -> conversation or None
      2. scalar_one         -> message count (int)
      3. scalars().all()    -> list of messages

    Args:
        conversation_mock: A conversation MagicMock or None.
        total_messages: Integer message count.
        messages: List of message mocks.

    Returns:
        List of three MagicMock objects suitable for AsyncMock side_effect.
    """
    conv_result = _scalar_one_or_none_result(conversation_mock)

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total_messages)

    msgs_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=messages)
    msgs_result.scalars = MagicMock(return_value=scalars_mock)

    return [conv_result, count_result, msgs_result]


# ---------------------------------------------------------------------------
# TestListConversations
# ---------------------------------------------------------------------------


class TestListConversations:
    """Tests for GET /v1/conversations endpoint."""

    @pytest.mark.asyncio
    async def test_list_conversations_success(self, auth_client: AsyncClient, db_session) -> None:
        """list_conversations returns paginated conversations for team."""
        conv = _make_conversation_mock(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(1, [conv]))

        response = await auth_client.get("/v1/conversations?limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert data["limit"] == 20
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, auth_client: AsyncClient, db_session) -> None:
        """list_conversations returns empty items when no conversations exist."""
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(0, []))

        response = await auth_client.get("/v1/conversations?limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_conversations_with_agent_filter(
        self, auth_client: AsyncClient, db_session, test_user_id: UUID
    ) -> None:
        """list_conversations filters by agent_id when provided."""
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(0, []))
        agent_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        response = await auth_client.get(f"/v1/conversations?agent_id={agent_id}&limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_conversations_with_status_filter(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """list_conversations filters by status when provided."""
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(0, []))

        response = await auth_client.get("/v1/conversations?status=active&limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_conversations_with_both_filters(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """list_conversations applies both agent_id and status filters."""
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(0, []))
        agent_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        response = await auth_client.get(
            f"/v1/conversations?agent_id={agent_id}&status=active&limit=20&offset=0"
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_list_conversations_pagination(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """list_conversations respects pagination parameters."""
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(20, []))

        response = await auth_client.get("/v1/conversations?limit=10&offset=5")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    @pytest.mark.asyncio
    async def test_list_conversations_pagination_has_more(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """list_conversations sets has_more correctly."""
        # total=20, offset=0, limit=10 => has_more = (0+10) < 20 = True
        conv = _make_conversation_mock(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(20, [conv]))

        response = await auth_client.get("/v1/conversations?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["has_more"], bool)
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_list_conversations_no_auth(self, app, client: AsyncClient) -> None:
        """list_conversations requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        response = await client.get("/v1/conversations")

        # Should fail auth - either 401 or 422 (missing/invalid Authorization header)
        assert response.status_code in [401, 422]


# ---------------------------------------------------------------------------
# TestGetConversation
# ---------------------------------------------------------------------------


class TestGetConversation:
    """Tests for GET /v1/conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_conversation_success(self, auth_client: AsyncClient, db_session) -> None:
        """get_conversation returns conversation details."""
        conversation_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        conv = _make_conversation_mock(conversation_id)
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(conv))

        response = await auth_client.get(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conversation_id)
        assert "team_id" in data
        assert "agent_id" in data
        assert "user_id" in data
        assert "status" in data
        assert "message_count" in data

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, auth_client: AsyncClient, db_session) -> None:
        """get_conversation returns 404 for non-existent conversation."""
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
        conversation_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

        response = await auth_client.get(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_conversation_invalid_uuid(self, auth_client: AsyncClient) -> None:
        """get_conversation returns 422 for invalid UUID format."""
        response = await auth_client.get("/v1/conversations/invalid-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_conversation_no_auth(self, app, client: AsyncClient) -> None:
        """get_conversation requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        conversation_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        response = await client.get(f"/v1/conversations/{conversation_id}")

        assert response.status_code in [401, 422]


# ---------------------------------------------------------------------------
# TestGetConversationMessages
# ---------------------------------------------------------------------------


class TestGetConversationMessages:
    """Tests for GET /v1/conversations/{conversation_id}/messages endpoint."""

    @pytest.mark.asyncio
    async def test_get_messages_success(self, auth_client: AsyncClient, db_session) -> None:
        """get_conversation_messages returns paginated messages."""
        conversation_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        conv = _make_conversation_mock(conversation_id)
        msg1 = _make_message_mock(
            UUID("11111111-1111-1111-1111-111111111111"),
            conversation_id,
            role="user",
            content="Hi",
            created_at=_NOW,
        )
        msg2 = _make_message_mock(
            UUID("22222222-2222-2222-2222-222222222222"),
            conversation_id,
            role="assistant",
            content="Hello!",
            created_at=_NOW + timedelta(seconds=1),
        )
        db_session.execute = AsyncMock(
            side_effect=_messages_execute_side_effect(conv, 2, [msg1, msg2])
        )

        response = await auth_client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=50&offset=0"
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert data["limit"] == 50
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, auth_client: AsyncClient, db_session) -> None:
        """get_conversation_messages respects pagination parameters."""
        conversation_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        conv = _make_conversation_mock(conversation_id)
        db_session.execute = AsyncMock(side_effect=_messages_execute_side_effect(conv, 0, []))

        response = await auth_client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=25&offset=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 25
        assert data["offset"] == 10

    @pytest.mark.asyncio
    async def test_get_messages_chronological_order(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """get_conversation_messages returns messages in chronological order (ASC)."""
        conversation_id = UUID("11111111-1111-1111-1111-111111111111")
        conv = _make_conversation_mock(conversation_id)
        t1 = _NOW
        t2 = _NOW + timedelta(seconds=30)
        t3 = _NOW + timedelta(seconds=60)
        msg1 = _make_message_mock(
            UUID("aa111111-1111-1111-1111-111111111111"),
            conversation_id,
            role="user",
            content="First",
            created_at=t1,
        )
        msg2 = _make_message_mock(
            UUID("bb111111-1111-1111-1111-111111111111"),
            conversation_id,
            role="assistant",
            content="Second",
            created_at=t2,
        )
        msg3 = _make_message_mock(
            UUID("cc111111-1111-1111-1111-111111111111"),
            conversation_id,
            role="user",
            content="Third",
            created_at=t3,
        )
        db_session.execute = AsyncMock(
            side_effect=_messages_execute_side_effect(conv, 3, [msg1, msg2, msg3])
        )

        response = await auth_client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=50&offset=0"
        )

        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 3
        for i in range(len(items) - 1):
            created_at_1 = datetime.fromisoformat(items[i]["created_at"])
            created_at_2 = datetime.fromisoformat(items[i + 1]["created_at"])
            assert created_at_1 <= created_at_2, "Messages should be in ASC order"

    @pytest.mark.asyncio
    async def test_get_messages_conversation_not_found(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """get_conversation_messages returns 404 if conversation not found."""
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
        conversation_id = UUID("22222222-2222-2222-2222-222222222222")

        response = await auth_client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=50&offset=0"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, auth_client: AsyncClient, db_session) -> None:
        """get_conversation_messages returns empty items when conversation has no messages."""
        conversation_id = UUID("33333333-3333-3333-3333-333333333333")
        conv = _make_conversation_mock(conversation_id)
        db_session.execute = AsyncMock(side_effect=_messages_execute_side_effect(conv, 0, []))

        response = await auth_client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=50&offset=0"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_get_messages_no_auth(self, app, client: AsyncClient) -> None:
        """get_conversation_messages requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        conversation_id = UUID("44444444-4444-4444-4444-444444444444")
        response = await client.get(
            f"/v1/conversations/{conversation_id}/messages?limit=50&offset=0"
        )

        assert response.status_code in [401, 422]


# ---------------------------------------------------------------------------
# TestCloseConversation
# ---------------------------------------------------------------------------


class TestCloseConversation:
    """Tests for DELETE /v1/conversations/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_close_conversation_success(self, auth_client: AsyncClient, db_session) -> None:
        """close_conversation closes a conversation."""
        conversation_id = UUID("55555555-5555-5555-5555-555555555555")
        conv = _make_conversation_mock(conversation_id)
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(conv))

        response = await auth_client.delete(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "conversation_id" in data
        assert "successfully" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_close_conversation_not_found(self, auth_client: AsyncClient, db_session) -> None:
        """close_conversation returns 404 for non-existent conversation."""
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
        conversation_id = UUID("66666666-6666-6666-6666-666666666666")

        response = await auth_client.delete(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_close_conversation_invalid_uuid(self, auth_client: AsyncClient) -> None:
        """close_conversation returns 422 for invalid UUID format."""
        response = await auth_client.delete("/v1/conversations/invalid-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_close_conversation_no_auth(self, app, client: AsyncClient) -> None:
        """close_conversation requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        conversation_id = UUID("77777777-7777-7777-7777-777777777777")
        response = await client.delete(f"/v1/conversations/{conversation_id}")

        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_close_conversation_response_structure(
        self, auth_client: AsyncClient, db_session
    ) -> None:
        """close_conversation response has correct structure."""
        conversation_id = UUID("88888888-8888-8888-8888-888888888888")
        conv = _make_conversation_mock(conversation_id)
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(conv))

        response = await auth_client.delete(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "message" in data
        assert "conversation_id" in data
        # Verify conversation_id is a valid UUID string
        UUID(data["conversation_id"])


# ---------------------------------------------------------------------------
# TestMultiTenantIsolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    """Tests for multi-tenant scoping in conversation endpoints."""

    @pytest.mark.asyncio
    async def test_list_conversations_team_scoped(
        self, auth_client: AsyncClient, db_session, test_team_id: UUID
    ) -> None:
        """list_conversations only returns conversations for current team."""
        conv = _make_conversation_mock(
            UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            team_id=test_team_id,
        )
        db_session.execute = AsyncMock(side_effect=_list_execute_side_effect(1, [conv]))

        response = await auth_client.get("/v1/conversations?limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["team_id"] == str(test_team_id)

    @pytest.mark.asyncio
    async def test_get_conversation_team_scoped(
        self, auth_client: AsyncClient, db_session, test_team_id: UUID
    ) -> None:
        """get_conversation returns 404 if conversation belongs to different team."""
        # Simulate no result (different team => not found)
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
        conversation_id = UUID("99999999-9999-9999-9999-999999999999")

        response = await auth_client.get(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_close_conversation_team_scoped(
        self, auth_client: AsyncClient, db_session, test_team_id: UUID
    ) -> None:
        """close_conversation returns 404 if conversation belongs to different team."""
        db_session.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
        conversation_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        response = await auth_client.delete(f"/v1/conversations/{conversation_id}")

        assert response.status_code == 404
