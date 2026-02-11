"""Unit tests for webhook router endpoints."""

import hashlib
import hmac
import json
import time
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.routers.webhooks import router


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Create mock async database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture()
def app(mock_db: AsyncMock) -> FastAPI:
    """Create test FastAPI app with webhook router and mocked DB."""
    app = FastAPI()
    app.include_router(router)

    async def override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
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

    def test_returns_200_valid_request(self, client: TestClient, mock_db: AsyncMock) -> None:
        """Test returns 200 for valid request with matching connection."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        # Mock _lookup_connection returning a valid connection
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connection
        mock_db.execute = AsyncMock(return_value=mock_result)

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

    def test_returns_200_even_when_dispatch_fails(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Test returns 200 even when Celery dispatch fails."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True

        # Mock _lookup_connection returning a valid connection
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connection
        mock_db.execute = AsyncMock(return_value=mock_result)

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
        """Test url_verification returns challenge (requires valid signature)."""
        signing_secret = "test_signing_secret"
        timestamp = str(int(time.time()))

        payload = json.dumps(
            {
                "type": "url_verification",
                "challenge": "test_challenge_abc123",
            }
        ).encode()

        base_string = f"v0:{timestamp}:".encode() + payload
        computed = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed}"

        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = signing_secret

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=payload,
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": signature,
                },
            )
            assert response.status_code == 200
            assert response.json()["challenge"] == "test_challenge_abc123"

    def test_url_verification_rejected_without_signature(self, client: TestClient) -> None:
        """Test url_verification is rejected without valid signature headers."""
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
            assert response.status_code == 401

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

    def test_returns_200_valid_event(self, client: TestClient, mock_db: AsyncMock) -> None:
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
                "api_app_id": "A123",
                "team_id": "T123",
            }
        ).encode()

        base_string = f"v0:{timestamp}:".encode() + body
        computed = hmac.new(signing_secret.encode(), base_string, hashlib.sha256).hexdigest()
        signature = f"v0={computed}"

        # Mock _lookup_connection returning a valid connection
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_connection
        mock_db.execute = AsyncMock(return_value=mock_result)

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

    def test_returns_503_no_signing_secret(self, client: TestClient) -> None:
        """Test returns 503 when no signing secret configured (validation impossible)."""
        mock_settings = MagicMock()
        mock_settings.feature_flags.enable_integrations = True
        mock_settings.slack_signing_secret = None

        payload = json.dumps(
            {
                "type": "event_callback",
                "event": {"type": "message"},
                "api_app_id": "A123",
                "team_id": "T123",
            }
        ).encode()

        with patch("src.api.routers.webhooks.load_settings", return_value=mock_settings):
            response = client.post(
                "/v1/webhooks/slack",
                content=payload,
                headers={
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=anything",
                },
            )
            assert response.status_code == 503
