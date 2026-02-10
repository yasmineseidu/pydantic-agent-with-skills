"""Tests for collaboration API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.collaboration.models import (
    AgentProfile,
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    HandoffResult,
)
from src.api.dependencies import get_settings
from src.settings import load_settings


@pytest.mark.asyncio
async def test_route_to_agent_returns_decision(auth_client, app) -> None:
    """Route endpoint returns a routing decision when expert gate is enabled."""
    agent_a_id = uuid4()
    agent_b_id = uuid4()

    profiles = [
        AgentProfile(
            agent_id=agent_a_id,
            name="Memory Analyst",
            capabilities=["memory", "analysis"],
            specializations=["memory"],
            personality_summary="analytical and thorough",
            average_response_time=3.0,
        ),
        AgentProfile(
            agent_id=agent_b_id,
            name="Designer",
            capabilities=["design"],
            specializations=["ui"],
            personality_summary="creative and artistic",
            average_response_time=4.0,
        ),
    ]

    test_settings = load_settings()
    test_settings.feature_flags.enable_expert_gate = True

    app.dependency_overrides[get_settings] = lambda: test_settings  # type: ignore[name-defined]

    with patch(
        "src.collaboration.routing.agent_directory.AgentDirectory.list_agents",
        new=AsyncMock(return_value=profiles),
    ):
        response = await auth_client.post(
            "/v1/collaboration/route",
            json={"query": "analyze memory system", "current_agent_id": str(agent_b_id)},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["selected_agent_id"] == str(agent_a_id)
    assert data["confidence"] >= 0.3


@pytest.mark.asyncio
async def test_recommend_agents_returns_ranked_results(auth_client, app) -> None:
    """Recommend endpoint returns multiple agent recommendations."""
    agent_a_id = uuid4()
    agent_b_id = uuid4()

    profiles = [
        AgentProfile(
            agent_id=agent_a_id,
            name="Memory Analyst",
            capabilities=["memory", "analysis"],
            specializations=["memory"],
            personality_summary="analytical",
            average_response_time=3.0,
        ),
        AgentProfile(
            agent_id=agent_b_id,
            name="Researcher",
            capabilities=["research"],
            specializations=["analysis"],
            personality_summary="systematic",
            average_response_time=5.0,
        ),
    ]

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True

    app.dependency_overrides[get_settings] = lambda: test_settings  # type: ignore[name-defined]

    with patch(
        "src.collaboration.routing.agent_directory.AgentDirectory.list_agents",
        new=AsyncMock(return_value=profiles),
    ):
        response = await auth_client.post(
            "/v1/collaboration/recommendations",
            json={"query": "analysis and research", "min_agents": 2, "max_agents": 3},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {item["agent_id"] for item in data} == {str(agent_a_id), str(agent_b_id)}


@pytest.mark.asyncio
async def test_initiate_handoff_persists_on_success(auth_client, db_session) -> None:
    """Handoff endpoint commits when the handoff succeeds."""
    handoff_result = HandoffResult(
        target_agent_id=uuid4(),
        success=True,
        context_transferred="summary",
        reason="Need a specialist",
    )

    with patch(
        "src.collaboration.coordination.handoff_manager.HandoffManager.initiate_handoff",
        new=AsyncMock(return_value=handoff_result),
    ):
        response = await auth_client.post(
            "/v1/collaboration/handoff",
            json={
                "conversation_id": str(uuid4()),
                "from_agent_id": str(uuid4()),
                "to_agent_id": str(handoff_result.target_agent_id),
                "reason": "Need a specialist",
                "context_transferred": {"summary": "context"},
            },
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_list_handoffs_returns_history(auth_client) -> None:
    """List handoffs returns serialized records."""
    record = MagicMock()
    record.id = uuid4()
    record.conversation_id = uuid4()
    record.from_agent_id = uuid4()
    record.to_agent_id = uuid4()
    record.reason = "handoff"
    record.context_transferred = {"summary": "context"}
    record.handoff_at = datetime.now(timezone.utc)

    with patch(
        "src.collaboration.coordination.handoff_manager.HandoffManager.get_handoff_history",
        new=AsyncMock(return_value=[record]),
    ):
        response = await auth_client.get(
            f"/v1/collaboration/handoffs/{record.conversation_id}?limit=5"
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(record.id)


@pytest.mark.asyncio
async def test_create_session_commits(auth_client, db_session) -> None:
    """Session creation commits on success."""
    session = CollaborationSession(
        id=uuid4(),
        pattern=CollaborationPattern.SUPERVISOR_WORKER,
        status=CollaborationStatus.ACTIVE,
        initiator_id=uuid4(),
        participants=[],
        started_at=datetime.now(timezone.utc),
        stage_outputs=[],
        metadata={},
    )

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.create_collaboration",
        new=AsyncMock(return_value=session),
    ):
        response = await auth_client.post(
            "/v1/collaboration/sessions",
            json={
                "conversation_id": str(uuid4()),
                "pattern": "supervisor_worker",
                "goal": "Test session",
                "initiator_id": str(session.initiator_id),
            },
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_add_participants_commits(auth_client, db_session) -> None:
    """Adding participants commits on success."""
    session = CollaborationSession(
        id=uuid4(),
        pattern=CollaborationPattern.PIPELINE,
        status=CollaborationStatus.ACTIVE,
        initiator_id=uuid4(),
        participants=[],
        started_at=datetime.now(timezone.utc),
        stage_outputs=[],
        metadata={},
    )

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.add_participants",
        new=AsyncMock(return_value=session),
    ):
        response = await auth_client.post(
            f"/v1/collaboration/sessions/{session.id}/participants",
            json={
                "participants": [
                    {"agent_id": str(uuid4()), "role": "invited"},
                ]
            },
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_update_session_status_commits(auth_client, db_session) -> None:
    """Status update commits on success."""
    session = CollaborationSession(
        id=uuid4(),
        pattern=CollaborationPattern.CONSENSUS,
        status=CollaborationStatus.COMPLETED,
        initiator_id=uuid4(),
        participants=[],
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        stage_outputs=[],
        final_result="done",
        metadata={},
    )

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.update_session_status",
        new=AsyncMock(return_value=session),
    ):
        response = await auth_client.patch(
            f"/v1/collaboration/sessions/{session.id}/status",
            json={"status": "completed", "final_result": "done"},
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1
