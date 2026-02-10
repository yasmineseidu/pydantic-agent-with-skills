"""Shared fixtures for Phase 7 collaboration tests."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.collaboration.models import RoutingDecision
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.settings import Settings


# Placeholder ExpertScore model (will be defined in Wave 4)
class ExpertScore(BaseModel):
    """Placeholder for MoE expert scoring (defined in Wave 4)."""

    agent_id: UUID
    confidence: float = Field(ge=0.0, le=1.0)
    skill_match: float = Field(ge=0.0, le=1.0)
    context_match: float = Field(ge=0.0, le=1.0)
    availability: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


@pytest.fixture
def mock_agent_orm() -> AgentORM:
    """Mock AgentORM with skills and personality.

    Returns:
        A MagicMock configured as an active AgentORM with skills and personality.
    """
    agent = MagicMock(spec=AgentORM)
    agent.id = uuid4()
    agent.team_id = uuid4()
    agent.name = "Test Agent"
    agent.slug = "test-agent"
    agent.tagline = "A test agent for collaboration"
    agent.avatar_emoji = "🤖"
    agent.status = AgentStatusEnum.ACTIVE.value
    agent.shared_skill_names = ["python", "testing"]
    agent.custom_skill_names = ["custom_skill"]
    agent.disabled_skill_names = []
    agent.personality = {
        "traits": ["helpful", "analytical"],
        "expertise": ["testing", "collaboration"],
    }
    agent.model_config_json = {
        "model_name": "anthropic/claude-sonnet-4.5",
        "temperature": 0.7,
    }
    agent.memory_config = {
        "token_budget": 2000,
        "auto_extract": True,
    }
    agent.boundaries = {
        "max_autonomy": "execute",
        "max_tool_calls_per_turn": 10,
    }
    agent.created_by = None
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


@pytest.fixture
def mock_team_agents() -> List[AgentORM]:
    """Create a list of 3-5 agents with varied skills.

    Returns:
        A list of MagicMock AgentORM instances with different skill sets.
    """
    team_id = uuid4()
    agents = []

    # Agent 1: Python expert
    agent1 = MagicMock(spec=AgentORM)
    agent1.id = uuid4()
    agent1.team_id = team_id
    agent1.name = "Python Expert"
    agent1.slug = "python-expert"
    agent1.shared_skill_names = ["python", "fastapi", "sqlalchemy"]
    agent1.personality = {"expertise": ["python", "backend"]}
    agents.append(agent1)

    # Agent 2: Frontend expert
    agent2 = MagicMock(spec=AgentORM)
    agent2.id = uuid4()
    agent2.team_id = team_id
    agent2.name = "Frontend Expert"
    agent2.slug = "frontend-expert"
    agent2.shared_skill_names = ["typescript", "react", "nextjs"]
    agent2.personality = {"expertise": ["frontend", "ui"]}
    agents.append(agent2)

    # Agent 3: Testing expert
    agent3 = MagicMock(spec=AgentORM)
    agent3.id = uuid4()
    agent3.team_id = team_id
    agent3.name = "Testing Expert"
    agent3.slug = "testing-expert"
    agent3.shared_skill_names = ["pytest", "testing", "quality"]
    agent3.personality = {"expertise": ["testing", "qa"]}
    agents.append(agent3)

    # Agent 4: DevOps expert
    agent4 = MagicMock(spec=AgentORM)
    agent4.id = uuid4()
    agent4.team_id = team_id
    agent4.name = "DevOps Expert"
    agent4.slug = "devops-expert"
    agent4.shared_skill_names = ["docker", "kubernetes", "ci_cd"]
    agent4.personality = {"expertise": ["devops", "infrastructure"]}
    agents.append(agent4)

    return agents


@pytest.fixture
def mock_routing_decision(mock_agent_orm: AgentORM) -> RoutingDecision:
    """Create a mock RoutingDecision instance.

    Args:
        mock_agent_orm: Mock agent fixture.

    Returns:
        A RoutingDecision instance with test data.
    """
    return RoutingDecision(
        selected_agent_id=mock_agent_orm.id,
        confidence=0.85,
        reasoning="High skill match for testing domain",
        alternatives=[uuid4(), uuid4()],
    )


@pytest.fixture
def mock_expert_scores(mock_team_agents: List[AgentORM]) -> List[ExpertScore]:
    """Create a list of ExpertScore instances for team agents.

    Args:
        mock_team_agents: List of mock agent fixtures.

    Returns:
        A list of ExpertScore instances with varied scores.
    """
    scores = []
    confidence_values = [0.9, 0.7, 0.6, 0.4]

    for i, agent in enumerate(mock_team_agents):
        score = ExpertScore(
            agent_id=agent.id,
            confidence=confidence_values[i],
            skill_match=confidence_values[i] * 0.95,
            context_match=confidence_values[i] * 0.90,
            availability=1.0 if i < 3 else 0.5,
            metadata={"rank": i + 1},
        )
        scores.append(score)

    return scores


@pytest.fixture
def mock_db_session() -> AsyncSession:
    """Mock AsyncSession for database operations.

    Returns:
        An AsyncMock configured as AsyncSession.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client for caching operations.

    Returns:
        An AsyncMock configured as a Redis client.
    """
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    redis.expire = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.pipeline = MagicMock()
    return redis


@pytest.fixture
def mock_embedding_service() -> AsyncMock:
    """Mock embedding service for vector operations.

    Returns:
        An AsyncMock configured as an embedding service.
    """
    embedding_service = AsyncMock()
    # Return orthogonal embeddings for testing
    embedding_service.get_embeddings = AsyncMock(
        return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    embedding_service.get_embedding = AsyncMock(return_value=[1.0, 0.0, 0.0])
    return embedding_service


@pytest.fixture
def collaboration_settings() -> Settings:
    """Settings with all Phase 7 collaboration features enabled.

    Returns:
        A Settings instance with collaboration flags enabled.
    """
    settings = Settings()
    settings.enable_agent_routing = True
    settings.enable_moe_routing = True
    settings.enable_agent_handoff = True
    settings.enable_agent_collaboration = True
    settings.max_delegation_depth = 3
    settings.routing_confidence_threshold = 0.6
    return settings


@pytest.fixture
def mock_celery_task() -> MagicMock:
    """Mock Celery task for background processing.

    Returns:
        A MagicMock configured as a Celery task.
    """
    task = MagicMock()
    task.delay = MagicMock(return_value=MagicMock(id=str(uuid4())))
    task.apply_async = MagicMock(return_value=MagicMock(id=str(uuid4())))
    return task
