"""Append-only audit log for memory lifecycle events."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import MemoryLogORM, MemoryORM
from src.memory.types import MemorySnapshot

logger = logging.getLogger(__name__)


class MemoryAuditLog:
    """Append-only audit log that records every memory lifecycle event.

    All writes are INSERT-only -- no updates, no deletes.
    Supports timeline reconstruction for debugging and compliance.

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_created(
        self,
        memory_id: UUID,
        content: str,
        source: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a memory was created.

        Args:
            memory_id: UUID of the newly created memory.
            content: The content of the new memory.
            source: How the memory was created (extraction, explicit, etc.).
            changed_by: Who or what created the memory.
        """
        log_entry = MemoryLogORM(
            memory_id=memory_id,
            action="created",
            new_content=content,
            changed_by=changed_by,
            reason=f"source={source}",
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_created: memory_id=%s source=%s changed_by=%s",
            memory_id,
            source,
            changed_by,
        )

    async def log_updated(
        self,
        memory_id: UUID,
        old_content: str,
        new_content: str,
        reason: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a memory's content was updated.

        Args:
            memory_id: UUID of the updated memory.
            old_content: Previous content before the update.
            new_content: New content after the update.
            reason: Why the update was made.
            changed_by: Who or what performed the update.
        """
        log_entry = MemoryLogORM(
            memory_id=memory_id,
            action="updated",
            old_content=old_content,
            new_content=new_content,
            changed_by=changed_by,
            reason=reason,
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_updated: memory_id=%s reason=%s changed_by=%s",
            memory_id,
            reason,
            changed_by,
        )

    async def log_superseded(
        self,
        old_id: UUID,
        new_id: UUID,
        reason: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a memory was superseded by a newer version.

        Args:
            old_id: UUID of the memory being superseded.
            new_id: UUID of the replacement memory.
            reason: Why the memory was superseded.
            changed_by: Who or what triggered the supersession.
        """
        log_entry = MemoryLogORM(
            memory_id=old_id,
            action="superseded",
            changed_by=changed_by,
            reason=reason,
            related_memory_ids=[str(new_id)],
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_superseded: old_id=%s new_id=%s reason=%s changed_by=%s",
            old_id,
            new_id,
            reason,
            changed_by,
        )

    async def log_promoted(
        self,
        memory_id: UUID,
        old_tier: str,
        new_tier: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a memory was promoted to a different storage tier.

        Args:
            memory_id: UUID of the promoted memory.
            old_tier: Previous tier (hot, warm, cold).
            new_tier: New tier after promotion.
            changed_by: Who or what triggered the promotion.
        """
        log_entry = MemoryLogORM(
            memory_id=memory_id,
            action="promoted",
            old_tier=old_tier,
            new_tier=new_tier,
            changed_by=changed_by,
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_promoted: memory_id=%s old_tier=%s new_tier=%s changed_by=%s",
            memory_id,
            old_tier,
            new_tier,
            changed_by,
        )

    async def log_demoted(
        self,
        memory_id: UUID,
        old_tier: str,
        new_tier: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a memory was demoted to a lower storage tier.

        Args:
            memory_id: UUID of the demoted memory.
            old_tier: Previous tier (hot, warm).
            new_tier: New tier after demotion (warm, cold).
            changed_by: Who or what triggered the demotion.
        """
        log_entry = MemoryLogORM(
            memory_id=memory_id,
            action="demoted",
            old_tier=old_tier,
            new_tier=new_tier,
            changed_by=changed_by,
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_demoted: memory_id=%s old_tier=%s new_tier=%s changed_by=%s",
            memory_id,
            old_tier,
            new_tier,
            changed_by,
        )

    async def log_contradiction(
        self,
        memory_a: UUID,
        memory_b: UUID,
        resolution: str,
        changed_by: str = "system",
    ) -> None:
        """Log that a contradiction was detected between two memories.

        Args:
            memory_a: UUID of the first conflicting memory.
            memory_b: UUID of the second conflicting memory.
            resolution: How the contradiction was resolved.
            changed_by: Who or what detected the contradiction.
        """
        log_entry = MemoryLogORM(
            memory_id=memory_a,
            action="contradiction_detected",
            changed_by=changed_by,
            reason=resolution,
            related_memory_ids=[str(memory_a), str(memory_b)],
        )
        self._session.add(log_entry)
        await self._session.flush()
        logger.info(
            "log_contradiction: memory_a=%s memory_b=%s resolution=%s changed_by=%s",
            memory_a,
            memory_b,
            resolution,
            changed_by,
        )

    async def reconstruct_at(
        self,
        timestamp: datetime,
        team_id: UUID,
    ) -> list[MemorySnapshot]:
        """Reconstruct the state of all memories for a team at a point in time.

        Replays audit log entries up to the given timestamp and builds
        a snapshot of each memory's last known state.

        Args:
            timestamp: The point in time to reconstruct.
            team_id: Team whose memories to reconstruct.

        Returns:
            List of MemorySnapshot representing each memory's state at the timestamp.
        """
        # First, find all memory IDs belonging to this team
        team_memory_stmt = select(MemoryORM.id).where(MemoryORM.team_id == team_id)
        team_result = await self._session.execute(team_memory_stmt)
        team_memory_ids: set[UUID] = {row[0] for row in team_result.all()}

        if not team_memory_ids:
            return []

        # Query all log entries for those memories up to the timestamp
        stmt = (
            select(MemoryLogORM)
            .where(
                and_(
                    MemoryLogORM.memory_id.in_(team_memory_ids),
                    MemoryLogORM.created_at <= timestamp,
                )
            )
            .order_by(MemoryLogORM.created_at.asc())
        )
        result = await self._session.execute(stmt)
        log_entries: list[MemoryLogORM] = list(result.scalars().all())

        # Replay log entries to build snapshots
        snapshots: dict[UUID, MemorySnapshot] = {}

        for entry in log_entries:
            mid = entry.memory_id

            if entry.action == "created":
                snapshots[mid] = MemorySnapshot(
                    memory_id=mid,
                    content=entry.new_content or "",
                    status="active",
                    tier="warm",
                    timestamp=entry.created_at,
                )

            elif entry.action == "updated" and mid in snapshots:
                snapshots[mid] = snapshots[mid].model_copy(
                    update={
                        "content": entry.new_content or snapshots[mid].content,
                        "timestamp": entry.created_at,
                    }
                )

            elif entry.action == "superseded" and mid in snapshots:
                snapshots[mid] = snapshots[mid].model_copy(
                    update={
                        "status": "superseded",
                        "tier": "cold",
                        "timestamp": entry.created_at,
                    }
                )

            elif entry.action in ("promoted", "demoted") and mid in snapshots:
                snapshots[mid] = snapshots[mid].model_copy(
                    update={
                        "tier": entry.new_tier or snapshots[mid].tier,
                        "timestamp": entry.created_at,
                    }
                )

            elif entry.action == "contradiction_detected" and mid in snapshots:
                snapshots[mid] = snapshots[mid].model_copy(
                    update={
                        "status": "disputed",
                        "timestamp": entry.created_at,
                    }
                )

        logger.info(
            "reconstruct_at: timestamp=%s team_id=%s snapshots=%d",
            timestamp,
            team_id,
            len(snapshots),
        )
        return list(snapshots.values())
