"""Tests for ExpertGate selection logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.moe.expert_gate import ExpertGate


def _settings(enable_expert_gate: bool = True):
    return SimpleNamespace(feature_flags=SimpleNamespace(enable_expert_gate=enable_expert_gate))


@pytest.mark.asyncio
async def test_expert_gate_returns_empty_when_disabled() -> None:
    session = AsyncMock()
    gate = ExpertGate(_settings(enable_expert_gate=False))

    result = await gate.score_agents(
        session=session,
        team_id=uuid4(),
        task_description="test",
    )

    assert result == []


@pytest.mark.asyncio
async def test_expert_gate_selects_best_agent() -> None:
    session = AsyncMock()
    agent_a = MagicMock()
    agent_a.id = uuid4()
    agent_a.name = "Analyst"
    agent_a.shared_skill_names = ["python", "analysis"]
    agent_a.custom_skill_names = []
    agent_a.disabled_skill_names = []
    agent_a.personality = {"analytical": 0.8}

    agent_b = MagicMock()
    agent_b.id = uuid4()
    agent_b.name = "Designer"
    agent_b.shared_skill_names = ["design"]
    agent_b.custom_skill_names = []
    agent_b.disabled_skill_names = []
    agent_b.personality = {"creativity": 0.9}

    result = MagicMock()
    result.scalars.return_value.all.return_value = [agent_a, agent_b]
    session.execute = AsyncMock(return_value=result)

    gate = ExpertGate(_settings())

    selection = await gate.select_best_agent(
        session=session,
        team_id=uuid4(),
        task_description="Need python analysis",
        required_skills=["python"],
        task_metadata={"task_type": "analytical"},
    )

    assert selection is not None
    assert selection.expert_id in {agent_a.id, agent_b.id}
    assert selection.rank == 1
    assert selection.score.overall >= 0.0
