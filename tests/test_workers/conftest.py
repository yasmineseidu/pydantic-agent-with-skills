"""Shared fixtures for background worker tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def celery_eager():
    """Configure Celery for eager (synchronous) task execution in tests.

    Sets CELERY_ALWAYS_EAGER=True so tasks execute inline without a broker.

    Yields:
        None. Tasks run synchronously during this fixture's scope.
    """
    with patch.dict("os.environ", {"CELERY_ALWAYS_EAGER": "true"}):
        yield


@pytest.fixture
def mock_session_factory():
    """Mock async session factory for testing database operations.

    Returns:
        A callable that returns an AsyncMock session with commit/rollback/close
        methods and context manager support.
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()

    factory = MagicMock()
    # Support `async with factory() as session:` pattern
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = context

    factory._mock_session = session  # expose for assertions
    return factory


@pytest.fixture
def mock_settings():
    """Mock Settings with all fields needed by worker tasks.

    Returns:
        MagicMock with redis_url, database_url, llm_api_key, llm_base_url,
        llm_model, and feature_flags attributes.
    """
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379/0"
    settings.database_url = "postgresql+asyncpg://test:test@localhost/test"
    settings.llm_api_key = "test-key"
    settings.llm_base_url = "https://openrouter.ai/api/v1"
    settings.llm_model = "anthropic/claude-sonnet-4.5"
    settings.embedding_model = "text-embedding-3-small"
    settings.embedding_api_key = "test-embedding-key"
    settings.embedding_dimensions = 1536
    settings.feature_flags = MagicMock()
    settings.feature_flags.enable_background_processing = True
    settings.feature_flags.enable_memory = True
    settings.feature_flags.enable_redis_cache = True
    return settings


@pytest.fixture
def mock_hot_cache():
    """Mock HotMemoryCache for testing cache invalidation.

    Returns:
        AsyncMock with invalidate and get methods.
    """
    cache = AsyncMock()
    cache.invalidate = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache
