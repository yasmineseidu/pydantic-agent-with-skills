"""Unit tests for workers/tasks/agent_tasks.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from workers.tasks.agent_tasks import _async_scheduled_agent_run, _track_job_failure


@pytest.mark.unit
class TestAsyncScheduledAgentRun:
    """Test _async_scheduled_agent_run async implementation."""

    @pytest.fixture
    def mock_job(self) -> MagicMock:
        """Create a mock ScheduledJobORM with default attributes."""
        job = MagicMock()
        job.id = uuid4()
        job.team_id = uuid4()
        job.agent_id = uuid4()
        job.user_id = uuid4()
        job.name = "Test Job"
        job.message = "Hello agent"
        job.is_active = True
        job.delivery_config = {}
        job.run_count = 0
        job.consecutive_failures = 0
        job.last_run_at = None
        job.last_error = None
        return job

    async def test_job_not_found_returns_not_found(
        self, mock_session_factory: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should return not_found when job does not exist in DB."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _async_scheduled_agent_run(str(uuid4()))

        assert result["status"] == "not_found"

    async def test_inactive_job_returns_inactive(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        mock_job: MagicMock,
    ) -> None:
        """Should return inactive for disabled jobs."""
        mock_job.is_active = False
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _async_scheduled_agent_run(str(mock_job.id))

        assert result["status"] == "inactive"
        assert result["job_id"] == str(mock_job.id)

    async def test_successful_run_returns_success(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        mock_job: MagicMock,
    ) -> None:
        """Should return success with conversation_id after LLM call."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Agent response"}}],
            "usage": {"completion_tokens": 10},
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_scheduled_agent_run(str(mock_job.id))

        assert result["status"] == "success"
        assert result["response_length"] == len("Agent response")
        assert "conversation_id" in result

    async def test_successful_run_increments_run_count(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        mock_job: MagicMock,
    ) -> None:
        """Should increment run_count and reset consecutive_failures on success."""
        mock_job.run_count = 3
        mock_job.consecutive_failures = 2
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"completion_tokens": 5},
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await _async_scheduled_agent_run(str(mock_job.id))

        assert mock_job.run_count == 4
        assert mock_job.consecutive_failures == 0
        assert mock_job.last_run_at is not None

    async def test_successful_run_creates_conversation_and_messages(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        mock_job: MagicMock,
    ) -> None:
        """Should call session.add for conversation and both messages."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Reply"}}],
            "usage": {"completion_tokens": 3},
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await _async_scheduled_agent_run(str(mock_job.id))

        # conversation + user_message + assistant_message = 3 calls to session.add
        assert session.add.call_count == 3
        session.commit.assert_awaited_once()
        session.flush.assert_awaited_once()

    async def test_successful_run_calls_llm_with_correct_payload(
        self,
        mock_session_factory: MagicMock,
        mock_settings: MagicMock,
        mock_job: MagicMock,
    ) -> None:
        """Should send correct model, message, and auth header to LLM."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {},
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.agent_tasks.get_task_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "workers.tasks.agent_tasks.get_task_settings",
                return_value=mock_settings,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await _async_scheduled_agent_run(str(mock_job.id))

        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.call_args
        assert "chat/completions" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["model"] == mock_settings.llm_model
        assert call_kwargs.kwargs["json"]["messages"][0]["content"] == mock_job.message
        assert mock_settings.llm_api_key in call_kwargs.kwargs["headers"]["Authorization"]


@pytest.mark.unit
class TestTrackJobFailure:
    """Test _track_job_failure async implementation."""

    @pytest.fixture
    def mock_job(self) -> MagicMock:
        """Create a mock ScheduledJobORM for failure tracking."""
        job = MagicMock()
        job.id = uuid4()
        job.is_active = True
        job.consecutive_failures = 0
        job.last_error = None
        return job

    async def test_job_not_found_returns_silently(self, mock_session_factory: MagicMock) -> None:
        """Should return without error when job does not exist."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.agent_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            await _track_job_failure(str(uuid4()), "some error")

        session.commit.assert_not_awaited()

    async def test_increments_consecutive_failures(
        self, mock_session_factory: MagicMock, mock_job: MagicMock
    ) -> None:
        """Should increment consecutive_failures and record error."""
        mock_job.consecutive_failures = 2
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.agent_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            await _track_job_failure(str(mock_job.id), "connection timeout")

        assert mock_job.consecutive_failures == 3
        assert mock_job.last_error == "connection timeout"
        assert mock_job.is_active is True
        session.commit.assert_awaited_once()

    async def test_auto_disables_after_5_failures(
        self, mock_session_factory: MagicMock, mock_job: MagicMock
    ) -> None:
        """Should set is_active=False after 5 consecutive failures."""
        mock_job.consecutive_failures = 4
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        with patch(
            "workers.tasks.agent_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            await _track_job_failure(str(mock_job.id), "5th failure")

        assert mock_job.consecutive_failures == 5
        assert mock_job.is_active is False
        session.commit.assert_awaited_once()

    async def test_truncates_long_error_message(
        self, mock_session_factory: MagicMock, mock_job: MagicMock
    ) -> None:
        """Should truncate error messages longer than 500 characters."""
        session = mock_session_factory._mock_session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = mock_result

        long_error = "x" * 1000

        with patch(
            "workers.tasks.agent_tasks.get_task_session_factory",
            return_value=mock_session_factory,
        ):
            await _track_job_failure(str(mock_job.id), long_error)

        assert len(mock_job.last_error) == 500
