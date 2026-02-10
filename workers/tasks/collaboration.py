"""Celery tasks for Phase 7 collaboration execution."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

from workers.utils import get_task_session_factory, get_task_settings, run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.collaboration.execute_agent_task",
    bind=True,
    max_retries=2,
    soft_time_limit=300,
    acks_late=True,
)
def execute_agent_task(
    self,  # type: ignore[no-untyped-def]
    task_id: str,
) -> dict[str, Any]:
    """Execute a delegated agent task.

    Loads AgentTaskORM by ID, updates status to in_progress, performs a
    placeholder execution, then marks task completed and publishes the
    result to Redis if configured.

    Args:
        self: Celery task instance.
        task_id: AgentTaskORM UUID as string.

    Returns:
        Dict with task_id and status.
    """
    logger.info("execute_agent_task_started: task_id=%s", task_id)

    try:
        result = run_async(_async_execute_agent_task(task_id=task_id))
        logger.info("execute_agent_task_completed: task_id=%s, status=%s", task_id, result)
        return result
    except Exception as exc:
        logger.warning(
            "execute_agent_task_failed: task_id=%s, error=%s, retry=%d/%d",
            task_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


async def _async_execute_agent_task(task_id: str) -> dict[str, Any]:
    """Async implementation of execute_agent_task.

    Args:
        task_id: AgentTaskORM UUID as string.

    Returns:
        Dict with task_id, status, and optional result.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.cache.client import RedisManager
    from src.collaboration.models import AgentTaskStatus
    from src.db.models.collaboration import AgentTaskORM

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    async with session_factory() as session:
        stmt = select(AgentTaskORM).where(AgentTaskORM.id == UUID(task_id))
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if task is None:
            logger.warning("execute_agent_task_not_found: task_id=%s", task_id)
            return {"task_id": task_id, "status": "not_found"}

        # Update status to in_progress
        task.status = AgentTaskStatus.IN_PROGRESS.value
        await session.flush()

        # Placeholder execution: echo task title/description
        result_text = f"Executed task: {task.title}"

        # Complete task
        task.status = AgentTaskStatus.COMPLETED.value
        task.result = result_text
        task.completed_at = datetime.now(timezone.utc)

        await session.commit()

        # Publish status update to Redis if configured
        if settings.redis_url:
            redis = RedisManager(settings.redis_url, getattr(settings, "redis_key_prefix", "ska:"))
            client = await redis.get_client()
            if client:
                payload = json.dumps({"task_id": task_id, "status": task.status, "result": result_text})
                channel = f"{redis.key_prefix}task_updates:{task_id}"
                await client.publish(channel, payload)

        logger.info("execute_agent_task_success: task_id=%s", task_id)

        return {
            "task_id": task_id,
            "status": task.status,
            "result": result_text,
        }
