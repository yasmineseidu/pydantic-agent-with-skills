"""Observability middleware for request logging and cost tracking."""

import logging
import time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.db.models.tracking import UsageLogORM

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for HTTP request/response logging.

    Logs method, path, status_code, duration_ms, and request_id for every request.
    Uses structured logging format for easy parsing.

    Usage:
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """
        Process request and log details.

        Args:
            request: Incoming Starlette request
            call_next: Next middleware/handler in chain

        Returns:
            Response from handler
        """
        # Get request ID from state (set by RequestIdMiddleware)
        request_id = getattr(request.state, "request_id", None)

        # Start timer
        start_time = time.time()

        # Process request
        response: Response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Structured logging
        logger.info(
            f"http_request: method={request.method} path={request.url.path} "
            f"status={response.status_code} duration_ms={duration_ms} request_id={request_id}"
        )

        return response


class CostTracker:
    """
    Utility class for tracking LLM usage and costs.

    Logs token usage and estimated costs to the usage_log table via UsageLogORM.
    Not a middleware itself - use in endpoint handlers to record usage.

    Usage:
        tracker = CostTracker()
        await tracker.track_usage(session, team_id, model, input_tokens, output_tokens, operation)
    """

    async def track_usage(
        self,
        session: AsyncSession,
        team_id: UUID,
        model: str,
        input_tokens: int,
        output_tokens: int,
        operation: str,
        agent_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        request_id: Optional[str] = None,
        embedding_tokens: int = 0,
        estimated_cost_usd: Optional[Decimal] = None,
        metadata: Optional[dict] = None,
    ) -> UsageLogORM:
        """
        Record token usage and cost to database.

        Args:
            session: SQLAlchemy async session
            team_id: Team that owns this usage
            model: Model name (e.g., "claude-sonnet-4.5")
            input_tokens: Number of input tokens consumed
            output_tokens: Number of output tokens consumed
            operation: Operation type (e.g., "chat", "embedding", "summarize")
            agent_id: Optional agent ID
            user_id: Optional user ID
            conversation_id: Optional conversation ID
            request_id: Optional request ID for tracing
            embedding_tokens: Optional embedding tokens consumed
            estimated_cost_usd: Optional cost estimate (default 0)
            metadata: Optional additional context

        Returns:
            Created UsageLogORM instance

        Raises:
            Exception: If database write fails
        """
        # Default cost to 0 if not provided
        if estimated_cost_usd is None:
            estimated_cost_usd = Decimal("0.0")

        # Create usage log entry
        usage_log = UsageLogORM(
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
            estimated_cost_usd=estimated_cost_usd,
            operation=operation,
            metadata_json=metadata or {},
        )

        session.add(usage_log)
        await session.flush()

        logger.info(
            f"usage_tracked: team_id={team_id}, model={model}, "
            f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
            f"operation={operation}, request_id={request_id}"
        )

        return usage_log
