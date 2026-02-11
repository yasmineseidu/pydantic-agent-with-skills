"""Outbound webhook event dispatcher."""

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def dispatch_webhook_event(
    event_type: str,
    payload: dict[str, Any],
    team_id: str,
    webhook_url: str,
    session: Any,
    settings: Any,
) -> Optional[str]:
    """Dispatch an outbound webhook event for delivery.

    Creates a WebhookDeliveryLogORM record and dispatches a Celery task
    for async delivery. Only dispatches if enable_webhooks feature flag is on.

    Args:
        event_type: Event type string (conversation.created, message.created, etc.)
        payload: Event payload dict.
        team_id: Team UUID as string.
        webhook_url: Destination webhook URL.
        session: SQLAlchemy async session.
        settings: Settings instance for feature flag check.

    Returns:
        Event ID if dispatched, None if webhooks disabled.
    """
    # Check feature flag
    if not settings.feature_flags.enable_webhooks:
        logger.debug("dispatch_webhook_event_skipped: webhooks disabled")
        return None

    from uuid import UUID

    from src.db.models.platform import WebhookDeliveryLogORM

    # Generate unique event ID
    event_id = f"evt_{uuid.uuid4().hex[:16]}"

    # Create delivery log record
    delivery = WebhookDeliveryLogORM(
        team_id=UUID(team_id),
        event_type=event_type,
        event_id=event_id,
        payload=payload,
        webhook_url=webhook_url,
    )
    session.add(delivery)
    await session.flush()  # Get the ID

    delivery_id = str(delivery.id)

    # Dispatch Celery task for async delivery
    try:
        from workers.tasks.platform_tasks import deliver_webhook

        deliver_webhook.delay(delivery_id=delivery_id)
        logger.info(
            "dispatch_webhook_event_dispatched: event_id=%s, event_type=%s, team_id=%s",
            event_id,
            event_type,
            team_id,
        )
    except Exception:
        logger.warning(
            "dispatch_webhook_event_celery_unavailable: event_id=%s, queued_in_db",
            event_id,
        )

    return event_id
