"""Health check endpoints for liveness and readiness probes."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_redis_manager
from src.cache.client import RedisManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Liveness check endpoint (always returns 200 OK).

    Simple endpoint to verify the application is running. Returns immediately
    without checking dependencies. Used by load balancers and orchestration
    systems for basic liveness detection.

    Returns:
        Dictionary with status "ok".
    """
    logger.debug("health_check: status=ok")
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(
    db: Optional[AsyncSession] = Depends(get_db),
    redis_manager: Optional[RedisManager] = Depends(get_redis_manager),
) -> dict[str, Any]:
    """
    Readiness check endpoint with dependency health status.

    Verifies that critical dependencies (database, optional Redis) are
    operational before accepting traffic. Returns 503 if database is unavailable.
    Redis unavailability does NOT fail readiness (graceful degradation).

    Args:
        db: Async database session from dependency injection.
        redis_manager: Optional Redis manager from dependency injection.

    Returns:
        Dictionary with status and dependency health:
        - status: "ok" if ready, "error" if not ready
        - database: "connected" or "error"
        - redis: "connected", "unavailable", or not included if not configured

    Raises:
        HTTPException: 503 if database is unavailable.
    """
    result: dict[str, Any] = {}

    # Check database
    database_status = "error"
    if db is not None:
        try:
            await db.execute(text("SELECT 1"))
            database_status = "connected"
            logger.info("readiness_check: database=connected")
        except Exception as e:
            logger.warning(f"readiness_check: database=error, error={str(e)}")
            database_status = "error"
    else:
        logger.warning("readiness_check: database=unavailable, reason=no_session")
        database_status = "error"

    result["database"] = database_status

    # Check Redis (optional - unavailability is NOT an error)
    if redis_manager is not None:
        try:
            client = await redis_manager.get_client()
            if client is not None:
                # Ping to verify connection
                await client.ping()
                redis_status = "connected"
                logger.info("readiness_check: redis=connected")
            else:
                redis_status = "unavailable"
                logger.debug("readiness_check: redis=unavailable, reason=client_none")
        except Exception as e:
            logger.warning(f"readiness_check: redis=unavailable, error={str(e)}")
            redis_status = "unavailable"

        result["redis"] = redis_status

    # Fail readiness if database is down
    if database_status == "error":
        result["status"] = "error"
        logger.error("readiness_check: status=error, reason=database_down")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )

    result["status"] = "ok"
    logger.info("readiness_check: status=ok")
    return result
