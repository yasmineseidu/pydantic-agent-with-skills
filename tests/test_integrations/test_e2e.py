"""End-to-end integration tests for platform webhook flows."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.webhooks import router


@pytest.fixture()
def app() -> FastAPI:
    """Create test FastAPI app with webhook router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """Create test client for webhook endpoints."""
    return TestClient(app)


class TestTelegramE2EFlow:
    """End-to-end tests for Telegram webhook flow."""

    def test_telegram_full_flow(self, client: TestClient) -> None:
        """Test full Telegram flow: webhook receive, parse, dispatch."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "from": {"id": 42, "username": "testuser"},
                "chat": {"id": 100},
                "text": "Hello bot!",
            },
        }

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch("workers.tasks.platform_tasks.handle_platform_message") as mock_task:
                mock_task.delay = MagicMock()

                response = client.post(
                    "/v1/webhooks/telegram",
                    content=json.dumps(payload).encode(),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
                )

                assert response.status_code == 200
                assert response.json()["status"] == "ok"
                mock_task.delay.assert_called_once()

    def test_telegram_celery_unavailable_still_200(self, client: TestClient) -> None:
        """Test Telegram returns 200 even if Celery dispatch fails."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1},
                "chat": {"id": 1},
                "text": "test",
            },
        }

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch(
                "workers.tasks.platform_tasks.handle_platform_message",
            ) as mock_task:
                mock_task.delay.side_effect = Exception("Celery down")

                response = client.post(
                    "/v1/webhooks/telegram",
                    content=json.dumps(payload).encode(),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
                )
                # Should still return 200 to prevent Telegram retries
                assert response.status_code == 200
                assert response.json()["status"] == "ok"

    def test_telegram_missing_secret_token_returns_401(self, client: TestClient) -> None:
        """Test Telegram rejects requests without secret token header."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = {"update_id": 1}

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/telegram",
                content=json.dumps(payload).encode(),
            )
            assert response.status_code == 401

    def test_telegram_integrations_disabled_returns_404(self, client: TestClient) -> None:
        """Test Telegram returns 404 when integrations feature flag is off."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = False

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/telegram",
                content=json.dumps({"update_id": 1}).encode(),
                headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            )
            assert response.status_code == 404


class TestSlackE2EFlow:
    """End-to-end tests for Slack webhook flow."""

    def test_slack_url_verification_flow(self, client: TestClient) -> None:
        """Test Slack URL verification challenge flow."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = {
            "type": "url_verification",
            "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
            "token": "test_token",
        }

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=json.dumps(payload).encode(),
            )
            assert response.status_code == 200
            data = response.json()
            assert data["challenge"] == payload["challenge"]

    def test_slack_event_callback_flow(self, client: TestClient) -> None:
        """Test Slack event callback full flow with signature validation."""
        signing_secret = "test_signing_secret_e2e"
        timestamp = str(int(time.time()))

        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123ABC",
                "channel": "C456DEF",
                "text": "<@U_BOT> hello world",
                "thread_ts": "1234567890.123456",
            },
            "team_id": "T789GHI",
        }
        body = json.dumps(payload).encode()

        # Generate valid Slack signature
        base_string = f"v0:{timestamp}:".encode() + body
        computed = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed}"

        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = signing_secret

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch("workers.tasks.platform_tasks.handle_platform_message") as mock_task:
                mock_task.delay = MagicMock()

                response = client.post(
                    "/v1/webhooks/slack",
                    content=body,
                    headers={
                        "X-Slack-Request-Timestamp": timestamp,
                        "X-Slack-Signature": signature,
                    },
                )

                assert response.status_code == 200
                assert response.json()["status"] == "ok"
                mock_task.delay.assert_called_once()

    def test_slack_replay_attack_rejected(self, client: TestClient) -> None:
        """Test Slack rejects replay attacks (timestamp > 5 min old)."""
        signing_secret = "test_signing_secret_e2e"
        old_timestamp = str(int(time.time()) - 600)  # 10 min ago

        body = json.dumps({"type": "event_callback", "event": {"type": "message"}}).encode()
        base_string = f"v0:{old_timestamp}:".encode() + body
        computed = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed}"

        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = signing_secret

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=body,
                headers={
                    "X-Slack-Request-Timestamp": old_timestamp,
                    "X-Slack-Signature": signature,
                },
            )
            assert response.status_code == 401

    def test_slack_missing_signature_headers_returns_401(self, client: TestClient) -> None:
        """Test Slack rejects event callbacks without signature headers."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = {
            "type": "event_callback",
            "event": {"type": "message", "user": "U123", "channel": "C456", "text": "hi"},
        }

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=json.dumps(payload).encode(),
            )
            assert response.status_code == 401


class TestAdapterParsingE2E:
    """End-to-end tests for adapter message parsing."""

    @pytest.mark.asyncio
    async def test_telegram_parse_and_format(self) -> None:
        """Test Telegram adapter parse + format round-trip."""
        from integrations.models import PlatformConfig
        from integrations.telegram.adapter import TelegramAdapter

        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )

        with patch("integrations.telegram.adapter.Bot"):
            adapter = TelegramAdapter(config)

        payload = {
            "update_id": 1,
            "message": {
                "from": {"id": 42, "username": "testuser"},
                "chat": {"id": 100},
                "text": "Hello **world**!",
            },
        }

        msg = await adapter.parse_message(payload)
        assert msg.platform == "telegram"
        assert msg.text == "Hello **world**!"
        assert msg.external_user_id == "42"
        assert msg.external_channel_id == "100"
        assert msg.username == "testuser"

        formatted = adapter.format_response("Hello *world*!")
        assert "\\*" in formatted  # Special chars escaped for MarkdownV2

    @pytest.mark.asyncio
    async def test_slack_parse_and_format(self) -> None:
        """Test Slack adapter parse + format round-trip."""
        from integrations.models import PlatformConfig
        from integrations.slack.adapter import SlackAdapter

        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )

        with patch("integrations.slack.adapter.WebClient"):
            adapter = SlackAdapter(config)

        payload = {
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C456",
                "text": "<@U_BOT> hello **world**",
            },
        }

        msg = await adapter.parse_message(payload)
        assert msg.platform == "slack"
        assert "<@U_BOT> hello **world**" in msg.text
        assert msg.external_user_id == "U123"
        assert msg.external_channel_id == "C456"

        formatted = adapter.format_response("Hello **world**")
        assert formatted == "Hello *world*"  # ** -> * (mrkdwn)

    @pytest.mark.asyncio
    async def test_telegram_parse_missing_message_raises(self) -> None:
        """Test Telegram adapter raises on missing message field."""
        from integrations.models import PlatformConfig
        from integrations.telegram.adapter import TelegramAdapter

        config = PlatformConfig(
            platform="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
        )

        with patch("integrations.telegram.adapter.Bot"):
            adapter = TelegramAdapter(config)

        with pytest.raises(ValueError, match="missing 'message' field"):
            await adapter.parse_message({"update_id": 1})

    @pytest.mark.asyncio
    async def test_slack_parse_unsupported_event_raises(self) -> None:
        """Test Slack adapter raises on unsupported event type."""
        from integrations.models import PlatformConfig
        from integrations.slack.adapter import SlackAdapter

        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123", "signing_secret": "abc"},
        )

        with patch("integrations.slack.adapter.WebClient"):
            adapter = SlackAdapter(config)

        with pytest.raises(ValueError, match="Unsupported Slack event type"):
            await adapter.parse_message({"event": {"type": "reaction_added"}})
