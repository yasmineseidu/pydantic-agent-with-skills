"""Common API schemas shared across endpoints."""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response.

    Args:
        error: Error type identifier (e.g., "validation_error", "not_found")
        message: Human-readable error description
        details: Optional additional error context (e.g., field-level validation errors)
        request_id: Optional request ID for tracing
    """

    error: str
    message: str
    details: Optional[dict] = None
    request_id: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response.

    Args:
        message: Human-readable success message
        data: Optional response payload
    """

    message: str
    data: Optional[dict] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based paginated response.

    Args:
        items: List of items in the current page
        total: Total count of items across all pages
        limit: Max items per page (1-100)
        offset: Number of items skipped from the start
        has_more: Whether more items exist beyond this page
    """

    items: list[T]
    total: int
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    has_more: bool


class ServiceStatus(BaseModel):
    """Service health status information.

    Args:
        status: Service status ("connected", "unavailable", "error")
        latency_ms: Optional response latency in milliseconds
        error: Optional error message if service is unhealthy
    """

    status: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response with service status.

    Args:
        status: Overall health status ("ok", "degraded", "error")
        version: Application version
        services: Dictionary of service statuses (e.g., {"database": ServiceStatus})
    """

    status: str
    version: str = "0.1.0"
    services: dict[str, ServiceStatus] = Field(default_factory=dict)
