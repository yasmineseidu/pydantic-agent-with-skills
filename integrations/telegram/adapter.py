"""Telegram Bot API adapter implementation."""

import logging
import re
from typing import Optional

from fastapi import Request
from telegram import Bot

from integrations.base import PlatformAdapter
from integrations.models import IncomingMessage, PlatformConfig
from integrations.telegram.webhook import validate_telegram_signature

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """Telegram Bot API adapter.

    Handles Telegram webhook validation, message parsing, response formatting,
    and sending messages via the Telegram Bot API.

    Credentials required in config:
        bot_token: Telegram bot token (e.g., "123456:ABC-DEF...").
    """

    def __init__(self, config: PlatformConfig) -> None:
        """Initialize Telegram adapter.

        Args:
            config: Platform configuration with bot_token in credentials.

        Raises:
            ValueError: If bot_token is missing from credentials.
        """
        super().__init__(config)
        self.bot_token: str = config.credentials.get("bot_token", "")
        if not self.bot_token:
            raise ValueError("Telegram adapter requires 'bot_token' in credentials")
        self.bot: Bot = Bot(token=self.bot_token)

    async def validate_webhook(self, request: Request) -> bool:
        """Validate Telegram webhook HMAC signature.

        Args:
            request: FastAPI Request object with headers and body.

        Returns:
            True if signature is valid, False otherwise.
        """
        body: bytes = await request.body()
        signature: str = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not signature:
            logger.warning("validate_webhook: missing signature header")
            return False
        return validate_telegram_signature(
            bot_token=self.bot_token,
            payload=body,
            signature=signature,
        )

    async def parse_message(self, payload: dict) -> IncomingMessage:
        """Parse Telegram Update to normalized message.

        Args:
            payload: Telegram Update dict from webhook.

        Returns:
            Normalized IncomingMessage.

        Raises:
            ValueError: If payload is missing required fields.
        """
        message: Optional[dict] = payload.get("message")
        if not message:
            raise ValueError("Telegram update missing 'message' field")

        chat: dict = message.get("chat", {})
        from_user: dict = message.get("from", {})
        text: str = message.get("text", "")

        if not chat.get("id"):
            raise ValueError("Telegram message missing 'chat.id'")

        return IncomingMessage(
            platform="telegram",
            external_user_id=str(from_user.get("id", "")),
            external_channel_id=str(chat["id"]),
            text=text,
            username=from_user.get("username") or from_user.get("first_name"),
            thread_id=(
                str(message["message_thread_id"]) if message.get("message_thread_id") else None
            ),
            raw_payload=payload,
        )

    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None:
        """Send formatted response via Telegram Bot API.

        Args:
            channel_id: Telegram chat ID.
            content: Message content (MarkdownV2 formatted).
            thread_id: Optional message thread ID.

        Raises:
            Exception: If Bot API call fails.
        """
        logger.info(f"send_response: chat_id={channel_id}, thread_id={thread_id}")
        await self.bot.send_message(
            chat_id=int(channel_id),
            text=content,
            parse_mode="MarkdownV2",
            message_thread_id=int(thread_id) if thread_id else None,
        )

    def format_response(self, text: str) -> str:
        """Convert markdown to Telegram MarkdownV2 format.

        MarkdownV2 requires escaping special characters:
        _ * [ ] ( ) ~ ` > # + - = | { } . !

        Args:
            text: Markdown text from agent.

        Returns:
            MarkdownV2 formatted text.
        """
        special_chars = r"_*[]()~`>#+=|{}.!-"
        # First, unescape any already-escaped characters to prevent double-escaping
        text = re.sub(r"\\([" + re.escape(special_chars) + r"])", r"\1", text)
        # Then escape all special characters
        return re.sub(r"([" + re.escape(special_chars) + r"])", r"\\\1", text)
