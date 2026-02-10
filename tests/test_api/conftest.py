"""Shared fixtures for API router tests."""

import pytest
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from datetime import datetime, timezone

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.app import create_app
from src.api.dependencies import get_db, get_redis_manager, get_settings
from src.auth.jwt import create_access_token
from src.db.models.user import UserORM, TeamORM
from src.settings import load_settings


@pytest.fixture
def test_user_id() -> UUID:
    """Fixed user UUID for testing.

    Returns:
        A fixed UUID to use across tests for consistency.
    """
    return UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def test_team_id() -> UUID:
    """Fixed team UUID for testing.

    Returns:
        A fixed UUID to use across tests for consistency.
    """
    return UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def test_user(test_user_id: UUID) -> UserORM:
    """Mock UserORM for testing.

    Args:
        test_user_id: Fixed user UUID fixture.

    Returns:
        A UserORM instance with test data.
    """
    user = MagicMock(spec=UserORM)
    user.id = test_user_id
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.is_active = True
    user.password_hash = "$2b$12$abcdefghijklmnopqrstuvwxyz123456789"  # Fake bcrypt hash
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


@pytest.fixture
def test_team(test_team_id: UUID, test_user_id: UUID) -> TeamORM:
    """Mock TeamORM for testing.

    Args:
        test_team_id: Fixed team UUID fixture.
        test_user_id: Fixed user UUID fixture (team owner).

    Returns:
        A TeamORM instance with test data.
    """
    team = MagicMock(spec=TeamORM)
    team.id = test_team_id
    team.name = "Test Team"
    team.slug = "test-team"
    team.owner_id = test_user_id
    team.settings = {}
    team.shared_skill_names = []
    team.webhook_url = None
    team.webhook_secret = None
    team.conversation_retention_days = 90
    team.created_at = datetime.now(timezone.utc)
    team.updated_at = datetime.now(timezone.utc)
    return team


@pytest.fixture
def db_session() -> AsyncSession:
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
def auth_headers(test_user_id: UUID, test_team_id: UUID) -> Dict[str, str]:
    """JWT authorization headers for authenticated requests.

    Args:
        test_user_id: Fixed user UUID fixture.
        test_team_id: Fixed team UUID fixture.

    Returns:
        Dictionary with Authorization header containing Bearer token.
    """
    # Patch settings to provide JWT secret key during token creation
    from unittest.mock import patch
    from src.settings import Settings

    test_settings = Settings()
    if not test_settings.jwt_secret_key:
        test_settings.jwt_secret_key = "test-secret-key-for-jwt-testing-only-not-for-production"

    with patch("src.auth.jwt.load_settings", return_value=test_settings):
        access_token = create_access_token(
            user_id=test_user_id, team_id=test_team_id, role="admin"
        )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def app(test_user_id: UUID, test_team_id: UUID, db_session: AsyncSession):
    """FastAPI application instance for testing.

    Creates a FastAPI app with test overrides:
    - Shared mock database session (from db_session fixture)
    - Mock Redis manager (returns None)
    - Test settings with JWT secret key
    - Override get_current_user to return test user

    Args:
        test_user_id: Fixed user UUID fixture.
        test_team_id: Fixed team UUID fixture.
        db_session: Shared mock database session fixture.

    Yields:
        Configured FastAPI application.
    """
    test_app = create_app()

    # Create test settings with JWT secret key
    test_settings = load_settings()
    if not test_settings.jwt_secret_key:
        test_settings.jwt_secret_key = "test-secret-key-for-jwt-testing-only-not-for-production"

    # Override dependencies — use shared db_session so tests can configure it
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_redis_manager():
        return None

    def override_get_settings():
        return test_settings

    def override_load_settings():
        return test_settings

    # Override get_current_user to return test user
    async def override_get_current_user() -> tuple:
        """Override get_current_user for testing - always returns valid test user."""
        from unittest.mock import MagicMock

        mock_user = MagicMock(spec=UserORM)
        mock_user.id = test_user_id
        mock_user.email = "test@example.com"
        mock_user.is_active = True
        return (mock_user, test_team_id)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_redis_manager] = override_get_redis_manager
    test_app.dependency_overrides[get_settings] = override_get_settings

    # Also override load_settings directly (used in get_current_user)
    import src.settings
    import src.auth.dependencies

    test_app.dependency_overrides[src.settings.load_settings] = override_load_settings
    test_app.dependency_overrides[src.auth.dependencies.get_current_user] = override_get_current_user

    yield test_app

    # Clean up overrides
    test_app.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient for making test requests without auth.

    Args:
        app: FastAPI application fixture.

    Yields:
        An AsyncClient bound to the test app.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(app, test_user_id: UUID, test_team_id: UUID) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient with auth headers pre-configured.

    Args:
        app: FastAPI application fixture.
        test_user_id: Fixed user UUID fixture.
        test_team_id: Fixed team UUID fixture.

    Yields:
        An AsyncClient with Authorization header set and override for admin user.
    """
    # Create headers with a dummy token (will be overridden by our mock get_current_user)
    headers = {"Authorization": "Bearer valid-token"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac
