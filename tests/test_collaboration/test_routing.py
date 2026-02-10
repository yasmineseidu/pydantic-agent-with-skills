"""Unit tests for collaboration routing and directory services."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.collaboration.models import AgentProfile
from src.collaboration.routing.agent_directory import AgentDirectory
from src.collaboration.routing.agent_router import AgentRouter


def _mock_profile(agent_id, name: str, capabilities: list[str], specializations: list[str]) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        name=name,
        capabilities=capabilities,
        specializations=specializations,
        personality_summary="",
        average_response_time=1.0,
    )


def _mock_settings(*, enable_expert_gate: bool = True, enable_collaboration: bool = True):
    return SimpleNamespace(
        feature_flags=SimpleNamespace(
            enable_expert_gate=enable_expert_gate,
            enable_collaboration=enable_collaboration,
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_directory_list_agents_returns_profiles() -> None:
    user_id = uuid4()
    team_id = uuid4()

    agent_orm = MagicMock()
    agent_orm.id = uuid4()
    agent_orm.team_id = team_id
    agent_orm.name = "Routing Agent"
    agent_orm.tagline = "routes work"
    agent_orm.shared_skill_names = ["python", "testing"]
    agent_orm.custom_skill_names = ["backend"]
    agent_orm.personality = {"summary": "fast and accurate"}
    agent_orm.boundaries = {"max_tool_calls_per_turn": 10}

    result = MagicMock()
    result.scalars.return_value.all.return_value = [agent_orm]

    session = AsyncMock()
    session.execute.return_value = result

    directory = AgentDirectory(session)
    profiles = await directory.list_agents(user_id=user_id)

    assert len(profiles) == 1
    assert profiles[0].agent_id == agent_orm.id
    assert "python" in profiles[0].capabilities


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_router_route_to_agent_selects_best_match() -> None:
    user_id = uuid4()
    agent_a = _mock_profile(uuid4(), "Python Agent", ["python", "fastapi"], ["backend"])
    agent_b = _mock_profile(uuid4(), "UI Agent", ["react", "css"], ["frontend"])

    directory = MagicMock()
    directory.list_agents = AsyncMock(return_value=[agent_a, agent_b])
    router = AgentRouter(directory, _mock_settings(enable_expert_gate=True))

    decision = await router.route_to_agent(query="Need help with python api", user_id=user_id)

    assert decision.selected_agent_id == agent_a.agent_id
    assert decision.confidence > 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_router_suggest_collaboration_respects_feature_flag() -> None:
    user_id = uuid4()
    directory = MagicMock()
    directory.list_agents = AsyncMock(return_value=[])
    router = AgentRouter(directory, _mock_settings(enable_collaboration=False))

    result = await router.suggest_collaboration(query="analyze and review this", user_id=user_id)

    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_directory_check_availability_uses_boundaries() -> None:
    agent_orm = MagicMock()
    agent_orm.id = uuid4()
    agent_orm.status = "active"
    agent_orm.boundaries = {"max_tool_calls_per_turn": 3}

    directory = AgentDirectory(AsyncMock())
    availability = await directory.check_availability(agent_orm, current_load=2)

    assert availability.is_available is True
    assert availability.max_concurrent_tasks == 3


@pytest.mark.unit
def test_agent_directory_filter_by_skills_matches_all() -> None:
    agent_a = MagicMock()
    agent_a.shared_skill_names = ["python", "sql"]
    agent_a.custom_skill_names = ["backend"]

    agent_b = MagicMock()
    agent_b.shared_skill_names = ["python"]
    agent_b.custom_skill_names = ["frontend"]

    directory = AgentDirectory(AsyncMock())
    filtered = asyncio.run(directory.filter_by_skills([agent_a, agent_b], ["python", "sql"]))

    assert filtered == [agent_a]
