"""Tests for MultiAgentManager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.coordination.multi_agent_manager import MultiAgentManager
from src.collaboration.models import CollaborationPattern, CollaborationStatus, ParticipantRole
from src.db.models.collaboration import CollaborationParticipantV2ORM, CollaborationSessionORM


@pytest.mark.asyncio
async def test_create_collaboration_success() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    manager = MultiAgentManager(session)
    result = await manager.create_collaboration(
        conversation_id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        goal="Test",
        initiator_id=uuid4(),
    )

    assert result.status == CollaborationStatus.ACTIVE
    assert result.pattern == CollaborationPattern.SUPERVISOR_WORKER


@pytest.mark.asyncio
async def test_add_participants_returns_session() -> None:
    session = AsyncMock()
    added = []

    def _add(obj):
        added.append(obj)

    async def _flush():
        for obj in added:
            if (
                isinstance(obj, CollaborationParticipantV2ORM)
                and getattr(obj, "created_at", None) is None
            ):
                obj.created_at = datetime.now(timezone.utc)

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock(side_effect=_flush)

    session_orm = MagicMock(spec=CollaborationSessionORM)
    session_orm.id = uuid4()
    session_orm.session_type = CollaborationPattern.PIPELINE.value
    session_orm.status = CollaborationStatus.ACTIVE.value
    session_orm.started_at = datetime.now(timezone.utc)
    session_orm.completed_at = None
    session_orm.goal = "Goal"

    session.get = AsyncMock(return_value=session_orm)

    manager = MultiAgentManager(session)
    result = await manager.add_participants(
        session_id=session_orm.id,
        participants=[(uuid4(), ParticipantRole.INVITED)],
    )

    assert result.pattern == CollaborationPattern.PIPELINE
    assert result.participants


@pytest.mark.asyncio
async def test_update_session_status_sets_completed_at() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()

    session_orm = MagicMock(spec=CollaborationSessionORM)
    session_orm.id = uuid4()
    session_orm.session_type = CollaborationPattern.CONSENSUS.value
    session_orm.status = CollaborationStatus.ACTIVE.value
    session_orm.started_at = datetime.now(timezone.utc)
    session_orm.completed_at = None

    session.get = AsyncMock(return_value=session_orm)

    manager = MultiAgentManager(session)
    result = await manager.update_session_status(
        session_id=session_orm.id,
        status=CollaborationStatus.COMPLETED,
        final_result="done",
    )

    assert result.status == CollaborationStatus.COMPLETED
    assert session_orm.completed_at is not None
