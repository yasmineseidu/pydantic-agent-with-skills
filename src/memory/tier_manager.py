"""Memory tier management for hot/warm/cold lifecycle."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import MemoryORM, MemoryTierEnum, MemoryTypeEnum
from src.memory.memory_log import MemoryAuditLog

logger = logging.getLogger(__name__)

# Tier ordering from coldest to hottest for promotion logic
_TIER_ORDER: list[str] = [
    MemoryTierEnum.COLD.value,
    MemoryTierEnum.WARM.value,
    MemoryTierEnum.HOT.value,
]


def _tier_index(tier: str) -> int:
    """Return the numeric index of a tier in the promotion ladder.

    Args:
        tier: Tier name (hot, warm, cold).

    Returns:
        Integer index where 0=cold, 1=warm, 2=hot.
    """
    try:
        return _TIER_ORDER.index(tier)
    except ValueError:
        return 0


def _one_tier_up(current_tier: str) -> str | None:
    """Return the next tier up, or None if already at the top.

    Args:
        current_tier: Current tier name.

    Returns:
        Next higher tier name, or None if already 'hot'.
    """
    idx: int = _tier_index(current_tier)
    if idx >= len(_TIER_ORDER) - 1:
        return None
    return _TIER_ORDER[idx + 1]


class TierManager:
    """Manages hot/warm/cold tier transitions for memories.

    Evaluates promotion and demotion rules against individual memories
    and applies tier changes via the database session, logging every
    transition through the audit log.

    Args:
        session: Async SQLAlchemy session for database operations.
        audit_log: Audit log for recording tier transitions.
    """

    def __init__(self, session: AsyncSession, audit_log: MemoryAuditLog) -> None:
        self._session: AsyncSession = session
        self._audit_log: MemoryAuditLog = audit_log

    def evaluate_promotion(self, memory: MemoryORM) -> str | None:
        """Evaluate whether a memory should be promoted to a higher tier.

        Promotion rules (evaluated in priority order):
        1. access_count > 10 within the last 7 days AND not already hot -> 'hot'
        2. is_pinned AND not already hot -> 'hot'
        3. Positive feedback in metadata AND importance >= 7 -> one tier up

        Args:
            memory: The memory ORM instance to evaluate.

        Returns:
            New tier name if promotion is warranted, None otherwise.
        """
        now: datetime = datetime.now(timezone.utc)
        current_tier: str = memory.tier

        # Rule 1: High access count in recent window
        seven_days_ago: datetime = now - timedelta(days=7)
        if (
            memory.access_count > 10
            and memory.last_accessed_at >= seven_days_ago
            and current_tier != MemoryTierEnum.HOT.value
        ):
            logger.info(
                "evaluate_promotion: memory_id=%s rule=high_access new_tier=hot",
                memory.id,
            )
            return MemoryTierEnum.HOT.value

        # Rule 2: Pinned memories belong in hot tier
        if memory.is_pinned and current_tier != MemoryTierEnum.HOT.value:
            logger.info(
                "evaluate_promotion: memory_id=%s rule=pinned new_tier=hot",
                memory.id,
            )
            return MemoryTierEnum.HOT.value

        # Rule 3: Positive feedback with high importance
        metadata: dict = memory.metadata_json or {}
        has_positive_feedback: bool = metadata.get("positive_feedback", False) is True
        if has_positive_feedback and memory.importance >= 7:
            new_tier: str | None = _one_tier_up(current_tier)
            if new_tier is not None:
                logger.info(
                    "evaluate_promotion: memory_id=%s rule=positive_feedback new_tier=%s",
                    memory.id,
                    new_tier,
                )
                return new_tier

        return None

    def evaluate_demotion(self, memory: MemoryORM) -> str | None:
        """Evaluate whether a memory should be demoted to a lower tier.

        Never demotes: identity type, pinned, or importance >= 8.

        Demotion rules (evaluated in priority order):
        1. status == 'superseded' -> 'cold'
        2. importance < 3 AND access_count < 2 AND age > 90 days AND NOT pinned -> 'cold'
        3. tier == 'hot' AND access_count < 5 in 30 days AND NOT pinned -> 'warm'

        Args:
            memory: The memory ORM instance to evaluate.

        Returns:
            New tier name if demotion is warranted, None otherwise.
        """
        # Never-demote guards
        if memory.memory_type == MemoryTypeEnum.IDENTITY.value:
            return None
        if memory.is_pinned:
            return None
        if memory.importance >= 8:
            return None

        now: datetime = datetime.now(timezone.utc)
        current_tier: str = memory.tier

        # Rule 1: Superseded memories move to cold
        if memory.status == "superseded" and current_tier != MemoryTierEnum.COLD.value:
            logger.info(
                "evaluate_demotion: memory_id=%s rule=superseded new_tier=cold",
                memory.id,
            )
            return MemoryTierEnum.COLD.value

        # Rule 2: Low-value, rarely-accessed, old memories go cold
        age: timedelta = now - memory.created_at.replace(tzinfo=timezone.utc)
        if memory.importance < 3 and memory.access_count < 2 and age > timedelta(days=90):
            if current_tier != MemoryTierEnum.COLD.value:
                logger.info(
                    "evaluate_demotion: memory_id=%s rule=low_value_old new_tier=cold",
                    memory.id,
                )
                return MemoryTierEnum.COLD.value

        # Rule 3: Hot memories with low recent access drop to warm
        thirty_days_ago: datetime = now - timedelta(days=30)
        if (
            current_tier == MemoryTierEnum.HOT.value
            and memory.access_count < 5
            and memory.last_accessed_at < thirty_days_ago
        ):
            logger.info(
                "evaluate_demotion: memory_id=%s rule=hot_low_access new_tier=warm",
                memory.id,
            )
            return MemoryTierEnum.WARM.value

        return None

    async def promote(self, memory_id: UUID, new_tier: str) -> None:
        """Promote a memory to a higher tier.

        Updates the memory's tier in the database and logs the transition
        via the audit log.

        Args:
            memory_id: UUID of the memory to promote.
            new_tier: Target tier name (hot, warm).
        """
        # Fetch current tier for audit log
        result = await self._session.get(MemoryORM, memory_id)
        old_tier: str = result.tier if result else "unknown"

        stmt = update(MemoryORM).where(MemoryORM.id == memory_id).values(tier=new_tier)
        await self._session.execute(stmt)
        await self._session.flush()

        await self._audit_log.log_promoted(
            memory_id=memory_id,
            old_tier=old_tier,
            new_tier=new_tier,
            changed_by="system",
        )
        logger.info(
            "promote: memory_id=%s old_tier=%s new_tier=%s",
            memory_id,
            old_tier,
            new_tier,
        )

    async def demote(self, memory_id: UUID, new_tier: str) -> None:
        """Demote a memory to a lower tier.

        Updates the memory's tier in the database and logs the transition
        via the audit log.

        Args:
            memory_id: UUID of the memory to demote.
            new_tier: Target tier name (warm, cold).
        """
        # Fetch current tier for audit log
        result = await self._session.get(MemoryORM, memory_id)
        old_tier: str = result.tier if result else "unknown"

        stmt = update(MemoryORM).where(MemoryORM.id == memory_id).values(tier=new_tier)
        await self._session.execute(stmt)
        await self._session.flush()

        await self._audit_log.log_promoted(
            memory_id=memory_id,
            old_tier=old_tier,
            new_tier=new_tier,
            changed_by="system",
        )
        logger.info(
            "demote: memory_id=%s old_tier=%s new_tier=%s",
            memory_id,
            old_tier,
            new_tier,
        )
