"""Backward compatibility tests for Phase 7 flags."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.routers.chat import _route_to_agent


@pytest.mark.asyncio
async def test_route_to_agent_defaults_when_flags_off() -> None:
    settings = SimpleNamespace(
        feature_flags=SimpleNamespace(enable_expert_gate=False, enable_agent_collaboration=False)
    )
    db = AsyncMock()

    slug = await _route_to_agent(
        message="hello",
        team_id=uuid4(),
        user_id=uuid4(),
        current_agent_slug="default",
        db=db,
        settings=settings,  # type: ignore[arg-type]
        request_id="req",
    )

    assert slug == "default"
