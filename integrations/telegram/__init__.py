"""Telegram Bot API adapter."""

from integrations.telegram.adapter import TelegramAdapter
from integrations.telegram.webhook import validate_telegram_signature

__all__ = ["TelegramAdapter", "validate_telegram_signature"]
