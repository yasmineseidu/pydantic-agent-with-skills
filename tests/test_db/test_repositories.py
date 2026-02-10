"""Unit tests for repository layer (no database required).

Validates repository class structure, method signatures, inheritance,
and basic mock-based behavior using inspect and unittest.mock.
"""

import inspect
from typing import Generic
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.db.base import Base
from src.db.models.memory import MemoryORM, MemoryStatusEnum
from src.db.repositories.base import BaseRepository
from src.db.repositories.memory_repo import MemoryRepository


# ---------------------------------------------------------------------------
# BaseRepository structural tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseRepositoryStructure:
    """Verify BaseRepository class structure and interface."""

    def test_base_repository_is_generic(self) -> None:
        """BaseRepository must be a Generic[T] class."""
        assert issubclass(BaseRepository, Generic)  # type: ignore[arg-type]

    def test_base_repository_init(self) -> None:
        """BaseRepository.__init__ must accept session and model_class."""
        sig = inspect.signature(BaseRepository.__init__)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "model_class" in params

    def test_base_repository_has_crud_methods(self) -> None:
        """BaseRepository must have get_by_id, create, update, delete, list_all."""
        expected_methods = {"get_by_id", "create", "update", "delete", "list_all"}
        actual_methods = {
            name
            for name, _ in inspect.getmembers(BaseRepository, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        missing = expected_methods - actual_methods
        assert not missing, f"Missing CRUD methods: {missing}"

    def test_base_repository_methods_are_async(self) -> None:
        """All CRUD methods must be coroutine functions."""
        methods = ["get_by_id", "create", "update", "delete", "list_all"]
        for method_name in methods:
            method = getattr(BaseRepository, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} is not async"


# ---------------------------------------------------------------------------
# MemoryRepository structural tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMemoryRepositoryStructure:
    """Verify MemoryRepository class structure and inheritance."""

    def test_memory_repository_extends_base(self) -> None:
        """MemoryRepository must be a subclass of BaseRepository."""
        assert issubclass(MemoryRepository, BaseRepository)

    def test_memory_repository_init_sets_model_class(self) -> None:
        """MemoryRepository must set _model_class to MemoryORM."""
        mock_session = AsyncMock()
        repo = MemoryRepository(session=mock_session)
        assert repo._model_class is MemoryORM

    def test_memory_repository_has_search_methods(self) -> None:
        """MemoryRepository must have search_by_embedding, find_similar, get_by_team."""
        expected_methods = {"search_by_embedding", "find_similar", "get_by_team"}
        actual_methods = {
            name
            for name, _ in inspect.getmembers(MemoryRepository, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        missing = expected_methods - actual_methods
        assert not missing, f"Missing search methods: {missing}"

    def test_memory_repository_search_methods_are_async(self) -> None:
        """All custom search methods must be coroutine functions."""
        methods = ["search_by_embedding", "find_similar", "get_by_team"]
        for method_name in methods:
            method = getattr(MemoryRepository, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} is not async"


# ---------------------------------------------------------------------------
# MemoryRepository method signature tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMemoryRepositorySignatures:
    """Validate method signatures for MemoryRepository custom methods."""

    def test_search_by_embedding_params(self) -> None:
        """search_by_embedding must have correct parameters and defaults."""
        sig = inspect.signature(MemoryRepository.search_by_embedding)
        params = sig.parameters

        assert "embedding" in params
        assert "team_id" in params
        assert "agent_id" in params
        assert params["agent_id"].default is None
        assert "memory_types" in params
        assert params["memory_types"].default is None
        assert "limit" in params
        assert params["limit"].default == 20

    def test_find_similar_params(self) -> None:
        """find_similar must have correct parameters and defaults."""
        sig = inspect.signature(MemoryRepository.find_similar)
        params = sig.parameters

        assert "embedding" in params
        assert "team_id" in params
        assert "threshold" in params
        assert params["threshold"].default == 0.92

    def test_get_by_team_params(self) -> None:
        """get_by_team must have correct parameters and defaults."""
        sig = inspect.signature(MemoryRepository.get_by_team)
        params = sig.parameters

        assert "team_id" in params
        assert "memory_types" in params
        assert params["memory_types"].default is None
        assert "status" in params
        assert params["status"].default == MemoryStatusEnum.ACTIVE
        assert "limit" in params
        assert params["limit"].default == 100
        assert "offset" in params
        assert params["offset"].default == 0


# ---------------------------------------------------------------------------
# Mock-based behavior tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseRepositoryMockBehavior:
    """Test BaseRepository behavior using mocked AsyncSession."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock AsyncSession."""
        session = AsyncMock()
        # session.add is synchronous in real AsyncSession
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repo(self, mock_session: AsyncMock) -> BaseRepository[Base]:
        """Create a BaseRepository with a mock session."""
        return BaseRepository(session=mock_session, model_class=MemoryORM)

    @pytest.mark.asyncio
    async def test_get_by_id_calls_session_get(
        self, repo: BaseRepository[Base], mock_session: AsyncMock
    ) -> None:
        """get_by_id must call session.get with model_class and id."""
        test_id = uuid4()
        mock_session.get.return_value = None

        result = await repo.get_by_id(test_id)

        mock_session.get.assert_awaited_once_with(MemoryORM, test_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_adds_to_session(
        self, repo: BaseRepository[Base], mock_session: AsyncMock
    ) -> None:
        """create must call session.add with the new instance."""
        await repo.create(
            team_id=uuid4(),
            memory_type="semantic",
            content="test content",
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing(
        self, repo: BaseRepository[Base], mock_session: AsyncMock
    ) -> None:
        """delete must return False when session.get returns None."""
        test_id = uuid4()
        mock_session.get.return_value = None

        result = await repo.delete(test_id)

        assert result is False
        mock_session.delete.assert_not_awaited()
        mock_session.flush.assert_not_awaited()
