"""Celery tasks for cleanup, expiration, and archival operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task
from sqlalchemy import delete, update

from workers.utils import get_task_session_factory, run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.cleanup_tasks.expire_tokens",
    acks_late=True,
)
def expire_tokens() -> dict[str, Any]:
    """Delete expired refresh tokens that have not been revoked.

    Removes rows from refresh_token where expires_at < now()
    and revoked_at IS NULL (already-revoked tokens are kept for audit).

    Returns:
        Dict with expired_count: number of tokens deleted.
    """
    logger.info("expire_tokens_started")
    result = run_async(_async_expire_tokens())
    logger.info("expire_tokens_completed: expired_count=%d", result["expired_count"])
    return result


async def _async_expire_tokens() -> dict[str, Any]:
    """Async implementation of expire_tokens.

    Returns:
        Dict with expired_count.
    """
    from src.db.models.auth import RefreshTokenORM

    session_factory = get_task_session_factory()
    async with session_factory() as session:
        stmt = delete(RefreshTokenORM).where(
            RefreshTokenORM.expires_at < datetime.now(timezone.utc),
            RefreshTokenORM.revoked_at.is_(None),
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"expired_count": result.rowcount}


@shared_task(
    name="workers.tasks.cleanup_tasks.close_stale_sessions",
    acks_late=True,
)
def close_stale_sessions(idle_minutes: int = 30) -> dict[str, Any]:
    """Mark active conversations as idle if inactive beyond threshold.

    Updates conversation status from 'active' to 'idle' where
    updated_at is older than now() - idle_minutes.

    Args:
        idle_minutes: Minutes of inactivity before marking idle.

    Returns:
        Dict with idle_count: number of conversations marked idle.
    """
    logger.info("close_stale_sessions_started: idle_minutes=%d", idle_minutes)
    result = run_async(_async_close_stale_sessions(idle_minutes=idle_minutes))
    logger.info("close_stale_sessions_completed: idle_count=%d", result["idle_count"])
    return result


async def _async_close_stale_sessions(idle_minutes: int) -> dict[str, Any]:
    """Async implementation of close_stale_sessions.

    Args:
        idle_minutes: Minutes of inactivity threshold.

    Returns:
        Dict with idle_count.
    """
    from src.db.models.conversation import ConversationORM, ConversationStatusEnum

    session_factory = get_task_session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)

    async with session_factory() as session:
        stmt = (
            update(ConversationORM)
            .where(
                ConversationORM.status == ConversationStatusEnum.ACTIVE.value,
                ConversationORM.updated_at < cutoff,
            )
            .values(status=ConversationStatusEnum.IDLE.value)
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"idle_count": result.rowcount}


@shared_task(
    name="workers.tasks.cleanup_tasks.archive_old_conversations",
    acks_late=True,
)
def archive_old_conversations(days: int = 90) -> dict[str, Any]:
    """Close conversations that have been inactive for extended period.

    Updates conversations to 'closed' status where updated_at is older
    than now() - days and status is not already 'closed'.

    Args:
        days: Days of inactivity before closing.

    Returns:
        Dict with closed_count: number of conversations closed.
    """
    logger.info("archive_old_conversations_started: days=%d", days)
    result = run_async(_async_archive_old_conversations(days=days))
    logger.info(
        "archive_old_conversations_completed: closed_count=%d",
        result["closed_count"],
    )
    return result


async def _async_archive_old_conversations(days: int) -> dict[str, Any]:
    """Async implementation of archive_old_conversations.

    Args:
        days: Days of inactivity threshold.

    Returns:
        Dict with closed_count.
    """
    from src.db.models.conversation import ConversationORM, ConversationStatusEnum

    session_factory = get_task_session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_factory() as session:
        stmt = (
            update(ConversationORM)
            .where(
                ConversationORM.status != ConversationStatusEnum.CLOSED.value,
                ConversationORM.updated_at < cutoff,
            )
            .values(status=ConversationStatusEnum.CLOSED.value)
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"closed_count": result.rowcount}


@shared_task(
    name="workers.tasks.cleanup_tasks.archive_expired_memories",
    acks_late=True,
)
def archive_expired_memories() -> dict[str, Any]:
    """Archive memories that have passed their expiration date.

    Updates memory tier to 'cold' and status to 'archived' where
    expires_at is set, has passed, and status is not already 'archived'.

    Returns:
        Dict with archived_count: number of memories archived.
    """
    logger.info("archive_expired_memories_started")
    result = run_async(_async_archive_expired_memories())
    logger.info(
        "archive_expired_memories_completed: archived_count=%d",
        result["archived_count"],
    )
    return result


async def _async_archive_expired_memories() -> dict[str, Any]:
    """Async implementation of archive_expired_memories.

    Returns:
        Dict with archived_count.
    """
    from src.db.models.memory import MemoryORM, MemoryStatusEnum, MemoryTierEnum

    session_factory = get_task_session_factory()

    async with session_factory() as session:
        stmt = (
            update(MemoryORM)
            .where(
                MemoryORM.expires_at.is_not(None),
                MemoryORM.expires_at < datetime.now(timezone.utc),
                MemoryORM.status != MemoryStatusEnum.ARCHIVED.value,
            )
            .values(
                tier=MemoryTierEnum.COLD.value,
                status=MemoryStatusEnum.ARCHIVED.value,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return {"archived_count": result.rowcount}
