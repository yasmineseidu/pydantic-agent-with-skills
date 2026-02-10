"""Comprehensive tests for agents CRUD endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class MockAgentORM:
    """Mock AgentORM for testing."""

    def __init__(
        self,
        agent_id: UUID,
        team_id: UUID,
        name: str = "Test Agent",
        slug: str = "test-agent",
        tagline: str = "Test agent for testing",
        avatar_emoji: str = "",
        personality: dict | None = None,
        shared_skill_names: list | None = None,
        custom_skill_names: list | None = None,
        disabled_skill_names: list | None = None,
        model_config_json: dict | None = None,
        memory_config: dict | None = None,
        boundaries: dict | None = None,
        status: str = "draft",
        created_by: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        """Initialize mock agent."""
        self.id = agent_id
        self.team_id = team_id
        self.name = name
        self.slug = slug
        self.tagline = tagline
        self.avatar_emoji = avatar_emoji
        self.personality = personality or {}
        self.shared_skill_names = shared_skill_names or []
        self.custom_skill_names = custom_skill_names or []
        self.disabled_skill_names = disabled_skill_names or []
        self.model_config_json = model_config_json or {}
        self.memory_config = memory_config or {}
        self.boundaries = boundaries or {}
        self.status = status
        self.created_by = created_by
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)


@pytest.fixture
def mock_agent_orm(test_team_id: UUID, test_user_id: UUID) -> MockAgentORM:
    """Create a mock agent for testing."""
    return MockAgentORM(
        agent_id=UUID("11111111-1111-1111-1111-111111111111"),
        team_id=test_team_id,
        name="Test Agent",
        slug="test-agent",
        status="draft",
        created_by=test_user_id,
    )


def _setup_require_role_override(app, db_session):
    """Add AsyncSession override so require_role's Depends() resolves.

    The require_role dependency internally declares
    ``session: AsyncSession = Depends()`` which causes FastAPI to try
    instantiating AsyncSession directly, exposing its __init__ params
    (bind, binds, kw, etc.) as required query fields and returning 422.

    This override makes ``Depends()`` for AsyncSession resolve to the
    shared mock db_session fixture.

    Args:
        app: FastAPI application instance.
        db_session: Mock AsyncSession from conftest fixture.
    """
    app.dependency_overrides[AsyncSession] = lambda: db_session


class TestListAgents:
    """Tests for GET /v1/agents endpoint."""

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, auth_client, db_session) -> None:
        """List agents returns empty list when no agents exist."""
        # Mock count query
        count_mock = MagicMock()
        count_mock.scalar_one = MagicMock(return_value=0)

        # Mock agents query (empty)
        agents_query_mock = MagicMock()
        agents_query_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        # Mock session.execute to return appropriate mock based on call order
        db_session.execute = AsyncMock(side_effect=[count_mock, agents_query_mock])

        response = await auth_client.get("/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_agents_returns_paginated_response(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """List agents returns agents in paginated response."""
        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            name="Agent 1",
            slug="agent-1",
            created_by=test_user_id,
        )

        # Mock count query
        count_mock = MagicMock()
        count_mock.scalar_one = MagicMock(return_value=1)

        # Mock agents query
        agents_query_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[agent])
        agents_query_mock.scalars = MagicMock(return_value=scalars_mock)

        db_session.execute = AsyncMock(side_effect=[count_mock, agents_query_mock])

        response = await auth_client.get("/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Agent 1"

    @pytest.mark.asyncio
    async def test_list_agents_respects_limit_and_offset(self, auth_client, db_session) -> None:
        """List agents respects limit and offset pagination parameters."""
        # Mock count query
        count_mock = MagicMock()
        count_mock.scalar_one = MagicMock(return_value=50)

        # Mock agents query
        agents_query_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        agents_query_mock.scalars = MagicMock(return_value=scalars_mock)

        db_session.execute = AsyncMock(side_effect=[count_mock, agents_query_mock])

        response = await auth_client.get("/v1/agents?limit=10&offset=5")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5
        assert data["has_more"] is True  # 5 + 10 < 50

    @pytest.mark.asyncio
    async def test_list_agents_with_status_filter(
        self, auth_client, db_session, test_team_id
    ) -> None:
        """List agents filters by status parameter."""
        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            status="active",
        )

        # Mock count query
        count_mock = MagicMock()
        count_mock.scalar_one = MagicMock(return_value=1)

        # Mock agents query
        agents_query_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[agent])
        agents_query_mock.scalars = MagicMock(return_value=scalars_mock)

        db_session.execute = AsyncMock(side_effect=[count_mock, agents_query_mock])

        response = await auth_client.get("/v1/agents?status=active")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_agents_without_auth_returns_401(self, app, client) -> None:
        """List agents without authentication returns 401."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)
        response = await client.get("/v1/agents")
        assert response.status_code in [401, 422]


