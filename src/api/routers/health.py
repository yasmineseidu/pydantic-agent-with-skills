"""Health check endpoints for liveness and readiness probes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_redis_manager
from src.api.schemas.common import HealthResponse, ServiceStatus
from src.cache.client import RedisManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness check endpoint (always returns 200 OK).

    Simple endpoint to verify the application is running. Returns immediately
    without checking dependencies. Used by load balancers and orchestration
    systems for basic liveness detection.

    Returns:
        HealthResponse with status "ok".
    """
    logger.debug("health_check: status=ok")
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(
    db: Optional[AsyncSession] = Depends(get_db),
    redis_manager: Optional[RedisManager] = Depends(get_redis_manager),
) -> HealthResponse:
    """
    Readiness check endpoint with dependency health status.

    Verifies that critical dependencies (database, optional Redis) are
    operational before accepting traffic. Returns 503 if database is unavailable.
    Redis unavailability does NOT fail readiness (graceful degradation).

    Args:
        db: Async database session from dependency injection.
        redis_manager: Optional Redis manager from dependency injection.

    Returns:
        HealthResponse with status and service health information.

    Raises:
        HTTPException: 503 if database is unavailable.
    """
    services: dict[str, ServiceStatus] = {}

    # Check database
    database_status = "error"
    database_error: Optional[str] = None
    if db is not None:
        try:
            await db.execute(text("SELECT 1"))
            database_status = "connected"
            logger.info("readiness_check: database=connected")
        except Exception as e:
            logger.warning(f"readiness_check: database=error, error={str(e)}")
            database_status = "error"
            database_error = str(e)
    else:
        logger.warning("readiness_check: database=unavailable, reason=no_session")
        database_status = "error"
        database_error = "No database session available"

    services["database"] = ServiceStatus(status=database_status, error=database_error)

    # Check Redis (optional - unavailability is NOT an error)
    if redis_manager is not None:
        redis_status = "unavailable"
        redis_error: Optional[str] = None
        try:
            client = await redis_manager.get_client()
            if client is not None:
                # Ping to verify connection
                await client.ping()
                redis_status = "connected"
                logger.info("readiness_check: redis=connected")
            else:
                redis_status = "unavailable"
                redis_error = "Redis client not available"
                logger.debug("readiness_check: redis=unavailable, reason=client_none")
        except Exception as e:
            logger.warning(f"readiness_check: redis=unavailable, error={str(e)}")
            redis_status = "unavailable"
            redis_error = str(e)

        services["redis"] = ServiceStatus(status=redis_status, error=redis_error)

    # Fail readiness if database is down
    if database_status == "error":
        logger.error("readiness_check: status=error, reason=database_down")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )

    logger.info("readiness_check: status=ok")
    return HealthResponse(status="ok", version="0.1.0", services=services)
