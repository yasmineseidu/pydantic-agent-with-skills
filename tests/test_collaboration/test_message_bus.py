"""Tests for AgentMessageBus."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.messaging.agent_message_bus import AgentMessageBus
from src.collaboration.models import AgentMessageType
from src.db.models.collaboration import AgentMessageORM


@pytest.mark.asyncio
async def test_send_message_returns_model() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        obj.message_type = AgentMessageType.INFO_REQUEST.value
        obj.from_agent_id = uuid4()
        obj.to_agent_id = uuid4()
        obj.body = "Hello"
        obj.created_at = datetime.now(timezone.utc)
        obj.metadata_json = {}

    session.refresh = AsyncMock(side_effect=_refresh)

    bus = AgentMessageBus(session)
    result = await bus.send_message(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        message_type=AgentMessageType.INFO_REQUEST,
        subject="Subject",
        body="Hello",
        metadata={},
    )

    assert result is not None
    assert result.content == "Hello"


@pytest.mark.asyncio
async def test_get_pending_messages_returns_list() -> None:
    session = AsyncMock()

    msg = MagicMock(spec=AgentMessageORM)
    msg.id = uuid4()
    msg.message_type = AgentMessageType.INFO_RESPONSE.value
    msg.from_agent_id = uuid4()
    msg.to_agent_id = uuid4()
    msg.body = "Reply"
    msg.created_at = datetime.now(timezone.utc)
    msg.metadata_json = {}

    result = MagicMock()
    result.scalars.return_value.all.return_value = [msg]
    session.execute = AsyncMock(return_value=result)

    bus = AgentMessageBus(session)
    messages = await bus.get_pending_messages(agent_id=msg.to_agent_id)

    assert len(messages) == 1
    assert messages[0].message_type == AgentMessageType.INFO_RESPONSE
