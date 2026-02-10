"""Celery application factory and configuration."""

import logging
from typing import Optional

from celery import Celery

logger = logging.getLogger(__name__)

_app: Optional[Celery] = None


def get_celery_app() -> Celery:
    """Get or create the singleton Celery application.

    Returns:
        Configured Celery app instance with Redis broker and JSON serialization.
    """
    global _app
    if _app is not None:
        return _app

    from src.settings import load_settings

    settings = load_settings()
    broker_url = settings.redis_url or "redis://localhost:6379/0"

    app = Celery("skill_agent_workers")
    app.conf.update(
        broker_url=broker_url,
        result_backend=broker_url,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_default_queue="default",
        broker_connection_retry_on_startup=True,
    )

    # Auto-discover tasks in workers/tasks/
    app.autodiscover_tasks(["workers.tasks"])

    logger.info("celery_app_created: broker=%s", broker_url)

    _app = app
    return app
