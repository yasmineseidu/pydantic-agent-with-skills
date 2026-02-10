"""Tests for DelegationManager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.delegation.delegation_manager import DelegationManager
from src.collaboration.models import AgentTaskStatus, MAX_DELEGATION_DEPTH
from src.db.models.collaboration import AgentTaskORM


@pytest.mark.asyncio
async def test_delegate_task_creates_task() -> None:
    session = AsyncMock()
    last_added = {}

    def _add(obj):
        last_added["obj"] = obj

    async def _flush():
        obj = last_added.get("obj")
        if obj is not None:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock(side_effect=_flush)

    manager = DelegationManager(session)
    result = await manager.delegate_task(
        conversation_id=uuid4(),
        created_by_agent_id=uuid4(),
        assigned_to_agent_id=uuid4(),
        title="Test",
        description="Do work",
        priority=5,
    )

    assert not isinstance(result, str)
    assert result.status == AgentTaskStatus.PENDING
    assert session.add.called


@pytest.mark.asyncio
async def test_delegate_task_rejects_when_depth_exceeded() -> None:
    session = AsyncMock()

    parent = MagicMock(spec=AgentTaskORM)
    parent.delegation_depth = MAX_DELEGATION_DEPTH
    session.get = AsyncMock(return_value=parent)

    manager = DelegationManager(session)
    result = await manager.delegate_task(
        conversation_id=uuid4(),
        created_by_agent_id=uuid4(),
        assigned_to_agent_id=uuid4(),
        title="Test",
        description="Do work",
        priority=5,
        parent_task_id=uuid4(),
    )

    assert isinstance(result, str)
    assert "Maximum delegation depth" in result


@pytest.mark.asyncio
async def test_get_pending_tasks_returns_models() -> None:
    session = AsyncMock()

    task_orm = MagicMock(spec=AgentTaskORM)
    task_orm.id = uuid4()
    task_orm.description = "Task"
    task_orm.status = AgentTaskStatus.PENDING.value
    task_orm.priority = 5
    task_orm.assigned_to_agent_id = uuid4()
    task_orm.created_by_agent_id = uuid4()
    task_orm.created_at = datetime.now(timezone.utc)
    task_orm.completed_at = None
    task_orm.result = None
    task_orm.parent_task_id = None
    task_orm.delegation_depth = 0
    task_orm.title = "Task"

    result = MagicMock()
    result.scalars.return_value.all.return_value = [task_orm]
    session.execute = AsyncMock(return_value=result)

    manager = DelegationManager(session)
    tasks = await manager.get_pending_tasks(assigned_to_agent_id=task_orm.assigned_to_agent_id)

    assert len(tasks) == 1
    assert tasks[0].description == "Task"
