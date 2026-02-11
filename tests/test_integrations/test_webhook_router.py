"""Unit tests for webhook router endpoints."""

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
    """Create test client."""
    return TestClient(app)


class TestTelegramWebhookEndpoint:
    """Tests for POST /v1/webhooks/telegram."""

    def test_returns_404_when_disabled(self, client: TestClient) -> None:
        """Test returns 404 when integrations are disabled."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = False

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/telegram",
                content=b'{"update_id": 1}',
                headers={"X-Telegram-Bot-Api-Secret-Token": "test"},
            )
            assert response.status_code == 404

    def test_returns_401_missing_header(self, client: TestClient) -> None:
        """Test returns 401 when secret token header is missing."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/telegram",
                content=b'{"update_id": 1}',
            )
            assert response.status_code == 401

    def test_returns_400_invalid_json(self, client: TestClient) -> None:
        """Test returns 400 for invalid JSON."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/telegram",
                content=b"not json",
                headers={"X-Telegram-Bot-Api-Secret-Token": "test"},
            )
            assert response.status_code == 400

    def test_returns_200_valid_request(self, client: TestClient) -> None:
        """Test returns 200 for valid request."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = json.dumps({"update_id": 1, "message": {"text": "hello"}}).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch("workers.tasks.platform_tasks.handle_platform_message") as mock_task:
                mock_task.delay = MagicMock()
                response = client.post(
                    "/v1/webhooks/telegram",
                    content=payload,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-token"},
                )
                assert response.status_code == 200
                assert response.json()["status"] == "ok"

    def test_returns_200_even_when_dispatch_fails(self, client: TestClient) -> None:
        """Test returns 200 even when Celery dispatch fails."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = json.dumps({"update_id": 2}).encode()

        mock_task = MagicMock()
        mock_task.delay.side_effect = RuntimeError("broker unavailable")

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch.dict(
                "sys.modules",
                {
                    "workers": MagicMock(),
                    "workers.tasks": MagicMock(),
                    "workers.tasks.platform_tasks": MagicMock(handle_platform_message=mock_task),
                },
            ):
                response = client.post(
                    "/v1/webhooks/telegram",
                    content=payload,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-token"},
                )
                # Should still return 200 (prevents Telegram retries)
                assert response.status_code == 200
                assert response.json()["status"] == "ok"


class TestSlackWebhookEndpoint:
    """Tests for POST /v1/webhooks/slack."""

    def test_returns_404_when_disabled(self, client: TestClient) -> None:
        """Test returns 404 when integrations are disabled."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = False

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=b'{"type": "event_callback"}',
            )
            assert response.status_code == 404

    def test_url_verification_challenge(self, client: TestClient) -> None:
        """Test url_verification returns challenge."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = json.dumps(
            {
                "type": "url_verification",
                "challenge": "test_challenge_abc123",
            }
        ).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=payload,
            )
            assert response.status_code == 200
            assert response.json()["challenge"] == "test_challenge_abc123"

    def test_returns_400_invalid_json(self, client: TestClient) -> None:
        """Test returns 400 for invalid JSON."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=b"not json",
            )
            assert response.status_code == 400

    def test_returns_401_missing_headers(self, client: TestClient) -> None:
        """Test returns 401 when signature headers missing."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        payload = json.dumps({"type": "event_callback"}).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=payload,
            )
            assert response.status_code == 401

    def test_returns_200_valid_event(self, client: TestClient) -> None:
        """Test returns 200 for valid event with signature."""
        signing_secret = "test_signing_secret"
        timestamp = str(int(time.time()))
        body = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "user": "U123",
                    "channel": "C456",
                    "text": "hi",
                },
                "team_id": "T123",
            }
        ).encode()

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

    def test_returns_401_invalid_signature(self, client: TestClient) -> None:
        """Test returns 401 for invalid signature."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = "real_secret"

        payload = json.dumps({"type": "event_callback"}).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=payload,
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=invalid_signature",
                },
            )
            assert response.status_code == 401

    def test_returns_200_no_signing_secret(self, client: TestClient) -> None:
        """Test returns 200 when no signing secret configured (skips validation)."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = None

        payload = json.dumps(
            {
                "type": "event_callback",
                "event": {"type": "message"},
                "team_id": "T123",
            }
        ).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            with patch("workers.tasks.platform_tasks.handle_platform_message") as mock_task:
                mock_task.delay = MagicMock()
                response = client.post(
                    "/v1/webhooks/slack",
                    content=payload,
                    headers={
                        "X-Slack-Request-Timestamp": str(int(time.time())),
                        "X-Slack-Signature": "v0=anything",
                    },
                )
                assert response.status_code == 200
                assert response.json()["status"] == "ok"
