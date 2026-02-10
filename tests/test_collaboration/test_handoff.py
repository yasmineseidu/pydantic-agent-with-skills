"""Tests for agent handoff manager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.coordination.handoff_manager import HandoffManager
from src.collaboration.models import HandoffResult, MAX_DELEGATION_DEPTH


@pytest.mark.asyncio
async def test_initiate_handoff_success() -> None:
    """Handoff should succeed when delegation depth is within limits."""
    session = AsyncMock()
    count_result = MagicMock()
    count_result.scalar = MagicMock(return_value=0)
    session.execute = AsyncMock(return_value=count_result)
    session.add = MagicMock()

    manager = HandoffManager(session)
    result = await manager.initiate_handoff(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        reason="Need specialist",
        context_transferred={"summary": "context"},
    )

    assert isinstance(result, HandoffResult)
    assert result.success is True
    assert session.add.call_count >= 1


@pytest.mark.asyncio
async def test_initiate_handoff_rejects_on_depth_limit() -> None:
    """Handoff should fail when delegation depth is exceeded."""
    session = AsyncMock()
    count_result = MagicMock()
    count_result.scalar = MagicMock(return_value=MAX_DELEGATION_DEPTH)
    session.execute = AsyncMock(return_value=count_result)

    manager = HandoffManager(session)
    result = await manager.initiate_handoff(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        reason="Need specialist",
        context_transferred={},
    )

    assert result.success is False
    assert "Maximum delegation depth" in result.reason


@pytest.mark.asyncio
async def test_get_handoff_history_returns_records() -> None:
    """get_handoff_history returns ordered records from the session."""
    session = AsyncMock()
    record = MagicMock()
    record.handoff_at = datetime.now(timezone.utc)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [record]
    session.execute = AsyncMock(return_value=result)

    manager = HandoffManager(session)
    records = await manager.get_handoff_history(conversation_id=uuid4(), limit=5)

    assert records == [record]
