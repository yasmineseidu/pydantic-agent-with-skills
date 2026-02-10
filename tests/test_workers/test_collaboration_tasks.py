"""Tests for collaboration Celery tasks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from workers.tasks.collaboration import _async_execute_agent_task


@pytest.mark.asyncio
async def test_execute_agent_task_not_found(mock_session_factory, mock_settings) -> None:
    """Returns not_found when task does not exist."""
    session = mock_session_factory._mock_session
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result)

    with (
        patch(
            "workers.tasks.collaboration.get_task_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "workers.tasks.collaboration.get_task_settings",
            return_value=mock_settings,
        ),
    ):
        output = await _async_execute_agent_task(task_id=str(uuid4()))

    assert output["status"] == "not_found"


@pytest.mark.asyncio
async def test_execute_agent_task_success(mock_session_factory, mock_settings) -> None:
    """Marks task completed and commits session."""
    session = mock_session_factory._mock_session

    task = MagicMock()
    task.id = uuid4()
    task.title = "Task"
    task.status = "pending"
    task.result = None
    task.completed_at = None

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=task)
    session.execute = AsyncMock(return_value=result)

    mock_settings.redis_url = None

    with (
        patch(
            "workers.tasks.collaboration.get_task_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "workers.tasks.collaboration.get_task_settings",
            return_value=mock_settings,
        ),
    ):
        output = await _async_execute_agent_task(task_id=str(task.id))

    session.commit.assert_awaited_once()
    assert output["status"] == "completed"
    assert "Executed task" in output["result"]


@pytest.mark.asyncio
async def test_execute_agent_task_publishes_to_redis(mock_session_factory, mock_settings) -> None:
    """Publishes task update to Redis when configured."""
    session = mock_session_factory._mock_session

    task = MagicMock()
    task.id = uuid4()
    task.title = "Task"
    task.status = "pending"
    task.result = None
    task.completed_at = None

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=task)
    session.execute = AsyncMock(return_value=result)

    redis_client = AsyncMock()
    redis_manager = MagicMock()
    redis_manager.get_client = AsyncMock(return_value=redis_client)
    redis_manager.key_prefix = "ska:"

    with (
        patch(
            "workers.tasks.collaboration.get_task_session_factory",
            return_value=mock_session_factory,
        ),
        patch(
            "workers.tasks.collaboration.get_task_settings",
            return_value=mock_settings,
        ),
        patch("src.cache.client.RedisManager", return_value=redis_manager),
    ):
        await _async_execute_agent_task(task_id=str(task.id))

    redis_client.publish.assert_awaited()
