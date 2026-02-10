"""Unit tests for workers/utils.py async bridge and database utilities."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from workers import utils


@pytest.mark.unit
class TestRunAsync:
    """Test the async-to-sync bridge function."""

    def test_run_async_basic(self) -> None:
        """run_async should execute a simple coroutine and return its value."""

        async def simple_coro():
            return 42

        result = utils.run_async(simple_coro())
        assert result == 42

    def test_run_async_with_await(self) -> None:
        """run_async should handle coroutines that await other coroutines."""

        async def inner():
            return "hello"

        async def outer():
            return await inner()

        result = utils.run_async(outer())
        assert result == "hello"

    def test_run_async_propagates_errors(self) -> None:
        """run_async should propagate exceptions from the coroutine."""

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            utils.run_async(failing_coro())

    def test_run_async_with_sleep(self) -> None:
        """run_async should handle asyncio.sleep."""

        async def sleeping_coro():
            await asyncio.sleep(0)
            return "awake"

        result = utils.run_async(sleeping_coro())
        assert result == "awake"


@pytest.mark.unit
class TestGetTaskSettings:
    """Test settings loading for worker context."""

    def test_get_task_settings_returns_settings(self, mock_settings: MagicMock) -> None:
        """get_task_settings should return a Settings instance."""
        with patch("workers.utils.get_task_settings", return_value=mock_settings):
            result = utils.get_task_settings()
            assert result.redis_url == "redis://localhost:6379/0"


@pytest.mark.unit
class TestGetTaskEngine:
    """Test engine creation for worker context."""

    def test_engine_raises_without_database_url(self) -> None:
        """get_task_engine should raise ValueError without DATABASE_URL."""
        original_engine = utils._engine
        utils._engine = None

        mock_settings = MagicMock()
        mock_settings.database_url = None

        try:
            with patch("workers.utils.get_task_settings", return_value=mock_settings):
                with pytest.raises(ValueError, match="DATABASE_URL is required"):
                    utils.get_task_engine()
        finally:
            utils._engine = original_engine

    def test_engine_caching(self) -> None:
        """get_task_engine should return cached engine on second call."""
        original_engine = utils._engine
        mock_engine = MagicMock()
        utils._engine = mock_engine

        try:
            result = utils.get_task_engine()
            assert result is mock_engine
        finally:
            utils._engine = original_engine


@pytest.mark.unit
class TestGetTaskSessionFactory:
    """Test session factory creation."""

    def test_session_factory_caching(self) -> None:
        """get_task_session_factory should return cached factory on second call."""
        original_factory = utils._session_factory
        mock_factory = MagicMock()
        utils._session_factory = mock_factory

        try:
            result = utils.get_task_session_factory()
            assert result is mock_factory
        finally:
            utils._session_factory = original_factory
