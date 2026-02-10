"""Tests for CollaborationOrchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.models import (
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    ParticipantConfig,
    ParticipantRole,
)
from src.collaboration.orchestration.collaboration_orchestrator import CollaborationOrchestrator


@pytest.mark.asyncio
async def test_orchestrate_collaboration_completes() -> None:
    session = AsyncMock()
    multi_agent = AsyncMock()
    handoff = AsyncMock()

    base_session = CollaborationSession(
        id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        status=CollaborationStatus.ACTIVE,
        initiator_id=uuid4(),
        participants=[],
        started_at=datetime.now(timezone.utc),
    )

    multi_agent.create_collaboration = AsyncMock(return_value=base_session)
    multi_agent.add_participants = AsyncMock(return_value=base_session)
    completed_session = base_session.model_copy(update={"status": CollaborationStatus.COMPLETED})
    multi_agent.update_session_status = AsyncMock(return_value=completed_session)

    orchestrator = CollaborationOrchestrator(session, multi_agent, handoff)
    orchestrator.execute_pattern = AsyncMock(return_value=base_session)

    result = await orchestrator.orchestrate_collaboration(
        conversation_id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        goal="Test",
        initiator_id=base_session.initiator_id,
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )

    assert result.status == CollaborationStatus.COMPLETED
    orchestrator.execute_pattern.assert_awaited()


@pytest.mark.asyncio
async def test_execute_pattern_dispatches() -> None:
    session = AsyncMock()
    multi_agent = AsyncMock()
    handoff = AsyncMock()

    orchestrator = CollaborationOrchestrator(session, multi_agent, handoff)
    orchestrator._execute_supervisor_worker = AsyncMock(return_value=MagicMock())
    orchestrator._execute_brainstorm = AsyncMock(return_value=MagicMock())
    orchestrator._execute_consensus = AsyncMock(return_value=MagicMock())

    collab_session = CollaborationSession(
        id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        status=CollaborationStatus.ACTIVE,
        initiator_id=uuid4(),
        participants=[],
        started_at=datetime.now(timezone.utc),
    )

    await orchestrator.execute_pattern(
        session=collab_session,
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )

    orchestrator._execute_supervisor_worker.assert_awaited()

    collab_session = collab_session.model_copy(update={"pattern": CollaborationPattern.BRAINSTORM})
    await orchestrator.execute_pattern(
        session=collab_session,
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )
    orchestrator._execute_brainstorm.assert_awaited()

    collab_session = collab_session.model_copy(update={"pattern": CollaborationPattern.CONSENSUS})
    await orchestrator.execute_pattern(
        session=collab_session,
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )
    orchestrator._execute_consensus.assert_awaited()
