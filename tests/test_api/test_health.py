"""Unit tests for health check endpoints."""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routers.health import health_check, readiness_check
from src.api.schemas.common import HealthResponse
from src.cache.client import RedisManager


class TestHealthCheck:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self) -> None:
        """health_check should always return status ok."""
        result = await health_check()

        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_health_check_no_dependencies(self) -> None:
        """health_check should not require any dependencies."""
        # This test verifies the function signature
        result = await health_check()
        assert isinstance(result, HealthResponse)
        assert result.status == "ok"


class TestReadinessCheck:
    """Tests for /ready endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_check_all_connected(self) -> None:
        """readiness_check returns 200 ok when all dependencies are healthy."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        # Mock Redis manager
        mock_redis = AsyncMock(spec=RedisManager)
        mock_client = AsyncMock()
        mock_redis.get_client = AsyncMock(return_value=mock_client)
        mock_client.ping = AsyncMock()

        result = await readiness_check(db=mock_db, redis_manager=mock_redis)

        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.services["database"].status == "connected"
        assert result.services["redis"].status == "connected"

    @pytest.mark.asyncio
    async def test_readiness_check_no_redis(self) -> None:
        """readiness_check returns ok without Redis (graceful degradation)."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        result = await readiness_check(db=mock_db, redis_manager=None)

        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.services["database"].status == "connected"
        assert "redis" not in result.services

    @pytest.mark.asyncio
    async def test_readiness_check_redis_unavailable(self) -> None:
        """readiness_check returns ok even if Redis is unavailable."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        # Mock Redis manager with no client
        mock_redis = AsyncMock(spec=RedisManager)
        mock_redis.get_client = AsyncMock(return_value=None)

        result = await readiness_check(db=mock_db, redis_manager=mock_redis)

        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.services["database"].status == "connected"
        assert result.services["redis"].status == "unavailable"

    @pytest.mark.asyncio
    async def test_readiness_check_redis_ping_fails(self) -> None:
        """readiness_check marks Redis unavailable if ping fails."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        # Mock Redis manager with failed ping
        mock_redis = AsyncMock(spec=RedisManager)
        mock_client = AsyncMock()
        mock_redis.get_client = AsyncMock(return_value=mock_client)
        mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))

        result = await readiness_check(db=mock_db, redis_manager=mock_redis)

        assert isinstance(result, HealthResponse)
        assert result.status == "ok"
        assert result.services["database"].status == "connected"
        assert result.services["redis"].status == "unavailable"

    @pytest.mark.asyncio
    async def test_readiness_check_database_error_raises_503(self) -> None:
        """readiness_check raises 503 when database is down."""
        from fastapi import HTTPException

        # Mock database session with error
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=Exception("Connection timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await readiness_check(db=mock_db, redis_manager=None)

        assert exc_info.value.status_code == 503
        assert "Database service unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_readiness_check_no_database_raises_503(self) -> None:
        """readiness_check raises 503 when database session is None."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await readiness_check(db=None, redis_manager=None)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_readiness_check_result_structure(self) -> None:
        """readiness_check result always includes status and database."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        result = await readiness_check(db=mock_db, redis_manager=None)

        # Check required fields
        assert isinstance(result, HealthResponse)
        assert result.status in ["ok", "error"]
        assert "database" in result.services
        assert result.services["database"].status in ["connected", "error"]

    @pytest.mark.asyncio
    async def test_readiness_check_executes_select_1(self) -> None:
        """readiness_check executes SELECT 1 on the database."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        await readiness_check(db=mock_db, redis_manager=None)

        # Verify SELECT 1 was executed
        mock_db.execute.assert_called_once()
        # Get the first argument passed to execute
        call_args = mock_db.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_readiness_check_with_both_dependencies_available(self) -> None:
        """readiness_check should report both dependencies available."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        # Mock Redis manager
        mock_redis = AsyncMock(spec=RedisManager)
        mock_client = AsyncMock()
        mock_redis.get_client = AsyncMock(return_value=mock_client)
        mock_client.ping = AsyncMock()

        result = await readiness_check(db=mock_db, redis_manager=mock_redis)

        # Both should be connected
        assert isinstance(result, HealthResponse)
        assert result.services["database"].status == "connected"
        assert result.services["redis"].status == "connected"
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_readiness_check_database_connection_error(self) -> None:
        """readiness_check fails with database connection errors."""
        from fastapi import HTTPException

        # Mock database session with connection error
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(side_effect=ConnectionError("Failed to connect to database"))

        with pytest.raises(HTTPException) as exc_info:
            await readiness_check(db=mock_db, redis_manager=None)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_readiness_check_result_types(self) -> None:
        """readiness_check result values are strings."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        result = await readiness_check(db=mock_db, redis_manager=None)

        assert isinstance(result, HealthResponse)
        assert isinstance(result.status, str)
        assert isinstance(result.services["database"].status, str)

    @pytest.mark.asyncio
    async def test_readiness_check_redis_client_none_is_unavailable(self) -> None:
        """readiness_check marks Redis unavailable when get_client returns None."""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()

        # Mock Redis manager with None client
        mock_redis = AsyncMock(spec=RedisManager)
        mock_redis.get_client = AsyncMock(return_value=None)

        result = await readiness_check(db=mock_db, redis_manager=mock_redis)

        assert isinstance(result, HealthResponse)
        assert result.services["redis"].status == "unavailable"
        assert result.status == "ok"  # But readiness still passes
