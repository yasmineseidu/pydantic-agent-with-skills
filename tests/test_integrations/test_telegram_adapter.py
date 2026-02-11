"""Unit tests for Telegram adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.models import PlatformConfig
from integrations.telegram.adapter import TelegramAdapter


class TestTelegramAdapterInit:
    """Tests for TelegramAdapter initialization."""

    def test_init_with_valid_config(self) -> None:
        """Test adapter initializes with valid bot_token."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)
        assert adapter.bot_token == "123456:ABC-DEF"
        assert adapter.config == config

    def test_init_missing_bot_token(self) -> None:
        """Test adapter raises ValueError without bot_token."""
        config = PlatformConfig(
            platform="telegram",
            credentials={},
        )
        with pytest.raises(ValueError, match="bot_token"):
            TelegramAdapter(config)

    def test_init_empty_bot_token(self) -> None:
        """Test adapter raises ValueError with empty bot_token string."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": ""},
        )
        with pytest.raises(ValueError, match="bot_token"):
            TelegramAdapter(config)

    def test_init_creates_bot_instance(self) -> None:
        """Test adapter creates a telegram.Bot instance."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)
        assert adapter.bot is not None


class TestTelegramParseMessage:
    """Tests for TelegramAdapter.parse_message."""

    @pytest.fixture()
    def adapter(self) -> TelegramAdapter:
        """Create adapter for testing."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        return TelegramAdapter(config)

    @pytest.mark.asyncio
    async def test_parse_valid_message(self, adapter: TelegramAdapter) -> None:
        """Test parsing a valid Telegram update."""
        payload = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "from": {"id": 42, "username": "testuser", "first_name": "Test"},
                "chat": {"id": 100},
                "text": "Hello bot",
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.platform == "telegram"
        assert msg.external_user_id == "42"
        assert msg.external_channel_id == "100"
        assert msg.text == "Hello bot"
        assert msg.username == "testuser"

    @pytest.mark.asyncio
    async def test_parse_missing_message(self, adapter: TelegramAdapter) -> None:
        """Test parsing update without message field."""
        with pytest.raises(ValueError, match="missing 'message'"):
            await adapter.parse_message({"update_id": 123})

    @pytest.mark.asyncio
    async def test_parse_missing_chat_id(self, adapter: TelegramAdapter) -> None:
        """Test parsing message without chat.id."""
        payload = {
            "message": {
                "from": {"id": 42},
                "chat": {},
                "text": "Hello",
            },
        }
        with pytest.raises(ValueError, match="chat.id"):
            await adapter.parse_message(payload)

    @pytest.mark.asyncio
    async def test_parse_with_thread_id(self, adapter: TelegramAdapter) -> None:
        """Test parsing message with thread ID."""
        payload = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
                "text": "Reply in thread",
                "message_thread_id": 555,
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.thread_id == "555"

    @pytest.mark.asyncio
    async def test_parse_fallback_to_first_name(self, adapter: TelegramAdapter) -> None:
        """Test username falls back to first_name."""
        payload = {
            "message": {
                "from": {"id": 42, "first_name": "Test"},
                "chat": {"id": 100},
                "text": "Hello",
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.username == "Test"

    @pytest.mark.asyncio
    async def test_parse_stores_raw_payload(self, adapter: TelegramAdapter) -> None:
        """Test raw_payload is stored in parsed message."""
        payload = {
            "update_id": 999,
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
                "text": "Hello",
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.raw_payload == payload

    @pytest.mark.asyncio
    async def test_parse_empty_text(self, adapter: TelegramAdapter) -> None:
        """Test parsing message with no text field defaults to empty string."""
        payload = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.text == ""

    @pytest.mark.asyncio
    async def test_parse_without_thread_id(self, adapter: TelegramAdapter) -> None:
        """Test thread_id is None when message_thread_id is absent."""
        payload = {
            "message": {
                "from": {"id": 42},
                "chat": {"id": 100},
                "text": "Hello",
            },
        }
        msg = await adapter.parse_message(payload)
        assert msg.thread_id is None


class TestTelegramFormatResponse:
    """Tests for TelegramAdapter.format_response."""

    @pytest.fixture()
    def adapter(self) -> TelegramAdapter:
        """Create adapter for testing."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        return TelegramAdapter(config)

    def test_escapes_special_chars(self, adapter: TelegramAdapter) -> None:
        """Test special characters are escaped for MarkdownV2."""
        text = "Hello *world* (test)"
        result = adapter.format_response(text)
        assert "\\*" in result
        assert "\\(" in result
        assert "\\)" in result

    def test_plain_text_unchanged(self, adapter: TelegramAdapter) -> None:
        """Test plain text without special chars passes through."""
        text = "Hello world"
        result = adapter.format_response(text)
        assert result == "Hello world"

    def test_escapes_all_markdownv2_chars(self, adapter: TelegramAdapter) -> None:
        """Test all MarkdownV2 special characters are escaped."""
        for char in r"_*[]()~`>#+-=|{}.!":
            result = adapter.format_response(char)
            assert result == f"\\{char}", f"Failed to escape '{char}'"

    def test_complex_markdown(self, adapter: TelegramAdapter) -> None:
        """Test escaping complex markdown text."""
        text = "**bold** and `code` with [link](url)"
        result = adapter.format_response(text)
        assert "\\\\" not in result  # No double escapes
        assert "\\*\\*bold\\*\\*" in result

    def test_no_double_escape_pre_escaped(self, adapter: TelegramAdapter) -> None:
        """Test pre-escaped input is not double-escaped."""
        text = "Hello \\_ world \\*"
        result = adapter.format_response(text)
        # Should produce single escapes, not \\_ or \\*
        assert result == "Hello \\_ world \\*"
        assert "\\\\_" not in result
        assert "\\\\*" not in result

    def test_mixed_escaped_and_unescaped(self, adapter: TelegramAdapter) -> None:
        """Test mix of pre-escaped and unescaped chars."""
        text = "pre\\-escaped and unescaped!"
        result = adapter.format_response(text)
        assert result == "pre\\-escaped and unescaped\\!"
        assert "\\\\-" not in result


