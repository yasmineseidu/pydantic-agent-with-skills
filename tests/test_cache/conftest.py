"""Shared fixtures for cache layer tests."""

import pytest
from typing import AsyncGenerator

from fakeredis import FakeAsyncRedis


@pytest.fixture
async def fake_redis() -> AsyncGenerator[FakeAsyncRedis, None]:
    """Async fakeredis client for isolated testing.

    Yields:
        A fresh FakeAsyncRedis instance with decode_responses=True.
        Automatically flushed and closed after each test.
    """
    client = FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushall()
    pool = getattr(client, "connection_pool", None)
    if pool is not None:
        await pool.disconnect(inuse_connections=True)
    await client.aclose()


@pytest.fixture
async def redis_manager(fake_redis: FakeAsyncRedis) -> AsyncGenerator:
    """RedisManager with injected fakeredis client (bypasses pool creation).

    Creates a RedisManager configured with a fake URL, then patches its
    internal client with the fakeredis instance so no real Redis is needed.

    Args:
        fake_redis: The fakeredis client fixture.

    Returns:
        A RedisManager that uses fakeredis internally.
    """
    from src.cache.client import RedisManager

    manager = RedisManager(redis_url="redis://fake:6379/0", key_prefix="test:")
    manager._client = fake_redis
    manager._available = True
    yield manager
    await manager.close()


@pytest.fixture
def unavailable_redis_manager():
    """RedisManager configured with no Redis URL (always unavailable).

    Returns:
        A RedisManager that returns None for all operations.
    """
    from src.cache.client import RedisManager

    return RedisManager(redis_url=None, key_prefix="test:")


@pytest.fixture
def key_prefix() -> str:
    """Standard test key prefix.

    Returns:
        The test key prefix string.
    """
    return "test:"
