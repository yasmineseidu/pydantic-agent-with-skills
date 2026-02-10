"""Celery tasks for scheduled agent execution."""

import logging
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

from workers.utils import get_task_session_factory, get_task_settings, run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.agent_tasks.scheduled_agent_run",
    bind=True,
    max_retries=2,
    soft_time_limit=300,
    acks_late=True,
)
def scheduled_agent_run(
    self,  # type: ignore[no-untyped-def]
    job_id: str,
) -> dict[str, Any]:
    """Execute a scheduled agent job.

    Loads the job from the database, runs the agent with the configured
    message, and persists the conversation.

    Args:
        self: Celery task instance (for retries).
        job_id: ScheduledJobORM UUID as string.

    Returns:
        Dict with execution result: job_id, conversation_id, status.
    """
    logger.info("scheduled_agent_run_started: job_id=%s", job_id)

    try:
        result = run_async(_async_scheduled_agent_run(job_id=job_id))
        logger.info(
            "scheduled_agent_run_completed: job_id=%s, result=%s",
            job_id,
            result,
        )
        return result
    except Exception as exc:
        logger.warning(
            "scheduled_agent_run_failed: job_id=%s, error=%s, retry=%d/%d",
            job_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        # Track failure before retry
        try:
            run_async(_track_job_failure(job_id=job_id, error=str(exc)))
        except Exception:
            logger.exception("scheduled_agent_run_track_failure_error: job_id=%s", job_id)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


async def _async_scheduled_agent_run(job_id: str) -> dict[str, Any]:
    """Async implementation of scheduled agent run.

    Loads the ScheduledJobORM, verifies it is active, creates a conversation
    with user and assistant messages, and calls the LLM via httpx.

    Args:
        job_id: ScheduledJobORM UUID as string.

    Returns:
        Execution result dict with job_id, conversation_id, status.
    """
    from uuid import UUID

    import httpx
    from sqlalchemy import select

    from src.db.models.conversation import (
        ConversationStatusEnum,
        MessageORM,
        MessageRoleEnum,
    )
    from src.db.models.conversation import ConversationORM
    from src.db.models.scheduled_job import ScheduledJobORM

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    async with session_factory() as session:
        # Load job
        stmt = select(ScheduledJobORM).where(ScheduledJobORM.id == UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return {"job_id": job_id, "status": "not_found"}

        if not job.is_active:
            return {"job_id": job_id, "status": "inactive"}

        # Create conversation
        conversation = ConversationORM(
            team_id=job.team_id,
            agent_id=job.agent_id,
            user_id=job.user_id,
            title=f"Scheduled: {job.name}",
            status=ConversationStatusEnum.ACTIVE,
            message_count=0,
        )
        session.add(conversation)
        await session.flush()

        # Add user message
        user_message = MessageORM(
            conversation_id=conversation.id,
            role=MessageRoleEnum.USER,
            content=job.message,
            token_count=0,
        )
        session.add(user_message)

        # Call LLM via httpx
        base_url = settings.llm_base_url or "https://openrouter.ai/api/v1"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": job.message}],
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            llm_result = response.json()

        assistant_content = llm_result["choices"][0]["message"]["content"]

        # Add assistant message
        assistant_message = MessageORM(
            conversation_id=conversation.id,
            role=MessageRoleEnum.ASSISTANT,
            content=assistant_content,
            token_count=llm_result.get("usage", {}).get("completion_tokens", 0),
        )
        session.add(assistant_message)

        # Update conversation counters
        conversation.message_count = 2

        # Track success on job
        job.last_run_at = datetime.now(timezone.utc)
        job.run_count += 1
        job.consecutive_failures = 0

        await session.commit()

        result_dict = {
            "job_id": job_id,
            "conversation_id": str(conversation.id),
            "status": "success",
            "response_length": len(assistant_content),
        }

        logger.info(
            "scheduled_agent_run_success: job_id=%s, conversation_id=%s",
            job_id,
            str(conversation.id),
        )

        # Deliver result via webhook if configured
        await _deliver_result(
            delivery_config=dict(job.delivery_config),
            result=result_dict,
            job_name=job.name,
        )

        return result_dict


async def _deliver_result(
    delivery_config: dict[str, Any],
    result: dict[str, Any],
    job_name: str,
) -> None:
    """Deliver job result via webhook if configured.

    Args:
        delivery_config: Config dict with optional webhook_url.
        result: Job execution result to deliver.
        job_name: Job name for logging.
    """
    webhook_url = delivery_config.get("webhook_url")
    if not webhook_url:
        return

    # Validate URL scheme
    if not isinstance(webhook_url, str) or not webhook_url.startswith(("https://", "http://")):
        logger.warning(
            "deliver_result_invalid_url: job_name=%s, webhook=%s",
            job_name,
            str(webhook_url)[:100],
        )
        return

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json={
                    "job_name": job_name,
                    "result": result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            response.raise_for_status()
            logger.info(
                "deliver_result_success: job_name=%s, webhook=%s",
                job_name,
                webhook_url,
            )
    except Exception as e:
        logger.warning(
            "deliver_result_failed: job_name=%s, webhook=%s, error=%s",
            job_name,
            webhook_url,
            str(e),
        )


async def _track_job_failure(job_id: str, error: str) -> None:
    """Track job failure in database.

    Increments consecutive_failures and auto-disables after 5 failures.

    Args:
        job_id: Job UUID as string.
        error: Error message (truncated to 500 chars).
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.db.models.scheduled_job import ScheduledJobORM

    session_factory = get_task_session_factory()

    async with session_factory() as session:
        stmt = select(ScheduledJobORM).where(ScheduledJobORM.id == UUID(job_id))
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return

        job.consecutive_failures += 1
        job.last_error = error[:500]

        # Auto-disable after 5 consecutive failures
        if job.consecutive_failures >= 5:
            job.is_active = False
            logger.warning(
                "scheduled_agent_run_auto_disabled: job_id=%s, failures=%d",
                job_id,
                job.consecutive_failures,
            )

        await session.commit()
