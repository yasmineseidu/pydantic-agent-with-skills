"""Request ID middleware for request tracing."""

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for request ID tracking.

    If X-Request-ID header is present, uses it. Otherwise generates UUID4.
    Adds X-Request-ID to response headers and stores in request.state for logging.

    Usage:
        app.add_middleware(RequestIdMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """
        Process request and add request ID.

        Args:
            request: Incoming Starlette request
            call_next: Next middleware/handler in chain

        Returns:
            Response with X-Request-ID header
        """
        # Check for existing request ID in header
        request_id = request.headers.get("X-Request-ID")

        # Generate new ID if not provided
        if not request_id:
            request_id = str(uuid.uuid4())
            logger.debug(f"request_id_generated: request_id={request_id}")
        else:
            logger.debug(f"request_id_provided: request_id={request_id}")

        # Store in request state for use by other middleware/handlers
        request.state.request_id = request_id

        # Process request
        response: Response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = request_id

        return response
