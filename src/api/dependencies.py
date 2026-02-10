"""FastAPI dependency injection for database, settings, and agent dependencies."""

import logging
from typing import AsyncGenerator, Optional

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.client import RedisManager
from src.cache.rate_limiter import RateLimiter
from src.db.engine import get_session
from src.dependencies import AgentDependencies
from src.settings import Settings, load_settings

logger = logging.getLogger(__name__)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session from app.state.engine.

    Yields an AsyncSession that is automatically closed after use.
    Requires app.state.engine to be initialized during lifespan.

    Args:
        request: FastAPI request object with app.state.engine.

    Yields:
        AsyncSession instance for database operations.

    Raises:
        RuntimeError: If app.state.engine is not initialized.

    Example:
        >>> @router.get("/users")
        >>> async def list_users(db: AsyncSession = Depends(get_db)):
        >>>     result = await db.execute(select(UserORM))
        >>>     return result.scalars().all()
    """
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        logger.error("get_db_error: reason=engine_not_initialized")
        raise RuntimeError(
            "Database engine not initialized. Ensure DATABASE_URL is set and app lifespan has run."
        )

    async for session in get_session(engine):
        logger.debug("db_session_created: engine=initialized")
        yield session
        logger.debug("db_session_closed: cleanup=complete")


def get_settings(request: Request) -> Settings:
    """
    Get application settings from app.state.settings.

    Requires app.state.settings to be initialized during lifespan (app.py).
    If not available, falls back to load_settings() which may raise.

    Args:
        request: FastAPI request object with app.state.

    Returns:
        Settings instance with application configuration.

    Example:
        >>> @router.get("/config")
        >>> async def get_config(settings: Settings = Depends(get_settings)):
        >>>     return {"llm_model": settings.llm_model}
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        # Fallback: load settings directly (not ideal, but prevents crashes)
        logger.warning(
            "get_settings_fallback: app.state.settings not initialized, loading directly"
        )
        settings = load_settings()
    return settings


def get_redis_manager(request: Request) -> Optional[RedisManager]:
    """
    Get Redis manager from app.state.redis.

    Returns None when Redis is not configured or unavailable (graceful degradation).

    Args:
        request: FastAPI request object with app.state.redis.

    Returns:
        RedisManager instance if available, None otherwise.

    Example:
        >>> @router.get("/cache-stats")
        >>> async def cache_stats(redis: Optional[RedisManager] = Depends(get_redis_manager)):
        >>>     if redis and redis.available:
        >>>         return await redis.health_check()
        >>>     return {"status": "unavailable"}
    """
    redis_manager = getattr(request.app.state, "redis", None)
    if redis_manager is None:
        logger.debug("get_redis_manager: redis not configured")
    return redis_manager


def get_rate_limiter(request: Request) -> Optional[RateLimiter]:
    """
    Get rate limiter from app.state.rate_limiter.

    Returns None when rate limiter is not configured (graceful degradation).

    Args:
        request: FastAPI request object with app.state.rate_limiter.

    Returns:
        RateLimiter instance if available, None otherwise.

    Example:
        >>> @router.post("/chat")
        >>> async def chat(
        >>>     rate_limiter: Optional[RateLimiter] = Depends(get_rate_limiter),
        >>>     current_user: tuple[UserORM, UUID] = Depends(get_current_user)
        >>> ):
        >>>     user, team_id = current_user
        >>>     if rate_limiter:
        >>>         result = await rate_limiter.check_rate_limit(team_id, "chat", 100, 60)
        >>>         if not result.allowed:
        >>>             raise HTTPException(status_code=429, detail="Rate limit exceeded")
        >>>     # Process chat request...
    """
    rate_limiter = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is None:
        logger.debug("get_rate_limiter: rate limiter not configured")
    return rate_limiter


async def get_agent_deps(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis_manager: Optional[RedisManager] = Depends(get_redis_manager),
) -> AgentDependencies:
    """
    Create and initialize AgentDependencies for skill-based agent usage.

    Bridges FastAPI DI to the existing AgentDependencies dataclass.
    Initializes skill loader and provides access to all agent subsystems.

    Args:
        db: Async database session from get_db dependency.
        settings: Application settings from get_settings dependency.
        redis_manager: Optional Redis manager from get_redis_manager dependency.

    Returns:
        Initialized AgentDependencies instance ready for agent execution.

    Example:
        >>> @router.post("/agent/run")
        >>> async def run_agent(
        >>>     query: str,
        >>>     deps: AgentDependencies = Depends(get_agent_deps)
        >>> ):
        >>>     result = await skill_agent.run(query, deps=deps)
        >>>     return {"response": result.data}
    """
    deps = AgentDependencies(
        settings=settings,
        redis_manager=redis_manager,
        # Additional Phase 2/3 fields can be initialized here when needed:
        # embedding_service=...,
        # memory_repo=...,
        # etc.
    )

    # Initialize skill loader (reads skill metadata from filesystem)
    await deps.initialize()

    logger.info(
        f"agent_deps_initialized: skills_count={len(deps.skill_loader.skills) if deps.skill_loader else 0}, "
        f"redis_available={redis_manager.available if redis_manager else False}"
    )
    return deps
