"""Slack Events API adapter implementation."""

import logging
from typing import Optional

from fastapi import Request
from slack_sdk import WebClient

from integrations.base import PlatformAdapter
from integrations.models import IncomingMessage, PlatformConfig
from integrations.slack.webhook import validate_slack_signature

logger = logging.getLogger(__name__)


class SlackAdapter(PlatformAdapter):
    """Slack Events API adapter.

    Handles Slack webhook validation (including url_verification challenge),
    message parsing, response formatting to mrkdwn, and sending messages
    via the Slack Web API.

    Credentials required in config:
    - bot_token: Slack bot token (xoxb-...)
    - signing_secret: Slack signing secret for webhook validation
    """

    def __init__(self, config: PlatformConfig) -> None:
        """Initialize Slack adapter.

        Args:
            config: Platform configuration with bot_token and signing_secret.
        """
        super().__init__(config)
        self.bot_token: str = config.credentials.get("bot_token", "")
        self.signing_secret: str = config.credentials.get("signing_secret", "")
        if not self.bot_token:
            raise ValueError("Slack adapter requires 'bot_token' in credentials")
        if not self.signing_secret:
            raise ValueError("Slack adapter requires 'signing_secret' in credentials")
        self.client = WebClient(token=self.bot_token)

    async def validate_webhook(self, request: Request) -> bool:
        """Validate Slack webhook signature.

        Args:
            request: FastAPI Request object with headers and body.

        Returns:
            True if signature is valid, False otherwise.
        """
        body = await request.body()
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not timestamp or not signature:
            logger.warning("validate_webhook: missing timestamp or signature headers")
            return False
        return validate_slack_signature(
            signing_secret=self.signing_secret,
            timestamp=timestamp,
            body=body,
            signature=signature,
        )

    async def parse_message(self, payload: dict) -> IncomingMessage:
        """Parse Slack event to normalized message.

        Handles both @mention events and DM events.

        Args:
            payload: Slack event payload from webhook.

        Returns:
            Normalized IncomingMessage.

        Raises:
            ValueError: If payload is missing required fields.
        """
        event = payload.get("event", {})
        event_type = event.get("type")
        if event_type not in ("app_mention", "message"):
            raise ValueError(f"Unsupported Slack event type: {event_type}")

        user = event.get("user", "")
        channel = event.get("channel", "")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")

        if not channel:
            raise ValueError("Slack event missing 'channel'")

        logger.info(f"parse_message: platform=slack, channel={channel}, event_type={event_type}")

        return IncomingMessage(
            platform="slack",
            external_user_id=user,
            external_channel_id=channel,
            text=text,
            username=None,
            thread_id=thread_ts,
            raw_payload=payload,
        )

    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None:
        """Send formatted response via Slack Web API.

        Args:
            channel_id: Slack channel ID.
            content: Message content (mrkdwn formatted).
            thread_id: Optional thread timestamp to reply in thread.

        Raises:
            Exception: If Web API call fails.
        """
        logger.info(f"send_response: platform=slack, channel={channel_id}")
        self.client.chat_postMessage(
            channel=channel_id,
            text=content,
            thread_ts=thread_id,
            mrkdwn=True,
        )

    def format_response(self, text: str) -> str:
        """Convert markdown to Slack mrkdwn format.

        Slack mrkdwn differences from standard markdown:
        - Bold: *text* (not **text**)

        Args:
            text: Markdown text from agent.

        Returns:
            Slack mrkdwn formatted text.
        """
        formatted = text.replace("**", "*")
        return formatted
