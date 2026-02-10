"""Unit tests for RateLimiter in src/cache/rate_limiter.py."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.cache.rate_limiter import RateLimiter, RateLimitResult


# ---------------------------------------------------------------------------
# RateLimitResult Validation Tests
# ---------------------------------------------------------------------------


def test_rate_limit_result_valid_values():
    """Test RateLimitResult accepts valid values."""
    reset_at = datetime.now(timezone.utc)
    result = RateLimitResult(allowed=True, remaining=5, reset_at=reset_at, limit=10)

    assert result.allowed is True
    assert result.remaining == 5
    assert result.reset_at == reset_at
    assert result.limit == 10


def test_rate_limit_result_rejects_negative_remaining():
    """Test RateLimitResult rejects negative remaining value."""
    reset_at = datetime.now(timezone.utc)

    with pytest.raises(ValidationError) as exc_info:
        RateLimitResult(allowed=False, remaining=-1, reset_at=reset_at, limit=10)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("remaining",) for e in errors)


def test_rate_limit_result_rejects_zero_limit():
    """Test RateLimitResult rejects zero limit value."""
    reset_at = datetime.now(timezone.utc)

    with pytest.raises(ValidationError) as exc_info:
        RateLimitResult(allowed=False, remaining=0, reset_at=reset_at, limit=0)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("limit",) for e in errors)


def test_rate_limit_result_rejects_negative_limit():
    """Test RateLimitResult rejects negative limit value."""
    reset_at = datetime.now(timezone.utc)

    with pytest.raises(ValidationError) as exc_info:
        RateLimitResult(allowed=False, remaining=0, reset_at=reset_at, limit=-5)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("limit",) for e in errors)


# ---------------------------------------------------------------------------
# RateLimiter Tests (Redis Available)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_rate_limit_first_request_within_limit(redis_manager, key_prefix):
    """Test first request within limit returns allowed=True, remaining=limit-1."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 10
    window_seconds = 60

    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    assert result.allowed is True
    assert result.remaining == 9  # limit - 1
    assert result.limit == limit
    assert result.reset_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_check_rate_limit_requests_up_to_limit(redis_manager, key_prefix):
    """Test requests up to limit are all allowed with decreasing remaining count."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 5
    window_seconds = 60

    results = []
    for _ in range(limit):
        result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)
        results.append(result)

    # All requests should be allowed
    assert all(r.allowed for r in results)

    # Remaining should decrement: 4, 3, 2, 1, 0
    expected_remaining = [4, 3, 2, 1, 0]
    actual_remaining = [r.remaining for r in results]
    assert actual_remaining == expected_remaining


@pytest.mark.asyncio
async def test_check_rate_limit_request_exceeding_limit(redis_manager, key_prefix):
    """Test request exceeding limit returns allowed=False, remaining=0."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 3
    window_seconds = 60

    # Make requests up to and beyond the limit
    for _ in range(limit):
        await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    # The next request should be denied
    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    assert result.allowed is False
    assert result.remaining == 0
    assert result.limit == limit


@pytest.mark.asyncio
async def test_check_rate_limit_different_resources_independent(redis_manager, key_prefix):
    """Test different resources have independent counters."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource_a = "resource_a"
    resource_b = "resource_b"
    limit = 5
    window_seconds = 60

    # Make 3 requests to resource_a
    for _ in range(3):
        await limiter.check_rate_limit(team_id, resource_a, limit, window_seconds)

    # First request to resource_b should have full limit available
    result_b = await limiter.check_rate_limit(team_id, resource_b, limit, window_seconds)
    assert result_b.allowed is True
    assert result_b.remaining == 4  # limit - 1

    # resource_a should still have 2 remaining
    result_a = await limiter.check_rate_limit(team_id, resource_a, limit, window_seconds)
    assert result_a.allowed is True
    assert result_a.remaining == 1  # 5 - 4 requests


@pytest.mark.asyncio
async def test_check_rate_limit_different_teams_independent(redis_manager, key_prefix):
    """Test different team_ids have independent counters."""
    limiter = RateLimiter(redis_manager)
    team_a = uuid4()
    team_b = uuid4()
    resource = "shared_resource"
    limit = 5
    window_seconds = 60

    # Make 4 requests for team_a
    for _ in range(4):
        await limiter.check_rate_limit(team_a, resource, limit, window_seconds)

    # First request for team_b should have full limit available
    result_b = await limiter.check_rate_limit(team_b, resource, limit, window_seconds)
    assert result_b.allowed is True
    assert result_b.remaining == 4  # limit - 1

    # team_a should have 1 remaining
    result_a = await limiter.check_rate_limit(team_a, resource, limit, window_seconds)
    assert result_a.allowed is True
    assert result_a.remaining == 0  # 5 - 5 requests


@pytest.mark.asyncio
async def test_check_rate_limit_key_format(redis_manager, key_prefix):
    """Test Redis key format is {prefix}rate:{team_id}:{resource}."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"

    expected_key = f"{key_prefix}rate:{team_id}:{resource}"
    actual_key = limiter._key(team_id, resource)

    assert actual_key == expected_key


@pytest.mark.asyncio
async def test_check_rate_limit_reset_at_in_future(redis_manager, key_prefix):
    """Test reset_at is in the future."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 10
    window_seconds = 60

    before = datetime.now(timezone.utc)
    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)
    after = datetime.now(timezone.utc)

    # reset_at should be in the future (between now and now + window_seconds)
    assert result.reset_at > before
    assert result.reset_at > after


@pytest.mark.asyncio
async def test_check_rate_limit_result_limit_matches_input(redis_manager, key_prefix):
    """Test result limit field matches the input limit."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 42
    window_seconds = 60

    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    assert result.limit == limit


# ---------------------------------------------------------------------------
# RateLimiter Tests (Redis Unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_rate_limit_redis_unavailable_degraded_mode(unavailable_redis_manager):
    """Test Redis unavailable returns allowed=True (degraded mode) with remaining=limit."""
    limiter = RateLimiter(unavailable_redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 10
    window_seconds = 60

    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    assert result.allowed is True
    assert result.remaining == limit
    assert result.limit == limit
    assert result.reset_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_check_rate_limit_client_returns_none_degraded_mode(redis_manager):
    """Test degraded mode when client returns None (connection fails after init)."""
    limiter = RateLimiter(redis_manager)
    team_id = uuid4()
    resource = "test_resource"
    limit = 10
    window_seconds = 60

    # Simulate connection failure by setting client to None
    redis_manager._client = None

    result = await limiter.check_rate_limit(team_id, resource, limit, window_seconds)

    assert result.allowed is True
    assert result.remaining == limit
    assert result.limit == limit
    assert result.reset_at > datetime.now(timezone.utc)
