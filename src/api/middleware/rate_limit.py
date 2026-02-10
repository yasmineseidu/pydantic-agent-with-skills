"""Rate limit middleware with X-RateLimit headers."""

import logging
from typing import Optional
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.cache.rate_limiter import RateLimiter
from src.auth.jwt import decode_token

logger = logging.getLogger(__name__)

# Rate limit configurations: resource -> (limit, window_seconds)
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "chat": (60, 60),  # 60 requests per minute for chat
    "api": (300, 60),  # 300 requests per minute for general API
    "auth": (10, 60),  # 10 requests per minute for auth endpoints (IP-based)
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis token-bucket algorithm.

    Applies rate limits based on endpoint type:
    - Chat endpoints: 60 req/min per user
    - API endpoints: 300 req/min per team
    - Auth endpoints: 10 req/min per IP

    When Redis unavailable: gracefully degrades to allow all requests.

    Adds X-RateLimit headers:
    - X-RateLimit-Limit: Maximum requests per window
    - X-RateLimit-Remaining: Remaining requests in current window
    - X-RateLimit-Reset: Unix timestamp when window resets
    - Retry-After: Seconds until reset (only on 429)

    Usage:
        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    """

    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None) -> None:  # type: ignore[no-untyped-def]
        """Initialize rate limit middleware.

        Args:
            app: FastAPI application instance.
            rate_limiter: Optional RateLimiter instance (Phase 3).
        """
        super().__init__(app)
        self._rate_limiter: Optional[RateLimiter] = rate_limiter

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Process request and enforce rate limits.

        Args:
            request: Incoming Starlette request.
            call_next: Next middleware/handler in chain.

        Returns:
            Response with X-RateLimit headers (or 429 if limit exceeded).
        """
        # Resolve limiter from app state if not provided at init
        if self._rate_limiter is None:
            self._rate_limiter = getattr(request.app.state, "rate_limiter", None)

        # Skip rate limiting if limiter not available
        if self._rate_limiter is None:
            logger.debug("rate_limit_skipped: reason=limiter_not_available")
            response: Response = await call_next(request)
            return response

        # Determine rate limit resource type based on path
        resource, limit, window_seconds = self._get_rate_limit_config(request.url.path)

        # Skip rate limiting for health checks
        if resource is None:
            response = await call_next(request)
            return response

        # Get team_id from request state (if set by upstream auth)
        team_id: Optional[UUID] = getattr(request.state, "team_id", None)

        # Attempt to derive team_id from JWT if available
        if team_id is None:
            auth_header = request.headers.get("authorization")
            if auth_header:
                parts = auth_header.split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    try:
                        payload = decode_token(parts[1])
                        team_id = payload.team_id
                        if team_id:
                            request.state.team_id = team_id
                    except Exception:
                        team_id = None

        # For auth endpoints or missing team_id, use IP-based rate limiting
        if team_id is None:
            # Use client IP as team_id for auth endpoints
            client_ip = request.client.host if request.client else "unknown"
            # Create a deterministic UUID from IP string for rate limiting
            import hashlib

            team_id_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:32]
            team_id = UUID(team_id_hash)
            logger.debug(
                f"rate_limit_auth_endpoint: client_ip={client_ip}, "
                f"path={request.url.path}, resource={resource}"
            )

        # Check rate limit
        result = await self._rate_limiter.check_rate_limit(
            team_id=team_id,
            resource=resource,
            limit=limit,
            window_seconds=window_seconds,
        )

        # Build response with rate limit headers
        if result.allowed:
            # Process request normally
            response = await call_next(request)

            # Add X-RateLimit headers to successful responses
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(result.reset_at.timestamp()))

            logger.debug(
                f"rate_limit_allowed: team_id={team_id}, resource={resource}, "
                f"remaining={result.remaining}, limit={result.limit}"
            )

            return response
        else:
            # Rate limit exceeded - return 429
            from datetime import datetime, timezone

            reset_timestamp = int(result.reset_at.timestamp())
            now_timestamp = int(datetime.now(timezone.utc).timestamp())
            retry_after_seconds = max(0, reset_timestamp - now_timestamp)

            logger.warning(
                f"rate_limit_exceeded: team_id={team_id}, resource={resource}, "
                f"limit={result.limit}, retry_after={retry_after_seconds}s"
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after_seconds,
                },
                headers={
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_timestamp),
                    "Retry-After": str(retry_after_seconds),
                },
            )

    def _get_rate_limit_config(self, path: str) -> tuple[Optional[str], int, int]:
        """Determine rate limit configuration based on request path.

        Args:
            path: Request URL path.

        Returns:
            Tuple of (resource_name, limit, window_seconds).
            Returns (None, 0, 0) if rate limiting should be skipped.
        """
        # Health checks: no rate limit
        if path.startswith("/health") or path.startswith("/ready"):
            return (None, 0, 0)

        # Chat endpoints: 60/min per user
        if "/chat" in path:
            limit, window = _RATE_LIMITS["chat"]
            return ("chat", limit, window)

        # Auth endpoints: 10/min per IP
        if path.startswith("/v1/auth"):
            limit, window = _RATE_LIMITS["auth"]
            return ("auth", limit, window)

        # All other API endpoints: 300/min per team
        limit, window = _RATE_LIMITS["api"]
        return ("api", limit, window)
