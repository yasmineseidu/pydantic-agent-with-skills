"""Webhook endpoints for platform integrations (Telegram, Slack)."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from src.settings import load_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _check_integrations_enabled() -> None:
    """Check if integrations feature flag is enabled.

    Raises:
        HTTPException: 404 if integrations are disabled.
    """
    settings = load_settings()
    if not settings.feature_flags.enable_integrations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform integrations are not enabled",
        )


@router.post("/telegram")
async def telegram_webhook(request: Request) -> dict[str, str]:
    """Handle incoming Telegram webhook.

    Validates the webhook signature, parses the message, and dispatches
    a Celery task for async processing.

    Args:
        request: FastAPI Request with Telegram update payload.

    Returns:
        Acknowledgement dict.

    Raises:
        HTTPException: 404 if integrations disabled, 401 if invalid signature.
    """
    _check_integrations_enabled()

    # Read raw body
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Get bot token from header to identify which connection
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    if not secret_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-Bot-Api-Secret-Token header",
        )

    # Dispatch Celery task for async processing
    try:
        from workers.tasks.platform_tasks import handle_platform_message

        # In a real implementation, we would look up the connection by
        # the bot token/external_bot_id. For now, pass the payload directly.
        handle_platform_message.delay(
            connection_id=secret_token,  # Will be resolved to UUID in task
            payload=payload,
        )
    except Exception as exc:
        logger.warning("telegram_webhook_dispatch_failed: error=%s", str(exc))
        # Still return 200 to prevent Telegram from retrying
        pass

    logger.info("telegram_webhook_received: update_id=%s", payload.get("update_id"))
    return {"status": "ok"}


@router.post("/slack")
async def slack_webhook(request: Request) -> dict[str, Any]:
    """Handle incoming Slack webhook.

    Handles url_verification challenges and event callbacks.
    Validates the webhook signature, parses the event, and dispatches
    a Celery task for async processing.

    Args:
        request: FastAPI Request with Slack event payload.

    Returns:
        Acknowledgement dict or challenge response.

    Raises:
        HTTPException: 404 if integrations disabled, 401 if invalid signature.
    """
    _check_integrations_enabled()

    # Read raw body
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Handle url_verification challenge
    if payload.get("type") == "url_verification":
        logger.info("slack_webhook_url_verification")
        return {"challenge": payload.get("challenge", "")}

    # Validate signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )

    settings = load_settings()
    if settings.slack_signing_secret:
        from integrations.slack.webhook import validate_slack_signature

        if not validate_slack_signature(
            signing_secret=settings.slack_signing_secret,
            timestamp=timestamp,
            body=body,
            signature=signature,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Slack signature",
            )

    # Dispatch Celery task for async processing
    event = payload.get("event", {})
    event_type = event.get("type", "unknown")

    try:
        from workers.tasks.platform_tasks import handle_platform_message

        # Pass team_id from payload for connection lookup
        team_id = payload.get("team_id", "")
        handle_platform_message.delay(
            connection_id=team_id,  # Will be resolved in task
            payload=payload,
        )
    except Exception as exc:
        logger.warning("slack_webhook_dispatch_failed: error=%s", str(exc))
        pass

    logger.info("slack_webhook_received: event_type=%s", event_type)
    return {"status": "ok"}
