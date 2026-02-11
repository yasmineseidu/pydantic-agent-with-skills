"""Unit tests for Slack adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.models import PlatformConfig
from integrations.slack.adapter import SlackAdapter


class TestSlackAdapterInit:
    """Tests for SlackAdapter initialization."""

    def test_init_with_valid_config(self) -> None:
        """Test adapter initializes with valid credentials."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )
        adapter = SlackAdapter(config)
        assert adapter.bot_token == "xoxb-123"
        assert adapter.signing_secret == "abc"

    def test_init_missing_bot_token(self) -> None:
        """Test adapter raises ValueError without bot_token."""
        config = PlatformConfig(
            platform="slack",
            credentials={"signing_secret": "abc"},
        )
        with pytest.raises(ValueError, match="bot_token"):
            SlackAdapter(config)

    def test_init_missing_signing_secret(self) -> None:
        """Test adapter raises ValueError without signing_secret."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123"},
        )
        with pytest.raises(ValueError, match="signing_secret"):
            SlackAdapter(config)

    def test_init_creates_web_client(self) -> None:
        """Test adapter creates a WebClient with bot_token."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-test-token", "signing_secret": "sec"},
        )
        adapter = SlackAdapter(config)
        assert adapter.client is not None
        assert adapter.client.token == "xoxb-test-token"

    def test_init_empty_bot_token_raises(self) -> None:
        """Test adapter raises ValueError when bot_token is empty string."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "", "signing_secret": "abc"},
        )
        with pytest.raises(ValueError, match="bot_token"):
            SlackAdapter(config)

    def test_init_empty_signing_secret_raises(self) -> None:
        """Test adapter raises ValueError when signing_secret is empty string."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": ""},
        )
        with pytest.raises(ValueError, match="signing_secret"):
            SlackAdapter(config)


class TestSlackParseMessage:
    """Tests for SlackAdapter.parse_message."""

    @pytest.fixture()
    def adapter(self) -> SlackAdapter:
        """Create adapter for testing."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )
        return SlackAdapter(config)

    @pytest.mark.asyncio
    async def test_parse_app_mention(self, adapter: SlackAdapter) -> None:
        """Test parsing app_mention event."""
        payload = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C456",
                "text": "<@U_BOT> hello",
                "thread_ts": "1234.5678",
            }
        }
        msg = await adapter.parse_message(payload)
        assert msg.platform == "slack"
        assert msg.external_user_id == "U123"
        assert msg.external_channel_id == "C456"
        assert msg.text == "<@U_BOT> hello"
        assert msg.thread_id == "1234.5678"

    @pytest.mark.asyncio
    async def test_parse_message_event(self, adapter: SlackAdapter) -> None:
        """Test parsing DM message event."""
        payload = {
            "event": {
                "type": "message",
                "user": "U789",
                "channel": "D012",
                "text": "Direct message",
            }
        }
        msg = await adapter.parse_message(payload)
        assert msg.platform == "slack"
        assert msg.external_user_id == "U789"
        assert msg.external_channel_id == "D012"
        assert msg.text == "Direct message"

    @pytest.mark.asyncio
    async def test_parse_unsupported_event_type(self, adapter: SlackAdapter) -> None:
        """Test parsing unsupported event type raises ValueError."""
        payload = {"event": {"type": "reaction_added"}}
        with pytest.raises(ValueError, match="Unsupported Slack event type"):
            await adapter.parse_message(payload)

    @pytest.mark.asyncio
    async def test_parse_missing_channel(self, adapter: SlackAdapter) -> None:
        """Test parsing event without channel raises ValueError."""
        payload = {
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "",
                "text": "Test",
            }
        }
        with pytest.raises(ValueError, match="channel"):
            await adapter.parse_message(payload)

    @pytest.mark.asyncio
    async def test_parse_no_thread_ts(self, adapter: SlackAdapter) -> None:
        """Test parsing message without thread_ts."""
        payload = {
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C456",
                "text": "Hello",
            }
        }
        msg = await adapter.parse_message(payload)
        assert msg.thread_id is None

    @pytest.mark.asyncio
    async def test_parse_stores_raw_payload(self, adapter: SlackAdapter) -> None:
        """Test that raw_payload is stored on the IncomingMessage."""
        payload = {
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C456",
                "text": "Hello",
            }
        }
        msg = await adapter.parse_message(payload)
        assert msg.raw_payload == payload

    @pytest.mark.asyncio
    async def test_parse_missing_event_key(self, adapter: SlackAdapter) -> None:
        """Test parsing payload with no event key raises ValueError."""
        payload: dict = {}
        with pytest.raises(ValueError, match="Unsupported Slack event type"):
            await adapter.parse_message(payload)


class TestSlackFormatResponse:
    """Tests for SlackAdapter.format_response."""

    @pytest.fixture()
    def adapter(self) -> SlackAdapter:
        """Create adapter for testing."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )
        return SlackAdapter(config)

    def test_converts_bold(self, adapter: SlackAdapter) -> None:
        """Test **bold** is converted to *bold*."""
        text = "Hello **world**"
        result = adapter.format_response(text)
        assert result == "Hello *world*"

    def test_plain_text_unchanged(self, adapter: SlackAdapter) -> None:
        """Test plain text passes through unchanged."""
        text = "Hello world"
        result = adapter.format_response(text)
        assert result == "Hello world"

    def test_code_unchanged(self, adapter: SlackAdapter) -> None:
        """Test code blocks pass through unchanged."""
        text = "`code` and ```block```"
        result = adapter.format_response(text)
        assert "`code`" in result

    def test_empty_text(self, adapter: SlackAdapter) -> None:
        """Test empty string passes through."""
        result = adapter.format_response("")
        assert result == ""

    def test_multiple_bold_segments(self, adapter: SlackAdapter) -> None:
        """Test multiple **bold** segments are all converted."""
        text = "**first** and **second**"
        result = adapter.format_response(text)
        assert result == "*first* and *second*"


class TestSlackSendResponse:
    """Tests for SlackAdapter.send_response."""

    @pytest.mark.asyncio
    async def test_send_calls_client(self) -> None:
        """Test send_response calls AsyncWebClient.chat_postMessage."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )
        adapter = SlackAdapter(config)
        adapter.client = MagicMock()
        adapter.client.chat_postMessage = AsyncMock()

        await adapter.send_response("C123", "Hello", thread_id="1234.5678")

        adapter.client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="Hello",
            thread_ts="1234.5678",
            mrkdwn=True,
        )

    @pytest.mark.asyncio
    async def test_send_without_thread(self) -> None:
        """Test send_response without thread_id."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )
        adapter = SlackAdapter(config)
        adapter.client = MagicMock()
        adapter.client.chat_postMessage = AsyncMock()

        await adapter.send_response("C123", "Hello")

        adapter.client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="Hello",
            thread_ts=None,
            mrkdwn=True,
        )
