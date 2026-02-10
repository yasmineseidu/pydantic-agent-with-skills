"""Unit tests for workers/tasks/cleanup_tasks.py."""

from unittest.mock import MagicMock, patch

import pytest

from workers.tasks.cleanup_tasks import (
    _async_archive_expired_memories,
    _async_archive_old_conversations,
    _async_close_stale_sessions,
    _async_expire_tokens,
)


@pytest.mark.unit
class TestAsyncExpireTokens:
    """Test _async_expire_tokens async implementation."""

    async def test_returns_expired_count(self, mock_session_factory: MagicMock) -> None:
        """Should return the number of deleted expired tokens."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 5
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_expire_tokens()

        assert result == {"expired_count": 5}
        session.commit.assert_awaited_once()

    async def test_returns_zero_when_no_expired_tokens(
        self, mock_session_factory: MagicMock
    ) -> None:
        """Should return 0 when no tokens are expired."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_expire_tokens()

        assert result == {"expired_count": 0}
        session.commit.assert_awaited_once()


@pytest.mark.unit
class TestAsyncCloseStaleSessions:
    """Test _async_close_stale_sessions async implementation."""

    async def test_returns_idle_count(self, mock_session_factory: MagicMock) -> None:
        """Should return the number of conversations marked idle."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_close_stale_sessions(idle_minutes=30)

        assert result == {"idle_count": 3}
        session.commit.assert_awaited_once()

    async def test_returns_zero_when_no_stale_sessions(
        self, mock_session_factory: MagicMock
    ) -> None:
        """Should return 0 when no sessions are stale."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_close_stale_sessions(idle_minutes=60)

        assert result == {"idle_count": 0}

    async def test_accepts_custom_idle_minutes(self, mock_session_factory: MagicMock) -> None:
        """Should accept different idle_minutes thresholds."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 10
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_close_stale_sessions(idle_minutes=5)

        assert result == {"idle_count": 10}


@pytest.mark.unit
class TestAsyncArchiveOldConversations:
    """Test _async_archive_old_conversations async implementation."""

    async def test_returns_closed_count(self, mock_session_factory: MagicMock) -> None:
        """Should return the number of conversations closed."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 7
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_archive_old_conversations(days=90)

        assert result == {"closed_count": 7}
        session.commit.assert_awaited_once()

    async def test_returns_zero_when_no_old_conversations(
        self, mock_session_factory: MagicMock
    ) -> None:
        """Should return 0 when no conversations qualify for archival."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_archive_old_conversations(days=90)

        assert result == {"closed_count": 0}

    async def test_accepts_custom_days_parameter(self, mock_session_factory: MagicMock) -> None:
        """Should accept different day thresholds."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 15
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_archive_old_conversations(days=30)

        assert result == {"closed_count": 15}


@pytest.mark.unit
class TestAsyncArchiveExpiredMemories:
    """Test _async_archive_expired_memories async implementation."""

    async def test_returns_archived_count(self, mock_session_factory: MagicMock) -> None:
        """Should return the number of memories archived."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 12
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_archive_expired_memories()

        assert result == {"archived_count": 12}
        session.commit.assert_awaited_once()

    async def test_returns_zero_when_no_expired_memories(
        self, mock_session_factory: MagicMock
    ) -> None:
        """Should return 0 when no memories have expired."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.cleanup_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            result = await _async_archive_expired_memories()

        assert result == {"archived_count": 0}
