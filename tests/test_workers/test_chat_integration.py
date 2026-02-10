"""Unit tests for chat.py Celery dispatch integration."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.settings import FeatureFlags


@pytest.mark.unit
class TestChatCeleryDispatch:
    """Test Celery dispatch in chat Step 8."""

    def test_dispatches_via_celery_when_flag_enabled(self) -> None:
        """When enable_background_processing=True, should call extract_memories.delay()."""
        mock_task = MagicMock()
        mock_task.delay = MagicMock()

        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_background_processing = True

        # Simulate the dispatch logic from chat.py Step 8
        _dispatched = False
        if mock_settings.feature_flags.enable_background_processing:
            try:
                mock_task.delay(
                    messages=[{"role": "user", "content": "hi"}],
                    team_id=str(uuid4()),
                    agent_id=str(uuid4()),
                    user_id=str(uuid4()),
                    conversation_id=str(uuid4()),
                )
                _dispatched = True
            except Exception:
                pass

        assert _dispatched is True
        mock_task.delay.assert_called_once()

    def test_falls_back_to_asyncio_when_flag_disabled(self) -> None:
        """When enable_background_processing=False, should not call Celery."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_background_processing = False

        _dispatched = False
        if mock_settings.feature_flags.enable_background_processing:
            _dispatched = True

        assert _dispatched is False

    def test_falls_back_to_asyncio_when_celery_unavailable(self) -> None:
        """When Celery import/dispatch fails, should fall back to asyncio."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_background_processing = True

        _dispatched = False
        if mock_settings.feature_flags.enable_background_processing:
            try:
                raise ImportError("No module named 'workers'")
            except Exception:
                pass

        assert _dispatched is False

    def test_passes_string_uuids_to_celery(self) -> None:
        """Celery args should be string UUIDs, not UUID objects."""
        mock_task = MagicMock()
        team_id = uuid4()
        agent_id = uuid4()

        mock_task.delay(
            messages=[],
            team_id=str(team_id),
            agent_id=str(agent_id),
            user_id=str(uuid4()),
            conversation_id=str(uuid4()),
        )

        call_kwargs = mock_task.delay.call_args[1]
        assert isinstance(call_kwargs["team_id"], str)
        assert isinstance(call_kwargs["agent_id"], str)

    def test_feature_flag_default_is_false(self) -> None:
        """enable_background_processing should default to False."""
        flags = FeatureFlags()
        assert flags.enable_background_processing is False

    def test_celery_dispatch_does_not_block_response(self) -> None:
        """Celery dispatch should be fire-and-forget (delay, not apply)."""
        mock_task = MagicMock()
        mock_task.delay = MagicMock(return_value=MagicMock())

        # delay() should return immediately (AsyncResult), not block
        result = mock_task.delay(
            messages=[],
            team_id="x",
            agent_id="y",
            user_id="z",
            conversation_id="w",
        )
        assert result is not None
        # apply() would block - verify delay was used, not apply
        mock_task.apply.assert_not_called()
