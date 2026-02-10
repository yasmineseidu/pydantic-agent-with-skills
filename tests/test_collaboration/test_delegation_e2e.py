"""E2E delegation smoke tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.delegation.delegation_manager import DelegationManager
from src.collaboration.models import AgentTaskStatus, MAX_DELEGATION_DEPTH


@pytest.mark.asyncio
async def test_delegation_full_flow() -> None:
    session = AsyncMock()
    last_added: dict[str, object] = {}

    def _add(obj):
        last_added["obj"] = obj

    async def _flush():
        obj = last_added.get("obj")
        if obj and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if obj and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock(side_effect=_flush)

    manager = DelegationManager(session)

    root = await manager.delegate_task(
        conversation_id=uuid4(),
        created_by_agent_id=uuid4(),
        assigned_to_agent_id=uuid4(),
        title="Root",
        description="Root task",
        priority=5,
    )

    assert root.status == AgentTaskStatus.PENDING


@pytest.mark.asyncio
async def test_delegation_depth_limit() -> None:
    session = AsyncMock()

    parent = MagicMock()
    parent.delegation_depth = MAX_DELEGATION_DEPTH
    session.get = AsyncMock(return_value=parent)

    manager = DelegationManager(session)
    result = await manager.delegate_task(
        conversation_id=uuid4(),
        created_by_agent_id=uuid4(),
        assigned_to_agent_id=uuid4(),
        title="Too deep",
        description="Too deep",
        priority=5,
        parent_task_id=uuid4(),
    )

    assert isinstance(result, str)
    assert "Maximum delegation depth" in result
