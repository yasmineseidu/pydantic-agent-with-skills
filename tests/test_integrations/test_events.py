"""Unit tests for outbound webhook event dispatcher."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from integrations.events import dispatch_webhook_event


class TestDispatchWebhookEvent:
    """Tests for dispatch_webhook_event function."""

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self) -> None:
        """Test returns None when webhooks feature flag is off."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_webhooks = False
        mock_session = AsyncMock()

        result = await dispatch_webhook_event(
            event_type="test.event",
            payload={"key": "value"},
            team_id=str(uuid4()),
            webhook_url="https://example.com/hook",
            session=mock_session,
            settings=mock_settings,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_creates_delivery_record(self) -> None:
        """Test creates WebhookDeliveryLogORM when enabled."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_webhooks = True
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        with patch("integrations.events.uuid") as mock_uuid_mod:
            mock_uuid_mod.uuid4.return_value = MagicMock(hex="abcdef1234567890extra")
            with patch("workers.tasks.platform_tasks.deliver_webhook") as mock_task:
                mock_task.delay = MagicMock()

                result = await dispatch_webhook_event(
                    event_type="message.created",
                    payload={"msg": "hello"},
                    team_id=str(uuid4()),
                    webhook_url="https://example.com/hook",
                    session=mock_session,
                    settings=mock_settings,
                )

        assert result is not None
        assert result.startswith("evt_")
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_generates_unique_event_id(self) -> None:
        """Test generates event IDs with evt_ prefix."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_webhooks = True
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        with patch("workers.tasks.platform_tasks.deliver_webhook"):
            result = await dispatch_webhook_event(
                event_type="test.event",
                payload={},
                team_id=str(uuid4()),
                webhook_url="https://example.com/hook",
                session=mock_session,
                settings=mock_settings,
            )

        assert result is not None
        assert result.startswith("evt_")
        assert len(result) > 4  # evt_ + some hex chars

    @pytest.mark.asyncio
    async def test_handles_celery_unavailable(self) -> None:
        """Test gracefully handles Celery being unavailable."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_webhooks = True
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_task = MagicMock()
        mock_task.delay.side_effect = Exception("Celery down")

        with patch("integrations.events.logger") as mock_logger:
            with patch(
                "workers.tasks.platform_tasks.deliver_webhook",
                mock_task,
            ):
                # Should NOT raise - graceful degradation
                result = await dispatch_webhook_event(
                    event_type="test.event",
                    payload={},
                    team_id=str(uuid4()),
                    webhook_url="https://example.com/hook",
                    session=mock_session,
                    settings=mock_settings,
                )
                assert result is not None  # Event ID still returned
                mock_logger.warning.assert_called_once()
