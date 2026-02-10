"""E2E collaboration session smoke tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.models import (
    CollaborationPattern,
    CollaborationStatus,
    ParticipantConfig,
    ParticipantRole,
)
from src.collaboration.orchestration.collaboration_orchestrator import CollaborationOrchestrator


@pytest.mark.asyncio
async def test_collaboration_pipeline_pattern() -> None:
    session = AsyncMock()
    multi_agent = AsyncMock()
    handoff = AsyncMock()

    base_session = MagicMock()
    base_session.id = uuid4()
    base_session.pattern = CollaborationPattern.PIPELINE
    base_session.status = CollaborationStatus.ACTIVE
    base_session.final_result = ""

    multi_agent.create_collaboration = AsyncMock(return_value=base_session)
    multi_agent.add_participants = AsyncMock(return_value=base_session)
    multi_agent.update_session_status = AsyncMock(return_value=base_session)

    orchestrator = CollaborationOrchestrator(session, multi_agent, handoff)
    orchestrator.execute_pattern = AsyncMock(return_value=base_session)

    result = await orchestrator.orchestrate_collaboration(
        conversation_id=uuid4(),
        pattern=CollaborationPattern.PIPELINE,
        goal="Goal",
        initiator_id=uuid4(),
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )

    assert result is not None
    multi_agent.update_session_status.assert_awaited()


@pytest.mark.asyncio
async def test_collaboration_supervisor_pattern() -> None:
    session = AsyncMock()
    multi_agent = AsyncMock()
    handoff = AsyncMock()

    base_session = MagicMock()
    base_session.id = uuid4()
    base_session.pattern = CollaborationPattern.SUPERVISOR_WORKER
    base_session.status = CollaborationStatus.ACTIVE
    base_session.final_result = ""

    multi_agent.create_collaboration = AsyncMock(return_value=base_session)
    multi_agent.add_participants = AsyncMock(return_value=base_session)
    multi_agent.update_session_status = AsyncMock(return_value=base_session)

    orchestrator = CollaborationOrchestrator(session, multi_agent, handoff)
    orchestrator.execute_pattern = AsyncMock(return_value=base_session)

    result = await orchestrator.orchestrate_collaboration(
        conversation_id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        goal="Goal",
        initiator_id=uuid4(),
        participants=[
            ParticipantConfig(agent_id=uuid4(), role=ParticipantRole.PRIMARY, instructions="")
        ],
    )

    assert result is not None
