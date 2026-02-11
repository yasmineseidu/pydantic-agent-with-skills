"""Abstract base class for platform adapters."""

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import Request

from integrations.models import IncomingMessage, PlatformConfig


class PlatformAdapter(ABC):
    """Base class for messaging platform integrations.

    All platform adapters (Telegram, Slack, etc.) must implement this interface.
    The adapter pattern allows platform-specific logic to be encapsulated while
    providing a consistent interface for the webhook router and worker tasks.
    """

    def __init__(self, config: PlatformConfig) -> None:
        """Initialize adapter with platform-specific configuration.

        Args:
            config: Platform connection configuration with credentials.
        """
        self.config = config

    @abstractmethod
    async def validate_webhook(self, request: Request) -> bool:
        """Validate incoming webhook signature.

        Each platform has its own signature verification scheme (HMAC, etc.).
        This method must use constant-time comparison to prevent timing attacks.

        Args:
            request: FastAPI Request object with headers and body.

        Returns:
            True if signature is valid, False otherwise.
        """
        ...

    @abstractmethod
    async def parse_message(self, payload: dict) -> IncomingMessage:
        """Parse platform-specific webhook payload to normalized message.

        Extracts user ID, channel ID, message text, and metadata from the
        platform's webhook event format.

        Args:
            payload: Raw webhook payload dict from platform.

        Returns:
            Normalized IncomingMessage with extracted fields.

        Raises:
            ValueError: If payload is invalid or missing required fields.
        """
        ...

    @abstractmethod
    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None:
        """Send formatted response back to the platform.

        Uses platform-specific API (Bot.send_message for Telegram,
        WebClient.chat_postMessage for Slack).

        Args:
            channel_id: Platform-specific channel/chat ID.
            content: Message content (already formatted for platform).
            thread_id: Optional thread/reply ID.

        Raises:
            Exception: If API call fails.
        """
        ...

    @abstractmethod
    def format_response(self, text: str) -> str:
        """Convert markdown to platform-specific format.

        Agent output is in markdown. This method converts it to the
        platform's format (MarkdownV2 for Telegram, mrkdwn for Slack).

        Args:
            text: Markdown text from agent.

        Returns:
            Platform-formatted text.
        """
        ...
