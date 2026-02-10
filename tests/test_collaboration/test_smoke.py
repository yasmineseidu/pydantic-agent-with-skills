"""Smoke tests for Phase 7 collaboration workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.routers.chat import _route_to_agent
from src.collaboration.delegation.delegation_manager import DelegationManager
from src.collaboration.models import AgentTaskStatus, CollaborationPattern
from src.collaboration.orchestration.collaboration_orchestrator import CollaborationOrchestrator
from src.moe.expert_gate import ExpertGate


@pytest.mark.asyncio
async def test_e2e_routing_smoke() -> None:
    """Routing smoke test uses expert gate selection when enabled."""
    session = AsyncMock()

    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Expert"
    agent.shared_skill_names = ["python"]
    agent.custom_skill_names = []
    agent.disabled_skill_names = []
    agent.personality = {"analytical": 0.9}

    result = MagicMock()
    result.scalars.return_value.all.return_value = [agent]
    session.execute = AsyncMock(return_value=result)

    settings = SimpleNamespace(feature_flags=SimpleNamespace(enable_expert_gate=True))

    gate = ExpertGate(settings)
    selection = await gate.select_best_agent(
        session=session,
        team_id=uuid4(),
        task_description="Need python",
    )

    assert selection is not None


@pytest.mark.asyncio
async def test_e2e_delegation_smoke() -> None:
    """Delegation smoke test returns a pending task."""
    session = AsyncMock()
    last_added = {}

    def _add(obj):
        last_added["obj"] = obj

    async def _flush():
        obj = last_added.get("obj")
        if obj and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if obj and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock(side_effect=_flush)

    manager = DelegationManager(session)
    result = await manager.delegate_task(
        conversation_id=uuid4(),
        created_by_agent_id=uuid4(),
        assigned_to_agent_id=uuid4(),
        title="Smoke",
        description="Check",
        priority=5,
    )

    assert result.status == AgentTaskStatus.PENDING


@pytest.mark.asyncio
async def test_e2e_collaboration_smoke() -> None:
    """Collaboration orchestrator smoke test completes successfully."""
    session = AsyncMock()
    multi_agent = AsyncMock()
    handoff = AsyncMock()

    base_session = MagicMock()
    base_session.id = uuid4()
    base_session.pattern = CollaborationPattern.PIPELINE
    base_session.status = "active"
    base_session.final_result = ""

    multi_agent.create_collaboration = AsyncMock(return_value=base_session)
    multi_agent.add_participants = AsyncMock(return_value=base_session)
    multi_agent.update_session_status = AsyncMock(return_value=base_session)

    orchestrator = CollaborationOrchestrator(session, multi_agent, handoff)
    orchestrator.execute_pattern = AsyncMock(return_value=base_session)

    result = await orchestrator.orchestrate_collaboration(
        conversation_id=uuid4(),
        pattern=CollaborationPattern.PIPELINE,
        goal="Smoke",
        initiator_id=uuid4(),
        participants=[],
    )

    assert result is not None


@pytest.mark.asyncio
async def test_backward_compatibility_route_to_agent_no_flags() -> None:
    """Route helper should return current agent when flags disabled."""
    settings = SimpleNamespace(feature_flags=SimpleNamespace(enable_expert_gate=False, enable_agent_collaboration=False))
    session = AsyncMock()

    slug = await _route_to_agent(
        message="Test",
        team_id=uuid4(),
        user_id=uuid4(),
        current_agent_slug="default",
        db=session,
        settings=settings,
        request_id="req",
    )

    assert slug == "default"
