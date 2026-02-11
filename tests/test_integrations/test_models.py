"""Unit tests for integration Pydantic models."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from integrations.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformConfig,
    WebhookEvent,
)


class TestIncomingMessage:
    """Tests for IncomingMessage model."""

    def test_valid_message(self) -> None:
        """Test IncomingMessage with all required fields."""
        msg = IncomingMessage(
            platform="telegram",
            external_user_id="123",
            external_channel_id="456",
            text="Hello world",
        )
        assert msg.platform == "telegram"
        assert msg.external_user_id == "123"
        assert msg.text == "Hello world"

    def test_missing_required_field(self) -> None:
        """Test IncomingMessage raises ValidationError when missing required field."""
        with pytest.raises(ValidationError):
            IncomingMessage(
                platform="telegram",
                external_user_id="123",
                text="Hello",
            )  # type: ignore[call-arg]

    def test_optional_fields(self) -> None:
        """Test IncomingMessage with optional fields."""
        msg = IncomingMessage(
            platform="slack",
            external_user_id="U123",
            external_channel_id="C456",
            text="Test",
            username="testuser",
            thread_id="1234.5678",
        )
        assert msg.username == "testuser"
        assert msg.thread_id == "1234.5678"

    def test_timestamp_default(self) -> None:
        """Test IncomingMessage timestamp defaults to current time."""
        msg = IncomingMessage(
            platform="telegram",
            external_user_id="123",
            external_channel_id="456",
            text="hi",
        )
        assert isinstance(msg.timestamp, datetime)

    def test_raw_payload_default(self) -> None:
        """Test IncomingMessage raw_payload defaults to empty dict."""
        msg = IncomingMessage(
            platform="telegram",
            external_user_id="123",
            external_channel_id="456",
            text="hi",
        )
        assert msg.raw_payload == {}

    def test_invalid_platform(self) -> None:
        """Test IncomingMessage rejects invalid platform."""
        with pytest.raises(ValidationError):
            IncomingMessage(
                platform="invalid_platform",
                external_user_id="123",
                external_channel_id="456",
                text="hi",
            )  # type: ignore[arg-type]


class TestOutgoingMessage:
    """Tests for OutgoingMessage model."""

    def test_valid_message(self) -> None:
        """Test OutgoingMessage with required fields."""
        msg = OutgoingMessage(
            platform="telegram",
            channel_id="123",
            text="Response text",
        )
        assert msg.platform == "telegram"
        assert msg.channel_id == "123"
        assert msg.text == "Response text"

    def test_with_formatted_text(self) -> None:
        """Test OutgoingMessage with formatted_text field."""
        msg = OutgoingMessage(
            platform="slack",
            channel_id="C123",
            text="**Bold** text",
            formatted_text="*Bold* text",
        )
        assert msg.formatted_text == "*Bold* text"

    def test_optional_defaults_none(self) -> None:
        """Test OutgoingMessage optional fields default to None."""
        msg = OutgoingMessage(
            platform="telegram",
            channel_id="123",
            text="hi",
        )
        assert msg.thread_id is None
        assert msg.formatted_text is None


class TestPlatformConfig:
    """Tests for PlatformConfig model."""

    def test_valid_config(self) -> None:
        """Test PlatformConfig with credentials."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        assert config.platform == "telegram"
        assert config.credentials["bot_token"] == "123456:ABC-DEF"

    def test_optional_fields(self) -> None:
        """Test PlatformConfig with optional fields."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
            webhook_url="https://example.com/webhook",
            external_bot_id="B123",
        )
        assert config.webhook_url == "https://example.com/webhook"
        assert config.external_bot_id == "B123"

    def test_optional_defaults_none(self) -> None:
        """Test PlatformConfig optional fields default to None."""
        config = PlatformConfig(
            platform="telegram",
            credentials={},
        )
        assert config.webhook_url is None
        assert config.external_bot_id is None


class TestWebhookEvent:
    """Tests for WebhookEvent model."""

    def test_valid_event(self) -> None:
        """Test WebhookEvent with all fields."""
        team_id = uuid4()
        event = WebhookEvent(
            event_id="evt_123",
            event_type="conversation.created",
            team_id=team_id,
            payload={"conversation_id": "conv_123"},
        )
        assert event.event_id == "evt_123"
        assert event.event_type == "conversation.created"
        assert event.team_id == team_id

    def test_timestamp_default(self) -> None:
        """Test WebhookEvent timestamp defaults to current time."""
        event = WebhookEvent(
            event_id="evt_456",
            event_type="message.created",
            team_id=uuid4(),
            payload={},
        )
        assert isinstance(event.timestamp, datetime)

    def test_missing_required_field(self) -> None:
        """Test WebhookEvent raises ValidationError when missing event_id."""
        with pytest.raises(ValidationError):
            WebhookEvent(
                event_type="message.created",
                team_id=uuid4(),
                payload={},
            )  # type: ignore[call-arg]
