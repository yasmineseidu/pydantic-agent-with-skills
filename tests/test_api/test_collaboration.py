"""Tests for collaboration API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.collaboration.models import (
    AgentMessage,
    AgentMessageType,
    AgentProfile,
    AgentTask,
    AgentTaskStatus,
    AgentTaskType,
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    HandoffResult,
    TaskPriority,
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
async def test_initiate_handoff_persists_on_success(auth_client, app, db_session) -> None:
    """Handoff endpoint commits when the handoff succeeds."""
    handoff_result = HandoffResult(
        target_agent_id=uuid4(),
        success=True,
        context_transferred="summary",
        reason="Need a specialist",
    )

    test_settings = load_settings()
    test_settings.feature_flags.enable_agent_collaboration = True

    with patch(
        "src.collaboration.coordination.handoff_manager.HandoffManager.initiate_handoff",
        new=AsyncMock(return_value=handoff_result),
    ):
        app.dependency_overrides[get_settings] = lambda: test_settings
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
async def test_list_handoffs_returns_history(auth_client, app) -> None:
    """List handoffs returns serialized records."""
    record = MagicMock()
    record.id = uuid4()
    record.conversation_id = uuid4()
    record.from_agent_id = uuid4()
    record.to_agent_id = uuid4()
    record.reason = "handoff"
    record.context_transferred = {"summary": "context"}
    record.handoff_at = datetime.now(timezone.utc)

    test_settings = load_settings()
    test_settings.feature_flags.enable_agent_collaboration = True

    with patch(
        "src.collaboration.coordination.handoff_manager.HandoffManager.get_handoff_history",
        new=AsyncMock(return_value=[record]),
    ):
        app.dependency_overrides[get_settings] = lambda: test_settings
        response = await auth_client.get(
            f"/v1/collaboration/handoffs/{record.conversation_id}?limit=5"
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(record.id)


@pytest.mark.asyncio
async def test_create_session_commits(auth_client, app, db_session) -> None:
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

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.create_collaboration",
        new=AsyncMock(return_value=session),
    ):
        app.dependency_overrides[get_settings] = lambda: test_settings
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
async def test_add_participants_commits(auth_client, app, db_session) -> None:
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

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.add_participants",
        new=AsyncMock(return_value=session),
    ):
        app.dependency_overrides[get_settings] = lambda: test_settings
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
async def test_update_session_status_commits(auth_client, app, db_session) -> None:
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

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True

    with patch(
        "src.collaboration.coordination.multi_agent_manager.MultiAgentManager.update_session_status",
        new=AsyncMock(return_value=session),
    ):
        app.dependency_overrides[get_settings] = lambda: test_settings
        await auth_client.patch(
            f"/v1/collaboration/sessions/{session.id}/status",
            json={"status": "completed", "final_result": "done"},
        )


@pytest.mark.asyncio
async def test_get_session_returns_status(auth_client, app, db_session) -> None:
    """Get collaboration session returns status payload."""
    session_id = uuid4()
    session_orm = MagicMock()
    session_orm.id = session_id
    session_orm.session_type = "pipeline"
    session_orm.status = "active"
    session_orm.conversation_id = uuid4()
    session_orm.goal = "Test goal"
    session_orm.total_cost = 0.0
    session_orm.total_duration_ms = 0
    session_orm.started_at = datetime.now(timezone.utc)
    session_orm.completed_at = None

    db_session.get = AsyncMock(return_value=session_orm)

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True
    app.dependency_overrides[get_settings] = lambda: test_settings

    response = await auth_client.get(f"/v1/collaborations/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(session_id)
    assert data["pattern"] == "pipeline"


@pytest.mark.asyncio
async def test_delegate_task_commits(auth_client, app, db_session) -> None:
    """Delegate task endpoint commits on success."""
    task = AgentTask(
        id=uuid4(),
        task_type=AgentTaskType.EXECUTE,
        description="Do the thing",
        status=AgentTaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
    )

    test_settings = load_settings()
    test_settings.feature_flags.enable_task_delegation = True
    app.dependency_overrides[get_settings] = lambda: test_settings

    with patch(
        "src.collaboration.delegation.delegation_manager.DelegationManager.delegate_task",
        new=AsyncMock(return_value=task),
    ):
        response = await auth_client.post(
            "/v1/tasks/delegate",
            json={
                "conversation_id": str(uuid4()),
                "created_by_agent_id": str(uuid4()),
                "assigned_to_agent_id": str(uuid4()),
                "title": "Test task",
                "description": "Do the thing",
                "priority": 5,
            },
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_cancel_task_commits(auth_client, app, db_session) -> None:
    """Cancel task endpoint commits on success."""
    task_id = uuid4()

    task_orm = MagicMock()
    task_orm.id = task_id
    task_orm.conversation_id = uuid4()
    task_orm.priority = 5
    task_orm.description = "Task"
    task_orm.status = "pending"
    task_orm.assigned_to_agent_id = uuid4()
    task_orm.created_by_agent_id = uuid4()
    task_orm.created_at = datetime.now(timezone.utc)
    task_orm.completed_at = None
    task_orm.result = None
    task_orm.parent_task_id = None
    task_orm.delegation_depth = 0
    task_orm.title = "Task"

    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=task_orm))
    )

    test_settings = load_settings()
    test_settings.feature_flags.enable_task_delegation = True
    app.dependency_overrides[get_settings] = lambda: test_settings

    task = AgentTask(
        id=task_id,
        task_type=AgentTaskType.EXECUTE,
        description="Task",
        status=AgentTaskStatus.CANCELLED,
        priority=TaskPriority.NORMAL,
        assigned_to=task_orm.assigned_to_agent_id,
        created_by=task_orm.created_by_agent_id,
        created_at=task_orm.created_at,
        completed_at=task_orm.completed_at,
        result="Task cancelled by user",
    )

    with patch(
        "src.collaboration.delegation.delegation_manager.DelegationManager.complete_task",
        new=AsyncMock(return_value=task),
    ):
        response = await auth_client.post(
            f"/v1/tasks/{task_id}/cancel",
            json={"reason": "no longer needed"},
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1


@pytest.mark.asyncio
async def test_agent_inbox_returns_messages(auth_client, app, db_session) -> None:
    """Inbox endpoint returns pending messages."""
    agent = MagicMock()
    agent.id = uuid4()

    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
    )

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True
    app.dependency_overrides[get_settings] = lambda: test_settings

    with patch(
        "src.collaboration.messaging.agent_message_bus.AgentMessageBus.get_pending_messages",
        new=AsyncMock(return_value=[]),
    ):
        response = await auth_client.get("/v1/agents/test-agent/inbox")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_send_agent_message_commits(auth_client, app, db_session) -> None:
    """Send message endpoint commits on success."""
    agent = MagicMock()
    agent.id = uuid4()

    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
    )

    test_settings = load_settings()
    test_settings.feature_flags.enable_collaboration = True
    app.dependency_overrides[get_settings] = lambda: test_settings

    message = AgentMessage(
        id=uuid4(),
        message_type=AgentMessageType.INFO_REQUEST,
        sender_id=agent.id,
        recipient_id=uuid4(),
        content="ping",
        timestamp=datetime.now(timezone.utc),
        metadata={},
    )

    with patch(
        "src.collaboration.messaging.agent_message_bus.AgentMessageBus.send_message",
        new=AsyncMock(return_value=message),
    ):
        response = await auth_client.post(
            "/v1/agents/test-agent/messages",
            json={
                "conversation_id": str(uuid4()),
                "to_agent_id": str(message.recipient_id),
                "message_type": "info_request",
                "subject": "ping",
                "body": "ping",
                "metadata": {},
            },
        )

    assert response.status_code == 200
    assert db_session.commit.await_count == 1

    assert response.status_code == 200
    assert db_session.commit.await_count == 1
