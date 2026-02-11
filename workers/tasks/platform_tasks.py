"""Celery tasks for platform integration message handling and webhook delivery."""

import ipaddress
import logging
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from celery import shared_task

from workers.utils import get_task_session_factory, get_task_settings, run_async

logger = logging.getLogger(__name__)


def validate_webhook_url(url: str) -> str | None:
    """Validate a webhook URL is safe to POST to (SSRF prevention).

    Blocks private IPs, loopback, link-local, cloud metadata endpoints,
    and non-HTTP(S) schemes.

    Args:
        url: The webhook URL to validate.

    Returns:
        None if valid, error message string if invalid.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid URL"

    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        return f"invalid scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return "missing hostname"

    # Resolve hostname to IP and check for private ranges
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return f"cannot resolve hostname: {hostname}"

    for _, _, _, _, sockaddr in resolved_ips:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"blocked private/reserved IP: {ip_str}"

        # Block cloud metadata endpoints explicitly
        if ip_str in ("169.254.169.254", "fd00:ec2::254"):
            return f"blocked metadata endpoint: {ip_str}"

    return None


@shared_task(
    name="workers.tasks.platform_tasks.handle_platform_message",
    bind=True,
    max_retries=2,
    soft_time_limit=120,
    acks_late=True,
)
def handle_platform_message(
    self,  # type: ignore[no-untyped-def]
    connection_id: str,
    payload: dict,
) -> dict[str, Any]:
    """Process an incoming platform message through the agent.

    Loads the platform connection, parses the message via adapter,
    calls the LLM, formats the response, and sends it back.

    Args:
        self: Celery task instance (for retries).
        connection_id: PlatformConnectionORM UUID as string.
        payload: Raw webhook payload dict.

    Returns:
        Dict with processing result: connection_id, status, platform.
    """
    logger.info("handle_platform_message_started: connection_id=%s", connection_id)

    try:
        result = run_async(
            _async_handle_platform_message(connection_id=connection_id, payload=payload)
        )
        logger.info(
            "handle_platform_message_completed: connection_id=%s, result=%s",
            connection_id,
            result,
        )
        return result
    except Exception as exc:
        logger.warning(
            "handle_platform_message_failed: connection_id=%s, error=%s, retry=%d/%d",
            connection_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


async def _async_handle_platform_message(connection_id: str, payload: dict) -> dict[str, Any]:
    """Async implementation of platform message handling.

    Args:
        connection_id: PlatformConnectionORM UUID as string.
        payload: Raw webhook payload dict.

    Returns:
        Processing result dict.
    """
    from uuid import UUID

    import httpx
    from sqlalchemy import select, update

    from integrations.models import PlatformConfig
    from integrations.registry import default_registry
    from src.db.models.platform import PlatformConnectionORM

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    async with session_factory() as session:
        # Load platform connection
        stmt = select(PlatformConnectionORM).where(PlatformConnectionORM.id == UUID(connection_id))
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if not connection:
            logger.error(
                "handle_platform_message_connection_not_found: connection_id=%s",
                connection_id,
            )
            return {
                "connection_id": connection_id,
                "status": "error",
                "error": "connection_not_found",
            }

        # Build adapter config
        config = PlatformConfig(
            platform=connection.platform.value,
            credentials=connection.credentials_json,
            webhook_url=connection.webhook_url,
            external_bot_id=connection.external_bot_id,
        )

        # Get adapter from registry
        adapter = default_registry.get_adapter(connection.platform.value, config)

        # Parse incoming message
        incoming = await adapter.parse_message(payload)

        # Call LLM via httpx (simple completion)
        base_url = settings.llm_base_url or "https://openrouter.ai/api/v1"
        async with httpx.AsyncClient(timeout=60.0) as client:
            llm_response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "user", "content": incoming.text},
                    ],
                    "max_tokens": 1024,
                },
            )
            llm_response.raise_for_status()
            llm_data = llm_response.json()

        # Extract response text
        response_text = llm_data["choices"][0]["message"]["content"]

        # Format for platform
        formatted = adapter.format_response(response_text)

        # Send response back
        await adapter.send_response(
            channel_id=incoming.external_channel_id,
            content=formatted,
            thread_id=incoming.thread_id,
        )

        # Update last_event_at
        await session.execute(
            update(PlatformConnectionORM)
            .where(PlatformConnectionORM.id == UUID(connection_id))
            .values(last_event_at=datetime.now(timezone.utc))
        )
        await session.commit()

        return {
            "connection_id": connection_id,
            "status": "success",
            "platform": connection.platform.value,
        }


@shared_task(
    name="workers.tasks.platform_tasks.deliver_webhook",
    bind=True,
    max_retries=4,
    soft_time_limit=30,
    acks_late=True,
)
def deliver_webhook(
    self,  # type: ignore[no-untyped-def]
    delivery_id: str,
) -> dict[str, Any]:
    """Deliver an outbound webhook with retry logic.

    Loads the delivery log, signs the payload with HMAC, POSTs to webhook URL.
    On success: sets delivered_at. On failure: increments attempt, schedules retry.
    After max_attempts: sets failed_at.

    Args:
        self: Celery task instance (for retries).
        delivery_id: WebhookDeliveryLogORM UUID as string.

    Returns:
        Dict with delivery result: delivery_id, status, http_status.
    """
    logger.info("deliver_webhook_started: delivery_id=%s", delivery_id)

    try:
        result = run_async(_async_deliver_webhook(delivery_id=delivery_id))
        logger.info(
            "deliver_webhook_completed: delivery_id=%s, result=%s",
            delivery_id,
            result,
        )
        return result
    except Exception as exc:
        logger.warning(
            "deliver_webhook_failed: delivery_id=%s, error=%s, retry=%d/%d",
            delivery_id,
            str(exc),
            self.request.retries,
            self.max_retries,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


async def _async_deliver_webhook(delivery_id: str) -> dict[str, Any]:
    """Async implementation of webhook delivery.

    Args:
        delivery_id: WebhookDeliveryLogORM UUID as string.

    Returns:
        Delivery result dict.
    """
    import hashlib
    import hmac
    import json
    from datetime import timedelta
    from uuid import UUID

    import httpx
    from sqlalchemy import select, update

    from src.db.models.platform import WebhookDeliveryLogORM

    settings = get_task_settings()
    session_factory = get_task_session_factory()

    async with session_factory() as session:
        # Load delivery log
        stmt = select(WebhookDeliveryLogORM).where(WebhookDeliveryLogORM.id == UUID(delivery_id))
        result = await session.execute(stmt)
        delivery = result.scalar_one_or_none()

        if not delivery:
            logger.error("deliver_webhook_not_found: delivery_id=%s", delivery_id)
            return {"delivery_id": delivery_id, "status": "error", "error": "not_found"}

        # SSRF prevention: validate webhook URL before POSTing
        url_error = validate_webhook_url(delivery.webhook_url)
        if url_error:
            logger.error(
                "deliver_webhook_ssrf_blocked: delivery_id=%s, url=%s, reason=%s",
                delivery_id,
                delivery.webhook_url[:100],
                url_error,
            )
            await session.execute(
                update(WebhookDeliveryLogORM)
                .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                .values(
                    failed_at=datetime.now(timezone.utc),
                    response_body=f"URL validation failed: {url_error}",
                )
            )
            await session.commit()
            return {
                "delivery_id": delivery_id,
                "status": "error",
                "error": f"invalid_webhook_url: {url_error}",
            }

        # Sign payload with HMAC-SHA256
        payload_bytes = json.dumps(delivery.payload).encode("utf-8")
        signing_secret = (settings.webhook_signing_secret or "").strip()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Webhook-Event": delivery.event_type,
            "X-Webhook-Event-Id": delivery.event_id,
        }

        if not signing_secret:
            logger.error(
                "deliver_webhook_no_signing_secret: delivery_id=%s, "
                "cannot sign payload without webhook_signing_secret",
                delivery_id,
            )
            await session.execute(
                update(WebhookDeliveryLogORM)
                .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                .values(
                    failed_at=datetime.now(timezone.utc),
                    response_body="webhook_signing_secret not configured",
                )
            )
            await session.commit()
            return {
                "delivery_id": delivery_id,
                "status": "error",
                "error": "webhook_signing_secret_not_configured",
            }

        signature = hmac.new(
            key=signing_secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

        # POST to webhook URL
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    delivery.webhook_url,
                    content=payload_bytes,
                    headers=headers,
                )

            http_status = response.status_code
            response_body = response.text[:1000]  # Truncate

            if 200 <= http_status < 300:
                # Success
                await session.execute(
                    update(WebhookDeliveryLogORM)
                    .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                    .values(
                        http_status=http_status,
                        response_body=response_body,
                        delivered_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
                return {
                    "delivery_id": delivery_id,
                    "status": "delivered",
                    "http_status": http_status,
                }
            else:
                # HTTP error - retry or fail
                new_attempt = delivery.attempt + 1
                if new_attempt > delivery.max_attempts:
                    await session.execute(
                        update(WebhookDeliveryLogORM)
                        .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                        .values(
                            http_status=http_status,
                            response_body=response_body,
                            failed_at=datetime.now(timezone.utc),
                            attempt=new_attempt,
                        )
                    )
                    await session.commit()
                    return {
                        "delivery_id": delivery_id,
                        "status": "failed",
                        "http_status": http_status,
                    }

                # Schedule retry with exponential backoff
                backoff = timedelta(minutes=2**new_attempt)
                await session.execute(
                    update(WebhookDeliveryLogORM)
                    .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                    .values(
                        http_status=http_status,
                        response_body=response_body,
                        attempt=new_attempt,
                        next_retry_at=datetime.now(timezone.utc) + backoff,
                    )
                )
                await session.commit()
                return {
                    "delivery_id": delivery_id,
                    "status": "retrying",
                    "http_status": http_status,
                    "attempt": new_attempt,
                }

        except httpx.RequestError as exc:
            logger.warning(
                "deliver_webhook_request_error: delivery_id=%s, error=%s",
                delivery_id,
                str(exc),
            )
            new_attempt = delivery.attempt + 1
            if new_attempt > delivery.max_attempts:
                await session.execute(
                    update(WebhookDeliveryLogORM)
                    .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                    .values(
                        failed_at=datetime.now(timezone.utc),
                        attempt=new_attempt,
                        response_body=str(exc)[:1000],
                    )
                )
                await session.commit()
                return {
                    "delivery_id": delivery_id,
                    "status": "failed",
                    "error": str(exc),
                }

            backoff = timedelta(minutes=2**new_attempt)
            await session.execute(
                update(WebhookDeliveryLogORM)
                .where(WebhookDeliveryLogORM.id == UUID(delivery_id))
                .values(
                    attempt=new_attempt,
                    next_retry_at=datetime.now(timezone.utc) + backoff,
                    response_body=str(exc)[:1000],
                )
            )
            await session.commit()
            return {
                "delivery_id": delivery_id,
                "status": "retrying",
                "error": str(exc),
                "attempt": new_attempt,
            }
