"""Tests for chat routing integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import src.api.routers.chat as chat_module
from src.api.schemas.chat import ChatRequest
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.conversation import MessageRoleEnum
from src.dependencies import AgentDependencies


@pytest.mark.asyncio
async def test_chat_routes_to_selected_agent() -> None:
    """Chat should use routed agent slug from _route_to_agent."""
    db_session = AsyncMock()
    conv_id = uuid4()
    user_msg_id = uuid4()
    assistant_msg_id = uuid4()

    def _mock_add(obj):
        if hasattr(obj, "role"):
            if obj.role == MessageRoleEnum.USER.value:
                obj.id = user_msg_id
            elif obj.role == MessageRoleEnum.ASSISTANT.value:
                obj.id = assistant_msg_id
        elif hasattr(obj, "message_count"):
            obj.id = conv_id

    db_session.add = MagicMock(side_effect=_mock_add)
    db_session.flush = AsyncMock()
    db_session.refresh = AsyncMock()
    db_session.commit = AsyncMock()

    team_id = uuid4()
    user = MagicMock()
    user.id = uuid4()

    mock_agent = MagicMock(spec=AgentORM)
    mock_agent.id = uuid4()
    mock_agent.team_id = team_id
    mock_agent.status = AgentStatusEnum.ACTIVE.value
    mock_agent.name = "Routed Agent"
    mock_agent.slug = "routed-agent"
    mock_agent.personality = None
    mock_agent.model_config_json = None

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=mock_agent)
    db_session.execute = AsyncMock(return_value=result)

    mock_run_result = MagicMock()
    mock_run_result.output = "Hello"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_run_result.usage = MagicMock(return_value=mock_usage)

    mock_settings = MagicMock()
    mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

    mock_agent_deps = MagicMock(spec=AgentDependencies)
    mock_agent_deps.memory_retriever = None
    mock_agent_deps.memory_extractor = None

    with (
        patch("src.api.routers.chat.skill_agent") as mock_skill_agent,
        patch(
            "src.api.routers.chat._route_to_agent", new=AsyncMock(return_value="routed-agent")
        ) as mock_route,
    ):
        mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

        response = await chat_module.chat(
            agent_slug="original-agent",
            body=ChatRequest(message="Hello"),
            current_user=(user, team_id),
            db=db_session,
            settings=mock_settings,
            agent_deps=mock_agent_deps,
        )

    assert response.response == "Hello"
    mock_route.assert_awaited_once()
    assert response.message_id == assistant_msg_id