class TestTelegramSendResponse:
    """Tests for TelegramAdapter.send_response."""

    @pytest.mark.asyncio
    async def test_send_calls_bot(self) -> None:
        """Test send_response calls Bot.send_message."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)
        adapter.bot = MagicMock()
        adapter.bot.send_message = AsyncMock()

        await adapter.send_response("100", "Hello", thread_id="555")

        adapter.bot.send_message.assert_called_once_with(
            chat_id=100,
            text="Hello",
            parse_mode="MarkdownV2",
            message_thread_id=555,
        )

    @pytest.mark.asyncio
    async def test_send_without_thread(self) -> None:
        """Test send_response without thread_id."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)
        adapter.bot = MagicMock()
        adapter.bot.send_message = AsyncMock()

        await adapter.send_response("100", "Hello")

        adapter.bot.send_message.assert_called_once_with(
            chat_id=100,
            text="Hello",
            parse_mode="MarkdownV2",
            message_thread_id=None,
        )

    @pytest.mark.asyncio
    async def test_send_converts_channel_id_to_int(self) -> None:
        """Test send_response converts string channel_id to int."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)
        adapter.bot = MagicMock()
        adapter.bot.send_message = AsyncMock()

        await adapter.send_response("999888777", "test")

        call_args = adapter.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 999888777


class TestTelegramValidateWebhook:
    """Tests for TelegramAdapter.validate_webhook."""

    @pytest.mark.asyncio
    async def test_validate_webhook_missing_signature(self) -> None:
        """Test validate_webhook returns False with missing signature header."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"update_id": 123}')
        request.headers = {}

        result = await adapter.validate_webhook(request)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_webhook_valid_signature(self) -> None:
        """Test validate_webhook returns True with valid signature."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)

        payload = b'{"update_id": 123}'

        # Compute valid signature
        import hashlib
        import hmac as hmac_mod

        secret_key = hashlib.sha256(b"123456:ABC-DEF").digest()
        valid_sig = hmac_mod.new(key=secret_key, msg=payload, digestmod=hashlib.sha256).hexdigest()

        request = MagicMock()
        request.body = AsyncMock(return_value=payload)
        request.headers = {"X-Telegram-Bot-Api-Secret-Token": valid_sig}

        result = await adapter.validate_webhook(request)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_webhook_invalid_signature(self) -> None:
        """Test validate_webhook returns False with invalid signature."""
        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )
        adapter = TelegramAdapter(config)

        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"update_id": 123}')
        request.headers = {"X-Telegram-Bot-Api-Secret-Token": "invalidsignature"}

        result = await adapter.validate_webhook(request)
        assert result is False
