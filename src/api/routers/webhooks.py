"""Webhook endpoints for platform integrations (Telegram, Slack)."""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.db.models.platform import PlatformConnectionORM, PlatformStatusEnum
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


async def _lookup_connection(
    db: AsyncSession,
    platform: str,
    external_bot_id: str,
) -> Optional[PlatformConnectionORM]:
    """Look up an active platform connection by platform type and external bot ID.

    Uses the idx_platform_external index for efficient lookup.

    Args:
        db: Async database session.
        platform: Platform type string (e.g., "telegram", "slack").
        external_bot_id: Platform-specific bot/app identifier.

    Returns:
        PlatformConnectionORM if found and active, None otherwise.
    """
    stmt = select(PlatformConnectionORM).where(
        PlatformConnectionORM.platform == platform,
        PlatformConnectionORM.external_bot_id == external_bot_id,
        PlatformConnectionORM.status == PlatformStatusEnum.ACTIVE.value,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle incoming Telegram webhook.

    Validates the webhook signature, looks up the platform connection,
    and dispatches a Celery task for async processing.

    Args:
        request: FastAPI Request with Telegram update payload.
        db: Async database session.

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

    # Get secret token header to identify which bot connection
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    if not secret_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-Bot-Api-Secret-Token header",
        )

    # Look up platform connection by external_bot_id
    connection = await _lookup_connection(db, "telegram", secret_token)
    if not connection:
        logger.warning(
            "telegram_webhook_connection_not_found: external_bot_id=%s",
            secret_token[:8] + "...",
        )
        # Return 200 to prevent Telegram from retrying
        return {"status": "ok"}

    # Dispatch Celery task for async processing
    try:
        from workers.tasks.platform_tasks import handle_platform_message

        handle_platform_message.delay(
            connection_id=str(connection.id),
            payload=payload,
        )
    except Exception as exc:
        logger.warning("telegram_webhook_dispatch_failed: error=%s", str(exc))
        # Still return 200 to prevent Telegram from retrying

    logger.info("telegram_webhook_received: update_id=%s", payload.get("update_id"))
    return {"status": "ok"}


@router.post("/slack")
async def slack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Handle incoming Slack webhook.

    Handles url_verification challenges and event callbacks.
    Validates the webhook signature, looks up the platform connection,
    and dispatches a Celery task for async processing.

    Args:
        request: FastAPI Request with Slack event payload.
        db: Async database session.

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

    # Validate signature BEFORE handling any payload content (including url_verification)
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )

    settings = load_settings()
    if not settings.slack_signing_secret:
        logger.error("slack_webhook_no_signing_secret: signature validation impossible")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack webhook not configured",
        )

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

    # Handle url_verification challenge (AFTER signature validation)
    if payload.get("type") == "url_verification":
        logger.info("slack_webhook_url_verification")
        return {"challenge": payload.get("challenge", "")}

    # Look up platform connection by Slack api_app_id (external_bot_id)
    api_app_id = payload.get("api_app_id", "")
    connection = await _lookup_connection(db, "slack", api_app_id)
    if not connection:
        logger.warning(
            "slack_webhook_connection_not_found: api_app_id=%s",
            api_app_id,
        )
        return {"status": "ok"}

    # Dispatch Celery task for async processing
    event = payload.get("event", {})
    event_type = event.get("type", "unknown")

    try:
        from workers.tasks.platform_tasks import handle_platform_message

        handle_platform_message.delay(
            connection_id=str(connection.id),
            payload=payload,
        )
    except Exception as exc:
        logger.warning("slack_webhook_dispatch_failed: error=%s", str(exc))

    logger.info("slack_webhook_received: event_type=%s", event_type)
    return {"status": "ok"}
