"""FastAPI application factory with async lifespan management."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from src.cache.client import RedisManager
from src.cache.rate_limiter import RateLimiter
from src.db.engine import get_engine
from src.settings import load_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage FastAPI application lifespan (startup and shutdown).

    Handles initialization and cleanup of:
    - Database engine (if database_url is configured)
    - Redis connection pool (if redis_url is configured)

    Resources are stored in app.state for access by routes and dependencies.

    Args:
        app: FastAPI application instance.

    Yields:
        None during the application runtime (between startup and shutdown).
    """
    # Load settings
    settings = load_settings()
    app.state.settings = settings
    logger.info("app_startup: initializing resources")

    # Validate JWT secret key is configured (required for all auth operations)
    if not settings.jwt_secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set in environment or .env file. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    # Initialize database engine (optional)
    engine: Optional[AsyncEngine] = None
    if settings.database_url:
        try:
            engine = await get_engine(
                database_url=settings.database_url,
                pool_size=settings.database_pool_size,
                pool_overflow=settings.database_pool_overflow,
            )
            app.state.engine = engine
            logger.info("db_engine_initialized: url=postgresql+asyncpg://...")
        except Exception as e:
            logger.exception(f"db_engine_init_error: error={str(e)}")
            app.state.engine = None
    else:
        app.state.engine = None
        logger.info("db_engine_skipped: database_url not configured")

    # Initialize Redis manager (optional)
    redis_manager: Optional[RedisManager] = None
    if settings.redis_url:
        try:
            redis_manager = RedisManager(
                redis_url=settings.redis_url, key_prefix=settings.redis_key_prefix
            )
            # Test connection
            client = await redis_manager.get_client()
            if client:
                app.state.redis = redis_manager
                logger.info("redis_initialized: url=redis://...")
            else:
                app.state.redis = None
                logger.warning("redis_connection_failed: client returned None")
        except Exception as e:
            logger.exception(f"redis_init_error: error={str(e)}")
            app.state.redis = None
    else:
        app.state.redis = None
        logger.info("redis_skipped: redis_url not configured")

    # Initialize rate limiter (optional, requires Redis)
    rate_limiter: Optional[RateLimiter] = None
    if redis_manager is not None:
        try:
            rate_limiter = RateLimiter(redis_manager)
            app.state.rate_limiter = rate_limiter
            logger.info("rate_limiter_initialized: redis_backed=True")
        except Exception as e:
            logger.exception(f"rate_limiter_init_error: error={str(e)}")
            app.state.rate_limiter = None
    else:
        app.state.rate_limiter = None
        logger.info("rate_limiter_skipped: redis not available")

    # Application is running
    logger.info("app_startup_complete: resources initialized")
    yield

    # Shutdown: clean up resources
    logger.info("app_shutdown: cleaning up resources")

    # Close Redis connection pool
    if redis_manager is not None:
        try:
            await redis_manager.close()
            logger.info("redis_closed: connection pool disposed")
        except Exception as e:
            logger.warning(f"redis_close_error: error={str(e)}")

    # Dispose database engine
    if engine is not None:
        try:
            await engine.dispose()
            logger.info("db_engine_disposed: connection pool closed")
        except Exception as e:
            logger.warning(f"db_engine_dispose_error: error={str(e)}")

    logger.info("app_shutdown_complete: all resources cleaned up")


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance.

    Returns:
        Configured FastAPI application with lifespan, CORS, routes, and middleware.
    """
    settings = load_settings()

    app = FastAPI(
        title="Skill Agent API",
        version="0.1.0",
        description="REST API for multi-agent platform with skill-based AI agents",
        lifespan=lifespan,
    )

    # Middleware registration order: Starlette executes in LIFO (last registered = first to run).
    # Execution order: CORS -> ErrorHandler -> RateLimit -> RequestID -> RequestLogging

    # Register innermost middleware first (runs last)
    from src.api.middleware.observability import RequestLoggingMiddleware

    app.add_middleware(RequestLoggingMiddleware)

    # Request ID middleware (sets request.state.request_id for downstream logging)
    from src.api.middleware.request_id import RequestIdMiddleware

    app.add_middleware(RequestIdMiddleware)

    # Rate limit middleware (will be configured during lifespan)
    from src.api.middleware.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware, rate_limiter=None)  # Set in lifespan

    # Error handling middleware (catches exceptions from all inner middleware/routes)
    from src.api.middleware.error_handler import error_handling_middleware

    app.middleware("http")(error_handling_middleware)

    # CORS middleware (outermost, runs first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from src.api.routers import (
        agents_router,
        auth_router,
        chat_router,
        collaboration_router,
        conversations_router,
        health_router,
        memories_router,
        teams_router,
        webhooks_router,
    )

    # Health checks (no prefix, paths start with /health and /ready)
    app.include_router(health_router, tags=["health"])

    # Auth endpoints (router has prefix="/v1/auth" in definition)
    app.include_router(auth_router)

    # API v1 endpoints (routers already have /v1/* paths in their @router decorators)
    app.include_router(agents_router, tags=["agents"])
    app.include_router(teams_router, tags=["teams"])
    app.include_router(memories_router, tags=["memories"])
    app.include_router(conversations_router, tags=["conversations"])
    app.include_router(collaboration_router, tags=["collaboration"])
    app.include_router(webhooks_router, tags=["webhooks"])

    # Chat endpoint (path is /{agent_slug}/chat, needs /v1/agents prefix)
    app.include_router(chat_router, prefix="/v1/agents", tags=["chat"])

    logger.info(
        "app_created: title=Skill Agent API, version=0.1.0, routers=8, "
        "middleware=cors,error_handler,rate_limit,request_id,request_logging"
    )
    return app
