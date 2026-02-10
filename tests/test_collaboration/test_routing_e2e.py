"""E2E routing smoke tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.routers.chat import _route_to_agent
from src.collaboration.routing.agent_router import AgentRouter
from src.moe.expert_gate import ExpertGate


@pytest.mark.asyncio
async def test_route_to_agent_with_expert_gate(monkeypatch) -> None:
    """Expert gate path should select agent slug when enabled."""
    settings = SimpleNamespace(feature_flags=SimpleNamespace(enable_expert_gate=True))
    settings = settings  # type: ignore[assignment]

    selection = MagicMock()
    selection.expert_id = uuid4()
    selection.score = MagicMock(overall=0.8)

    async def _select_best_agent(*args, **kwargs):
        return selection

    agent = MagicMock()
    agent.id = selection.expert_id
    agent.slug = "expert"
    agent.team_id = uuid4()
    agent.status = "active"

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=agent)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    monkeypatch.setattr(ExpertGate, "select_best_agent", _select_best_agent)

    slug = await _route_to_agent(
        message="route",
        team_id=agent.team_id,
        user_id=uuid4(),
        current_agent_slug="default",
        db=db,
        settings=settings,  # type: ignore[arg-type]
        request_id="req",
    )

    assert slug == "expert"


@pytest.mark.asyncio
async def test_route_to_agent_with_router(monkeypatch) -> None:
    """AgentRouter path should be used when expert gate disabled."""
    settings = SimpleNamespace(
        feature_flags=SimpleNamespace(enable_expert_gate=False, enable_agent_collaboration=True)
    )

    decision = MagicMock()
    decision.selected_agent_id = uuid4()
    decision.confidence = 0.7
    decision.reasoning = "match"

    async def _route_to_agent_impl(*args, **kwargs):
        return decision

    agent = MagicMock()
    agent.id = decision.selected_agent_id
    agent.slug = "router"
    agent.team_id = uuid4()
    agent.status = "active"

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=agent)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    monkeypatch.setattr(AgentRouter, "route_to_agent", _route_to_agent_impl)

    slug = await _route_to_agent(
        message="route",
        team_id=agent.team_id,
        user_id=uuid4(),
        current_agent_slug="default",
        db=db,
        settings=settings,  # type: ignore[arg-type]
        request_id="req",
    )

    assert slug == "router"


@pytest.mark.asyncio
async def test_route_to_agent_flags_off_returns_default() -> None:
    settings = SimpleNamespace(
        feature_flags=SimpleNamespace(enable_expert_gate=False, enable_agent_collaboration=False)
    )
    db = AsyncMock()

    slug = await _route_to_agent(
        message="route",
        team_id=uuid4(),
        user_id=uuid4(),
        current_agent_slug="default",
        db=db,
        settings=settings,  # type: ignore[arg-type]
        request_id="req",
    )

    assert slug == "default"
