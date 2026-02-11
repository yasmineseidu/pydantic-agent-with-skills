"""Unit tests for platform integration settings."""

import os
from unittest.mock import patch

from src.settings import load_settings


class TestPlatformIntegrationSettings:
    """Tests for Phase 9 platform integration settings."""

    def test_default_values(self) -> None:
        """Test platform fields default to None when not set."""
        with patch.dict(os.environ, {"LLM_API_KEY": "test_key"}, clear=True):
            settings = load_settings()
            assert settings.telegram_bot_token is None
            assert settings.slack_signing_secret is None
            assert settings.slack_bot_token is None
            assert settings.webhook_signing_secret is None

    def test_load_from_env_vars(self) -> None:
        """Test platform fields load from environment variables."""
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "test_key",
                "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF",
                "SLACK_SIGNING_SECRET": "abc123",
                "SLACK_BOT_TOKEN": "xoxb-123456",
                "WEBHOOK_SIGNING_SECRET": "secret123",
            },
            clear=True,
        ):
            settings = load_settings()
            assert settings.telegram_bot_token == "123456:ABC-DEF"
            assert settings.slack_signing_secret == "abc123"
            assert settings.slack_bot_token == "xoxb-123456"
            assert settings.webhook_signing_secret == "secret123"

    def test_feature_flags_unchanged(self) -> None:
        """Test enable_webhooks and enable_integrations flags still exist."""
        with patch.dict(os.environ, {"LLM_API_KEY": "test_key"}, clear=True):
            settings = load_settings()
            assert hasattr(settings.feature_flags, "enable_webhooks")
            assert hasattr(settings.feature_flags, "enable_integrations")
            assert settings.feature_flags.enable_webhooks is False
            assert settings.feature_flags.enable_integrations is False

    def test_existing_settings_still_work(self) -> None:
        """Test existing settings fields are not broken."""
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "test_key",
                "LLM_MODEL": "anthropic/claude-sonnet-4.5",
            },
            clear=True,
        ):
            settings = load_settings()
            assert settings.llm_api_key == "test_key"
            assert settings.llm_model == "anthropic/claude-sonnet-4.5"
