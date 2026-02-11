"""Unit tests for platform Celery tasks and webhook delivery."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from workers.tasks.platform_tasks import (
    _async_deliver_webhook,
    _async_handle_platform_message,
    deliver_webhook,
    handle_platform_message,
    validate_webhook_url,
)


# ---------------------------------------------------------------------------
# Helpers: inline mock factories (test_integrations has no conftest fixtures)
# ---------------------------------------------------------------------------


def _make_mock_session_factory(session: AsyncMock | None = None) -> MagicMock:
    """Build a mock async session factory matching conftest pattern."""
    if session is None:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()

    factory = MagicMock()
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = context
    factory._mock_session = session
    return factory


def _make_mock_settings() -> MagicMock:
    """Build a mock Settings with fields needed by platform tasks."""
    settings = MagicMock()
    settings.llm_api_key = "test-key"
    settings.llm_base_url = "https://openrouter.ai/api/v1"
    settings.llm_model = "anthropic/claude-sonnet-4.5"
    settings.webhook_signing_secret = "test-signing-secret"
    return settings


def _make_mock_connection() -> MagicMock:
    """Build a mock PlatformConnectionORM."""
    conn = MagicMock()
    conn.id = uuid4()
    conn.platform = MagicMock()
    conn.platform.value = "telegram"
    conn.credentials_json = {"token": "fake-token"}
    conn.webhook_url = "https://example.com/webhook"
    conn.external_bot_id = "bot123"
    return conn


def _make_mock_delivery(
    *,
    attempt: int = 1,
    max_attempts: int = 5,
) -> MagicMock:
    """Build a mock WebhookDeliveryLogORM."""
    delivery = MagicMock()
    delivery.id = uuid4()
    delivery.webhook_url = "https://example.com/hook"
    delivery.payload = {"event": "test"}
    delivery.event_type = "agent.message"
    delivery.event_id = "evt-123"
    delivery.attempt = attempt
    delivery.max_attempts = max_attempts
    return delivery


# ===========================================================================
# Task Registration Tests
# ===========================================================================


class TestHandlePlatformMessageTask:
    """Tests for handle_platform_message Celery task registration."""

    def test_task_registered(self) -> None:
        """Task is registered with correct name."""
        assert (
            handle_platform_message.name == "workers.tasks.platform_tasks.handle_platform_message"
        )

    def test_task_has_correct_config(self) -> None:
        """Task has expected retry and timeout configuration."""
        assert handle_platform_message.max_retries == 2
        assert handle_platform_message.soft_time_limit == 120

    def test_task_signature(self) -> None:
        """Task can be called with expected arguments."""
        sig = handle_platform_message.s(
            connection_id="test-uuid",
            payload={"message": {"text": "hello"}},
        )
        assert sig is not None


class TestDeliverWebhookTask:
    """Tests for deliver_webhook Celery task registration."""

    def test_task_registered(self) -> None:
        """Task is registered with correct name."""
        assert deliver_webhook.name == "workers.tasks.platform_tasks.deliver_webhook"

    def test_task_has_correct_config(self) -> None:
        """Task has expected retry and timeout configuration."""
        assert deliver_webhook.max_retries == 4
        assert deliver_webhook.soft_time_limit == 30

    def test_task_signature(self) -> None:
        """Task can be called with expected arguments."""
        sig = deliver_webhook.s(delivery_id="test-uuid")
        assert sig is not None


# ===========================================================================
# Async Platform Message Handler Tests
# ===========================================================================


@pytest.mark.asyncio
class TestAsyncPlatformMessageHandler:
    """Tests for _async_handle_platform_message helper."""

    async def test_connection_not_found(self) -> None:
        """Returns error when connection ID doesn't exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_handle_platform_message(connection_id=str(uuid4()), payload={})

        assert result["status"] == "error"
        assert result["error"] == "connection_not_found"

    async def test_success_returns_platform(self) -> None:
        """Returns success with platform name on happy path."""
        conn = _make_mock_connection()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conn
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_adapter = MagicMock()
        mock_incoming = MagicMock()
        mock_incoming.text = "Hello"
        mock_incoming.external_channel_id = "chan123"
        mock_incoming.thread_id = None
        mock_adapter.parse_message = AsyncMock(return_value=mock_incoming)
        mock_adapter.format_response = MagicMock(return_value="Response text")
        mock_adapter.send_response = AsyncMock()

        mock_registry = MagicMock()
        mock_registry.get_adapter = MagicMock(return_value=mock_adapter)

        mock_http_response = MagicMock()
        mock_http_response.raise_for_status = MagicMock()
        mock_http_response.json.return_value = {"choices": [{"message": {"content": "LLM reply"}}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_http_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch(
                "integrations.registry.default_registry",
                mock_registry,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_handle_platform_message(
                connection_id=str(conn.id), payload={"msg": "hi"}
            )

        assert result["status"] == "success"
        assert result["platform"] == "telegram"
        mock_adapter.send_response.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_connection_id_returned_in_result(self) -> None:
        """Result always includes the connection_id."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        cid = str(uuid4())
        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_handle_platform_message(connection_id=cid, payload={})

        assert result["connection_id"] == cid


# ===========================================================================
# Async Webhook Delivery Tests
# ===========================================================================


@pytest.mark.asyncio
class TestAsyncDeliverWebhook:
    """Tests for _async_deliver_webhook helper."""

    async def test_delivery_not_found(self) -> None:
        """Returns error when delivery ID doesn't exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(uuid4()))

        assert result["status"] == "error"
        assert result["error"] == "not_found"

    async def test_successful_delivery(self) -> None:
        """Returns delivered status on 200 HTTP response."""
        delivery = _make_mock_delivery()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "delivered"
        assert result["http_status"] == 200
        session.commit.assert_awaited_once()

    async def test_http_error_retry(self) -> None:
        """Returns retrying status on non-2xx when under max_attempts."""
        delivery = _make_mock_delivery(attempt=1, max_attempts=5)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "retrying"
        assert result["http_status"] == 500
        assert result["attempt"] == 2

    async def test_http_error_max_attempts_reached(self) -> None:
        """Returns failed status when attempt exceeds max_attempts."""
        delivery = _make_mock_delivery(attempt=5, max_attempts=5)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "failed"
        assert result["http_status"] == 502

    async def test_request_error_retry(self) -> None:
        """Returns retrying status on network error when under max_attempts."""
        import httpx

        delivery = _make_mock_delivery(attempt=1, max_attempts=5)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "retrying"
        assert "Connection refused" in result["error"]
        assert result["attempt"] == 2

    async def test_request_error_max_attempts_fails(self) -> None:
        """Returns failed status on network error when max_attempts exceeded."""
        import httpx

        delivery = _make_mock_delivery(attempt=5, max_attempts=5)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "failed"
        assert "Connection refused" in result["error"]

    async def test_delivery_id_returned_in_result(self) -> None:
        """Result always includes the delivery_id."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        did = str(uuid4())
        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=did)

        assert result["delivery_id"] == did

    async def test_no_signing_secret_fails_delivery(self) -> None:
        """Returns error when webhook_signing_secret is not configured."""
        delivery = _make_mock_delivery()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()
        settings.webhook_signing_secret = None

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert result["error"] == "webhook_signing_secret_not_configured"
        session.commit.assert_awaited_once()

    async def test_empty_signing_secret_fails_delivery(self) -> None:
        """Returns error when webhook_signing_secret is empty string."""
        delivery = _make_mock_delivery()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()
        settings.webhook_signing_secret = ""

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert result["error"] == "webhook_signing_secret_not_configured"

    async def test_whitespace_signing_secret_fails_delivery(self) -> None:
        """Returns error when webhook_signing_secret is whitespace only."""
        delivery = _make_mock_delivery()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()
        settings.webhook_signing_secret = "   "

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert result["error"] == "webhook_signing_secret_not_configured"

    async def test_webhook_signature_sent(self) -> None:
        """Webhook POST includes X-Webhook-Signature header."""
        delivery = _make_mock_delivery()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await _async_deliver_webhook(delivery_id=str(delivery.id))

        # Verify POST was called with signature header
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")
        assert headers["X-Webhook-Event"] == "agent.message"
        assert headers["X-Webhook-Event-Id"] == "evt-123"

    async def test_ssrf_private_ip_blocked(self) -> None:
        """Returns error when webhook URL resolves to private IP."""
        delivery = _make_mock_delivery()
        delivery.webhook_url = "http://192.168.1.1/hook"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert "invalid_webhook_url" in result["error"]

    async def test_ssrf_localhost_blocked(self) -> None:
        """Returns error when webhook URL targets localhost."""
        delivery = _make_mock_delivery()
        delivery.webhook_url = "http://127.0.0.1/hook"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert "invalid_webhook_url" in result["error"]

    async def test_ssrf_ftp_scheme_blocked(self) -> None:
        """Returns error when webhook URL uses non-HTTP scheme."""
        delivery = _make_mock_delivery()
        delivery.webhook_url = "ftp://example.com/hook"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = delivery
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        factory = _make_mock_session_factory(session)
        settings = _make_mock_settings()

        with (
            patch(
                "workers.tasks.platform_tasks.get_task_settings",
                return_value=settings,
            ),
            patch(
                "workers.tasks.platform_tasks.get_task_session_factory",
                return_value=factory,
            ),
        ):
            result = await _async_deliver_webhook(delivery_id=str(delivery.id))

        assert result["status"] == "error"
        assert "invalid_webhook_url" in result["error"]


# ===========================================================================
# URL Validation (SSRF) Tests
# ===========================================================================


class TestValidateWebhookUrl:
    """Tests for validate_webhook_url SSRF prevention."""

    def test_valid_https_url(self) -> None:
        """Accepts valid HTTPS URL."""
        result = validate_webhook_url("https://example.com/webhook")
        assert result is None

    def test_valid_http_url(self) -> None:
        """Accepts valid HTTP URL."""
        result = validate_webhook_url("http://example.com/webhook")
        assert result is None

    def test_rejects_ftp_scheme(self) -> None:
        """Rejects non-HTTP(S) schemes."""
        result = validate_webhook_url("ftp://example.com/file")
        assert result is not None
        assert "invalid scheme" in result

    def test_rejects_file_scheme(self) -> None:
        """Rejects file:// scheme."""
        result = validate_webhook_url("file:///etc/passwd")
        assert result is not None
        assert "invalid scheme" in result

    def test_rejects_loopback(self) -> None:
        """Rejects 127.0.0.1."""
        result = validate_webhook_url("http://127.0.0.1/hook")
        assert result is not None
        assert "blocked" in result

    def test_rejects_private_10_range(self) -> None:
        """Rejects 10.x.x.x private range."""
        result = validate_webhook_url("http://10.0.0.1/hook")
        assert result is not None
        assert "blocked" in result

    def test_rejects_private_192_range(self) -> None:
        """Rejects 192.168.x.x private range."""
        result = validate_webhook_url("http://192.168.1.1/hook")
        assert result is not None
        assert "blocked" in result

    def test_rejects_missing_hostname(self) -> None:
        """Rejects URL with no hostname."""
        result = validate_webhook_url("http:///path")
        assert result is not None
        assert "missing hostname" in result
