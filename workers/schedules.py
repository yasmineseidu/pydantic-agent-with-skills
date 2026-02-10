"""Celery Beat schedule configuration for periodic tasks."""

import logging
from typing import Any

from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)


BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "expire-tokens": {
        "task": "workers.tasks.cleanup_tasks.expire_tokens",
        "schedule": crontab(minute=0),  # Every hour
        "options": {"queue": "default"},
    },
    "close-stale-sessions": {
        "task": "workers.tasks.cleanup_tasks.close_stale_sessions",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {"queue": "default"},
    },
    "archive-old-conversations": {
        "task": "workers.tasks.cleanup_tasks.archive_old_conversations",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        "options": {"queue": "default"},
    },
    "archive-expired-memories": {
        "task": "workers.tasks.cleanup_tasks.archive_expired_memories",
        "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM
        "options": {"queue": "default"},
    },
    "consolidate-memories": {
        "task": "workers.tasks.memory_tasks.consolidate_memories",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
        "options": {"queue": "default"},
    },
    "decay-and-expire-memories": {
        "task": "workers.tasks.memory_tasks.decay_and_expire_memories",
        "schedule": crontab(hour=5, minute=0),  # Daily at 5 AM
        "options": {"queue": "default"},
    },
}


def _parse_cron_to_schedule(cron_expression: str) -> crontab | None:
    """Parse a cron expression string into a Celery crontab schedule.

    Supports standard 5-field cron format: minute hour day_of_month month day_of_week.

    Args:
        cron_expression: Standard cron expression (e.g., "0 9 * * *").

    Returns:
        crontab instance, or None if expression is invalid.
    """
    try:
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            logger.warning(
                "cron_parse_invalid: expression=%s, reason=expected_5_parts",
                cron_expression,
            )
            return None
        return crontab(
            minute=parts[0],
            hour=parts[1],
            day_of_month=parts[2],
            month_of_year=parts[3],
            day_of_week=parts[4],
        )
    except (ValueError, TypeError) as e:
        logger.warning(
            "cron_parse_failed: expression=%s, error=%s",
            cron_expression,
            str(e),
        )
        return None


def load_dynamic_schedules() -> dict[str, dict[str, Any]]:
    """Load dynamic schedules from ScheduledJobORM in database.

    Queries active scheduled jobs and creates Celery Beat schedule entries.
    Gracefully handles database unavailability by returning empty dict.

    Returns:
        Dict of schedule entries keyed by job name.
    """
    schedules: dict[str, dict[str, Any]] = {}

    try:
        from workers.utils import get_task_session_factory, run_async

        session_factory = get_task_session_factory()
        jobs = run_async(_load_active_jobs(session_factory))
    except Exception as e:
        logger.warning("dynamic_schedules_load_failed: error=%s", str(e))
        return schedules

    for job_id, job_name, cron_expression in jobs:
        schedule = _parse_cron_to_schedule(cron_expression)
        if schedule is None:
            logger.warning(
                "dynamic_schedule_skipped: job_id=%s, name=%s, reason=invalid_cron",
                str(job_id),
                job_name,
            )
            continue

        entry_key = f"dynamic-{job_name}"
        schedules[entry_key] = {
            "task": "workers.tasks.agent_tasks.scheduled_agent_run",
            "schedule": schedule,
            "args": [str(job_id)],
        }

    logger.info("dynamic_schedules_loaded: count=%d", len(schedules))
    return schedules


async def _load_active_jobs(
    session_factory: Any,
) -> list[tuple[Any, str, str]]:
    """Query active scheduled jobs from the database.

    Args:
        session_factory: Async session factory for DB access.

    Returns:
        List of (id, name, cron_expression) tuples for active jobs.
    """
    from sqlalchemy import select

    from src.db.models.scheduled_job import ScheduledJobORM

    async with session_factory() as session:
        stmt = select(
            ScheduledJobORM.id,
            ScheduledJobORM.name,
            ScheduledJobORM.cron_expression,
        ).where(ScheduledJobORM.is_active.is_(True))
        result = await session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]


def configure_beat_schedule(app: Celery) -> None:
    """Apply the beat schedule to a Celery application.

    Merges static BEAT_SCHEDULE with dynamic schedules loaded from DB.
    Falls back to static-only if dynamic loading fails.

    Args:
        app: Celery application instance to configure.
    """
    merged = dict(BEAT_SCHEDULE)
    dynamic = load_dynamic_schedules()
    merged.update(dynamic)
    app.conf.beat_schedule = merged
    logger.info(
        "beat_schedule_configured: static=%d, dynamic=%d, total=%d",
        len(BEAT_SCHEDULE),
        len(dynamic),
        len(merged),
    )
