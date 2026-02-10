"""Async bridge and database utilities for Celery worker tasks."""

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# Module-level singletons (one per worker process in prefork model)
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def run_async(coro):  # type: ignore[no-untyped-def]
    """Execute an async coroutine from synchronous Celery task context.

    Creates a new event loop per invocation. Safe in Celery's prefork model
    where each worker is its own process.

    Args:
        coro: Awaitable coroutine to execute.

    Returns:
        The coroutine's return value.

    Raises:
        Any exception raised by the coroutine.
    """
    return asyncio.run(coro)


def get_task_settings():
    """Load application settings for worker context.

    Returns:
        Settings instance loaded from environment.
    """
    from src.settings import load_settings

    return load_settings()


def get_task_engine() -> AsyncEngine:
    """Get or create the singleton async engine for worker tasks.

    Uses a smaller pool (3) than the FastAPI app (5) since workers
    run fewer concurrent queries.

    Returns:
        Configured async engine instance.

    Raises:
        ValueError: If DATABASE_URL is not configured.
    """
    global _engine
    if _engine is not None:
        return _engine

    settings = get_task_settings()
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for background tasks")

    _engine = create_async_engine(
        settings.database_url,
        pool_size=3,
        max_overflow=5,
    )
    logger.info("task_engine_created: pool_size=3, max_overflow=5")
    return _engine


def get_task_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the singleton session factory for worker tasks.

    Returns:
        Async session factory with expire_on_commit=False.
    """
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_task_engine()
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("task_session_factory_created")
    return _session_factory
