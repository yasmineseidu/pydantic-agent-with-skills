"""Platform integration adapters for external messaging platforms.

Supports Telegram, Slack, and extensible to Discord/WhatsApp.
"""

from integrations.events import dispatch_webhook_event
from integrations.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformConfig,
    PlatformStatus,
    PlatformType,
    WebhookEvent,
)
from integrations.registry import default_registry
from integrations.slack.adapter import SlackAdapter
from integrations.telegram.adapter import TelegramAdapter

# Register platform adapters in default registry
default_registry.register("telegram", TelegramAdapter)
default_registry.register("slack", SlackAdapter)

__all__ = [
    "IncomingMessage",
    "OutgoingMessage",
    "PlatformConfig",
    "PlatformStatus",
    "PlatformType",
    "SlackAdapter",
    "TelegramAdapter",
    "WebhookEvent",
    "default_registry",
    "dispatch_webhook_event",
]
