"""Async database engine and session factory."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


async def get_engine(
    database_url: str,
    pool_size: int = 5,
    pool_overflow: int = 10,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: PostgreSQL connection URL (postgresql+asyncpg://...).
        pool_size: Connection pool size.
        pool_overflow: Max overflow connections beyond pool_size.

    Returns:
        Configured async engine instance.
    """
    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=pool_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return engine


async def get_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async session from an engine.

    Args:
        engine: SQLAlchemy async engine.

    Yields:
        AsyncSession instance that is automatically closed on exit.
    """
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
