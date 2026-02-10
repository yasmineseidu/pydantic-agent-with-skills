"""Tests for TeamMemoryBus."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.messaging.team_memory_bus import TeamMemoryBus


@pytest.mark.asyncio
async def test_publish_to_team_returns_payload() -> None:
    session = AsyncMock()
    memory_repo = AsyncMock()
    bus = TeamMemoryBus(session, memory_repo)

    result = await bus.publish_to_team(
        session_id=uuid4(),
        team_id=uuid4(),
        memory_content="Important finding",
        subject="Summary",
        importance=7,
    )

    assert len(result) == 1
    assert result[0]["content"] == "Important finding"


@pytest.mark.asyncio
async def test_store_team_knowledge_persists() -> None:
    session = AsyncMock()
    memory_repo = AsyncMock()

    memory_orm = MagicMock()
    memory_orm.id = uuid4()
    memory_orm.team_id = uuid4()
    memory_orm.agent_id = uuid4()
    memory_orm.content = "Shared"
    memory_orm.subject = "Subject"
    memory_orm.importance = 5
    memory_orm.created_at = datetime.now(timezone.utc)

    memory_repo.create = AsyncMock(return_value=memory_orm)

    bus = TeamMemoryBus(session, memory_repo)
    result = await bus.store_team_knowledge(
        team_id=memory_orm.team_id,
        agent_id=memory_orm.agent_id,
        content=memory_orm.content,
        subject=memory_orm.subject,
        importance=memory_orm.importance,
    )

    assert result
    assert result[0]["id"] == memory_orm.id