class TestCreateAgent:
    """Tests for POST /v1/agents endpoint."""

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_create_agent_success_returns_201(
        self, mock_perm, auth_client, app, db_session, test_team_id, test_user_id
    ) -> None:
        """Create agent with valid data returns 201 Created."""
        _setup_require_role_override(app, db_session)

        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            name="New Agent",
            slug="new-agent",
            status="draft",
            created_by=test_user_id,
        )

        # Mock existing check (no duplicate)
        existing_mock = MagicMock()
        existing_mock.scalar_one_or_none = MagicMock(return_value=None)

        db_session.execute = AsyncMock(return_value=existing_mock)
        db_session.add = MagicMock()
        db_session.commit = AsyncMock()

        # refresh must populate the ORM object created in the route with real values
        async def mock_refresh(obj):
            obj.id = agent.id
            obj.team_id = agent.team_id
            obj.name = agent.name
            obj.slug = agent.slug
            obj.tagline = agent.tagline
            obj.avatar_emoji = agent.avatar_emoji
            obj.personality = agent.personality
            obj.shared_skill_names = agent.shared_skill_names
            obj.custom_skill_names = agent.custom_skill_names
            obj.disabled_skill_names = agent.disabled_skill_names
            obj.model_config_json = agent.model_config_json
            obj.memory_config = agent.memory_config
            obj.boundaries = agent.boundaries
            obj.status = agent.status
            obj.created_by = agent.created_by
            obj.created_at = agent.created_at
            obj.updated_at = agent.updated_at

        db_session.refresh = AsyncMock(side_effect=mock_refresh)

        response = await auth_client.post(
            "/v1/agents",
            json={
                "name": "New Agent",
                "slug": "new-agent",
                "tagline": "A new agent",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Agent"
        assert data["slug"] == "new-agent"
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_create_agent_duplicate_slug_returns_409(
        self, mock_perm, auth_client, app, db_session, test_team_id
    ) -> None:
        """Create agent with duplicate slug in team returns 409 Conflict."""
        _setup_require_role_override(app, db_session)

        existing_agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            slug="test-agent",
        )

        # Mock existing check (found duplicate)
        existing_mock = MagicMock()
        existing_mock.scalar_one_or_none = MagicMock(return_value=existing_agent)

        db_session.execute = AsyncMock(return_value=existing_mock)

        response = await auth_client.post(
            "/v1/agents",
            json={"name": "Test Agent", "slug": "test-agent"},
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_agent_invalid_slug_format_returns_422(self, auth_client) -> None:
        """Create agent with invalid slug format returns 422 Unprocessable Entity."""
        response = await auth_client.post(
            "/v1/agents",
            json={
                "name": "Test Agent",
                "slug": "Invalid_Slug!",  # Invalid: uppercase, underscore, special char
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch(
        "src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=False
    )
    async def test_create_agent_requires_admin_role(
        self, mock_perm, app, client, db_session
    ) -> None:
        """Create agent requires admin role (member role returns 403)."""
        _setup_require_role_override(app, db_session)

        response = await client.post(
            "/v1/agents",
            json={"name": "Test Agent", "slug": "test-agent"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_agent_without_auth_returns_401(self, app, client) -> None:
        """Create agent without authentication returns 401."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)
        response = await client.post(
            "/v1/agents",
            json={"name": "Test Agent", "slug": "test-agent"},
        )

        assert response.status_code in [401, 422]


class TestGetAgent:
    """Tests for GET /v1/agents/{slug} endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_found_returns_200(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Get agent by slug returns 200 OK when found."""
        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            slug="test-agent",
            name="Test Agent",
            created_by=test_user_id,
        )

        # Mock query
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=agent)

        db_session.execute = AsyncMock(return_value=query_mock)

        response = await auth_client.get("/v1/agents/test-agent")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "test-agent"
        assert data["name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_get_agent_not_found_returns_404(self, auth_client, db_session) -> None:
        """Get agent by slug returns 404 Not Found when not found."""
        # Mock query (no agent found)
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=None)

        db_session.execute = AsyncMock(return_value=query_mock)

        response = await auth_client.get("/v1/agents/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_agent_without_auth_returns_401(self, app, client) -> None:
        """Get agent without authentication returns 401."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)
        response = await client.get("/v1/agents/test-agent")
        assert response.status_code in [401, 422]


class TestUpdateAgent:
    """Tests for PATCH /v1/agents/{slug} endpoint."""

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_update_agent_success_returns_200(
        self, mock_perm, auth_client, app, db_session, test_team_id, test_user_id
    ) -> None:
        """Update agent with partial data returns 200 OK."""
        _setup_require_role_override(app, db_session)

        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            name="Original Name",
            slug="test-agent",
            status="draft",
            created_by=test_user_id,
        )

        # Mock query
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=agent)

        db_session.execute = AsyncMock(return_value=query_mock)
        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        response = await auth_client.patch(
            "/v1/agents/test-agent",
            json={"name": "Updated Name", "status": "active"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_update_agent_partial_update_only_provided_fields(
        self, mock_perm, auth_client, app, db_session, test_team_id
    ) -> None:
        """Update agent with only some fields updates only those fields."""
        _setup_require_role_override(app, db_session)

        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            name="Original",
            tagline="Original tagline",
            status="draft",
        )

        # Mock query
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=agent)

        db_session.execute = AsyncMock(return_value=query_mock)
        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        response = await auth_client.patch(
            "/v1/agents/test-agent",
            json={"tagline": "Updated tagline"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tagline"] == "Updated tagline"

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_update_agent_not_found_returns_404(
        self, mock_perm, auth_client, app, db_session
    ) -> None:
        """Update nonexistent agent returns 404 Not Found."""
        _setup_require_role_override(app, db_session)

        # Mock query (no agent found)
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=None)

        db_session.execute = AsyncMock(return_value=query_mock)

        response = await auth_client.patch(
            "/v1/agents/nonexistent",
            json={"name": "Updated"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=False
    )
    async def test_update_agent_requires_admin_role(
        self, mock_perm, app, client, db_session
    ) -> None:
        """Update agent requires admin role (member role returns 403)."""
        _setup_require_role_override(app, db_session)

        response = await client.patch(
            "/v1/agents/test-agent",
            json={"name": "Updated"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_agent_without_auth_returns_401(self, app, client) -> None:
        """Update agent without authentication returns 401."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)
        response = await client.patch(
            "/v1/agents/test-agent",
            json={"name": "Updated"},
        )
        assert response.status_code in [401, 422]


class TestDeleteAgent:
    """Tests for DELETE /v1/agents/{slug} endpoint."""

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_delete_agent_soft_delete_returns_204(
        self, mock_perm, auth_client, app, db_session, test_team_id, test_user_id
    ) -> None:
        """Delete agent soft-deletes (sets status to archived) returns 204 No Content."""
        _setup_require_role_override(app, db_session)

        agent = MockAgentORM(
            agent_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            slug="test-agent",
            status="active",
            created_by=test_user_id,
        )

        # Mock query
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=agent)

        db_session.execute = AsyncMock(return_value=query_mock)
        db_session.commit = AsyncMock()

        response = await auth_client.delete("/v1/agents/test-agent")

        assert response.status_code == 204
        assert agent.status == "archived"

    @pytest.mark.asyncio
    @patch("src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=True)
    async def test_delete_agent_not_found_returns_404(
        self, mock_perm, auth_client, app, db_session
    ) -> None:
        """Delete nonexistent agent returns 404 Not Found."""
        _setup_require_role_override(app, db_session)

        # Mock query (no agent found)
        query_mock = MagicMock()
        query_mock.scalar_one_or_none = MagicMock(return_value=None)

        db_session.execute = AsyncMock(return_value=query_mock)

        response = await auth_client.delete("/v1/agents/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @patch(
        "src.auth.dependencies.check_team_permission", new_callable=AsyncMock, return_value=False
    )
    async def test_delete_agent_requires_admin_role(
        self, mock_perm, app, client, db_session
    ) -> None:
        """Delete agent requires admin role (member role returns 403)."""
        _setup_require_role_override(app, db_session)

        response = await client.delete("/v1/agents/test-agent")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_agent_without_auth_returns_401(self, app, client) -> None:
        """Delete agent without authentication returns 401."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)
        response = await client.delete("/v1/agents/test-agent")
        assert response.status_code in [401, 422]
