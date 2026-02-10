"""Comprehensive tests for memory CRUD and search endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID


class MockMemoryORM:
    """Mock MemoryORM for testing."""

    def __init__(
        self,
        memory_id: UUID,
        team_id: UUID,
        agent_id: UUID | None = None,
        user_id: UUID | None = None,
        memory_type: str = "semantic",
        content: str = "Test memory content",
        subject: str | None = None,
        importance: int = 5,
        confidence: float = 0.9,
        is_pinned: bool = False,
        status: str = "active",
        tier: str = "warm",
        access_count: int = 0,
        version: int = 1,
        superseded_by: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        """Initialize mock memory."""
        self.id = memory_id
        self.team_id = team_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.memory_type = memory_type
        self.content = content
        self.subject = subject
        self.importance = importance
        self.confidence = confidence
        self.is_pinned = is_pinned
        self.status = status
        self.tier = tier
        self.access_count = access_count
        self.version = version
        self.superseded_by = superseded_by
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)


class TestListMemories:
    """Tests for GET /v1/memories endpoint."""

    @pytest.mark.asyncio
    async def test_list_memories_empty(self, auth_client, db_session, test_team_id) -> None:
        """List memories returns empty list when no memories exist."""
        # Mock count query - scalar() must return int synchronously
        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        # Mock MemoryRepository.get_by_team (empty)
        with patch("src.api.routers.memories.MemoryRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_by_team = AsyncMock(return_value=[])
            mock_repo_class.return_value = mock_repo

            db_session.execute = AsyncMock(return_value=count_mock)

            response = await auth_client.get("/v1/memories")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["items"] == []
            assert data["limit"] == 20
            assert data["offset"] == 0
            assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_memories_with_pagination(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """List memories respects limit and offset parameters."""
        memory1 = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            content="First memory",
        )

        # Mock count query - scalar() must return int synchronously
        count_mock = MagicMock()
        count_mock.scalar.return_value = 5

        # Mock MemoryRepository.get_by_team (with one memory)
        with patch("src.api.routers.memories.MemoryRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_by_team = AsyncMock(return_value=[memory1])
            mock_repo_class.return_value = mock_repo

            db_session.execute = AsyncMock(return_value=count_mock)

            response = await auth_client.get("/v1/memories?limit=1&offset=0")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 5
            assert len(data["items"]) == 1
            assert data["limit"] == 1
            assert data["offset"] == 0
            assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_list_memories_filter_by_memory_type(
        self, auth_client, db_session, test_team_id
    ) -> None:
        """List memories filters by memory_type parameter."""
        memory = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            memory_type="episodic",
        )

        # Mock count query - scalar() must return int synchronously via MagicMock
        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        # Mock MemoryRepository.get_by_team
        with patch("src.api.routers.memories.MemoryRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_by_team = AsyncMock(return_value=[memory])
            mock_repo_class.return_value = mock_repo

            db_session.execute = AsyncMock(return_value=count_mock)

            response = await auth_client.get("/v1/memories?memory_type=episodic")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["memory_type"] == "episodic"

    @pytest.mark.asyncio
    async def test_list_memories_invalid_memory_type_raises_error(
        self, auth_client, db_session
    ) -> None:
        """List memories returns 400 for invalid memory_type."""
        response = await auth_client.get("/v1/memories?memory_type=invalid_type")
        assert response.status_code == 400
        assert "Invalid memory_type" in response.json()["detail"]


class TestCreateMemory:
    """Tests for POST /v1/memories endpoint."""

    @pytest.mark.asyncio
    async def test_create_memory_success(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Create memory returns 201 with created memory."""
        # Mock EmbeddingService
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embedding_service = AsyncMock()
            mock_embedding_service.embed_single = AsyncMock(return_value=[0.1] * 1536)
            mock_embed_fn.return_value = mock_embedding_service

            # Mock MemoryAuditLog
            with patch("src.api.routers.memories.MemoryAuditLog") as mock_audit_class:
                mock_audit = AsyncMock()
                mock_audit.log_event = AsyncMock()
                mock_audit_class.return_value = mock_audit

                # Mock db.flush, db.refresh — refresh populates ORM attributes
                db_session.flush = AsyncMock()
                db_session.commit = AsyncMock()

                # db.refresh needs to set the id on the memory object
                async def fake_refresh(obj):
                    if not hasattr(obj, "id") or obj.id is None:
                        obj.id = UUID("33333333-3333-3333-3333-333333333333")
                    if not hasattr(obj, "created_at") or obj.created_at is None:
                        obj.created_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "updated_at") or obj.updated_at is None:
                        obj.updated_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "access_count") or obj.access_count is None:
                        obj.access_count = 0
                    if not hasattr(obj, "is_pinned") or obj.is_pinned is None:
                        obj.is_pinned = False

                db_session.refresh = AsyncMock(side_effect=fake_refresh)

                request_body = {
                    "content": "Remember this important fact",
                    "memory_type": "semantic",
                    "importance": 8,
                    "subject": "Testing",
                    "agent_id": str(UUID("22222222-2222-2222-2222-222222222222")),
                }

                response = await auth_client.post("/v1/memories", json=request_body)

                assert response.status_code == 201
                data = response.json()
                assert data["content"] == "Remember this important fact"
                assert data["importance"] == 8
                assert data["status"] == "active"
                assert data["tier"] == "warm"

    @pytest.mark.asyncio
    async def test_create_memory_invalid_memory_type_400(self, auth_client, db_session) -> None:
        """Create memory returns 400 for invalid memory_type."""
        request_body = {
            "content": "Test content",
            "memory_type": "invalid_type",
        }

        response = await auth_client.post("/v1/memories", json=request_body)

        assert response.status_code == 400
        data = response.json()
        assert "Invalid memory_type" in data["detail"]

    @pytest.mark.asyncio
    async def test_create_memory_embedding_service_unavailable_continues(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Create memory continues without embedding if service fails."""
        # Mock EmbeddingService to raise exception
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embedding_service = AsyncMock()
            mock_embedding_service.embed_single = AsyncMock(
                side_effect=Exception("Embedding service down")
            )
            mock_embed_fn.return_value = mock_embedding_service

            # Mock MemoryAuditLog
            with patch("src.api.routers.memories.MemoryAuditLog") as mock_audit_class:
                mock_audit = AsyncMock()
                mock_audit.log_event = AsyncMock()
                mock_audit_class.return_value = mock_audit

                db_session.flush = AsyncMock()
                db_session.commit = AsyncMock()

                # db.refresh needs to set the id on the memory object
                async def fake_refresh(obj):
                    if not hasattr(obj, "id") or obj.id is None:
                        obj.id = UUID("33333333-3333-3333-3333-333333333333")
                    if not hasattr(obj, "created_at") or obj.created_at is None:
                        obj.created_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "updated_at") or obj.updated_at is None:
                        obj.updated_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "access_count") or obj.access_count is None:
                        obj.access_count = 0
                    if not hasattr(obj, "is_pinned") or obj.is_pinned is None:
                        obj.is_pinned = False

                db_session.refresh = AsyncMock(side_effect=fake_refresh)

                request_body = {
                    "content": "Test content",
                    "memory_type": "semantic",
                }

                response = await auth_client.post("/v1/memories", json=request_body)

                # Should still succeed (graceful degradation)
                assert response.status_code == 201


class TestSearchMemories:
    """Tests for POST /v1/memories/search endpoint."""

    @pytest.mark.asyncio
    async def test_search_memories_success(self, auth_client, db_session, test_team_id) -> None:
        """Search memories returns results ranked by relevance."""
        memory1 = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            content="Python programming tips",
        )

        # Mock EmbeddingService
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embedding_service = AsyncMock()
            mock_embedding_service.embed_single = AsyncMock(return_value=[0.1] * 1536)
            mock_embed_fn.return_value = mock_embedding_service

            # Mock MemoryRepository.search_by_embedding
            with patch("src.api.routers.memories.MemoryRepository") as mock_repo_class:
                mock_repo = AsyncMock()
                # Returns list of (memory, score) tuples
                mock_repo.search_by_embedding = AsyncMock(return_value=[(memory1, 0.95)])
                mock_repo_class.return_value = mock_repo

                request_body = {
                    "query": "Python tips",
                    "limit": 10,
                }

                response = await auth_client.post("/v1/memories/search", json=request_body)

                assert response.status_code == 200
                data = response.json()
                assert data["query"] == "Python tips"
                assert data["total"] == 1
                assert len(data["memories"]) == 1
                assert data["memories"][0]["content"] == "Python programming tips"

    @pytest.mark.asyncio
    async def test_search_memories_empty_results(
        self, auth_client, db_session, test_team_id
    ) -> None:
        """Search memories returns empty list when no matches."""
        # Mock EmbeddingService
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embedding_service = AsyncMock()
            mock_embedding_service.embed_single = AsyncMock(return_value=[0.1] * 1536)
            mock_embed_fn.return_value = mock_embedding_service

            # Mock MemoryRepository.search_by_embedding (empty results)
            with patch("src.api.routers.memories.MemoryRepository") as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo.search_by_embedding = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                request_body = {
                    "query": "Nonexistent topic",
                }

                response = await auth_client.post("/v1/memories/search", json=request_body)

                assert response.status_code == 200
                data = response.json()
                assert data["total"] == 0
                assert len(data["memories"]) == 0

    @pytest.mark.asyncio
    async def test_search_memories_embedding_service_unavailable_503(
        self, auth_client, db_session
    ) -> None:
        """Search memories returns 503 when embedding service unavailable."""
        # Mock EmbeddingService to return None
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embed_fn.return_value = None

            request_body = {
                "query": "Test query",
            }

            response = await auth_client.post("/v1/memories/search", json=request_body)

            assert response.status_code == 503
            data = response.json()
            assert "Embedding service not configured" in data["detail"]


class TestDeleteMemory:
    """Tests for DELETE /v1/memories/{memory_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_memory_soft_delete_success(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Delete memory performs soft delete (status=archived, tier=cold)."""
        memory = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            status="active",
            tier="warm",
        )

        # Mock select query to find memory — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = memory
        db_session.execute = AsyncMock(return_value=result_mock)

        # Mock MemoryAuditLog
        with patch("src.api.routers.memories.MemoryAuditLog") as mock_audit_class:
            mock_audit = AsyncMock()
            mock_audit.log_event = AsyncMock()
            mock_audit_class.return_value = mock_audit

            db_session.commit = AsyncMock()

            response = await auth_client.delete("/v1/memories/11111111-1111-1111-1111-111111111111")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Memory deleted successfully"
            assert "memory_id" in data["data"]

            # Verify soft delete applied
            assert memory.status == "archived"
            assert memory.tier == "cold"

    @pytest.mark.asyncio
    async def test_delete_memory_not_found_404(self, auth_client, db_session, test_team_id) -> None:
        """Delete memory returns 404 if memory not found."""
        # Mock select query to return None — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=result_mock)

        response = await auth_client.delete("/v1/memories/11111111-1111-1111-1111-111111111111")

        assert response.status_code == 404
        data = response.json()
        assert "Memory not found" in data["detail"]


class TestTogglePinMemory:
    """Tests for POST /v1/memories/{memory_id}/pin endpoint."""

    @pytest.mark.asyncio
    async def test_toggle_pin_memory_success(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Toggle pin changes is_pinned status."""
        memory = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            is_pinned=False,
        )

        # Mock select query to find memory — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = memory
        db_session.execute = AsyncMock(return_value=result_mock)

        # Mock MemoryAuditLog
        with patch("src.api.routers.memories.MemoryAuditLog") as mock_audit_class:
            mock_audit = AsyncMock()
            mock_audit.log_event = AsyncMock()
            mock_audit_class.return_value = mock_audit

            db_session.commit = AsyncMock()
            db_session.refresh = AsyncMock()

            response = await auth_client.post(
                "/v1/memories/11111111-1111-1111-1111-111111111111/pin"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_pinned"] is True

    @pytest.mark.asyncio
    async def test_toggle_pin_memory_not_found_404(
        self, auth_client, db_session, test_team_id
    ) -> None:
        """Toggle pin returns 404 if memory not found."""
        # Mock select query to return None — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=result_mock)

        response = await auth_client.post("/v1/memories/11111111-1111-1111-1111-111111111111/pin")

        assert response.status_code == 404
        data = response.json()
        assert "Memory not found" in data["detail"]


class TestCorrectMemory:
    """Tests for POST /v1/memories/{memory_id}/correct endpoint."""

    @pytest.mark.asyncio
    async def test_correct_memory_creates_correction(
        self, auth_client, db_session, test_team_id, test_user_id
    ) -> None:
        """Correct memory creates new version and supersedes original."""
        original_memory = MockMemoryORM(
            memory_id=UUID("11111111-1111-1111-1111-111111111111"),
            team_id=test_team_id,
            content="Original content",
            version=1,
            status="active",
            tier="warm",
        )

        # Mock select query to find original memory — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = original_memory
        db_session.execute = AsyncMock(return_value=result_mock)

        # Mock EmbeddingService
        with patch("src.api.routers.memories._get_embedding_service") as mock_embed_fn:
            mock_embedding_service = AsyncMock()
            mock_embedding_service.embed_single = AsyncMock(return_value=[0.1] * 1536)
            mock_embed_fn.return_value = mock_embedding_service

            # Mock MemoryAuditLog
            with patch("src.api.routers.memories.MemoryAuditLog") as mock_audit_class:
                mock_audit = AsyncMock()
                mock_audit.log_event = AsyncMock()
                mock_audit_class.return_value = mock_audit

                db_session.flush = AsyncMock()
                db_session.commit = AsyncMock()

                # db.refresh needs to set the id on the corrected memory object
                async def fake_refresh(obj):
                    if not hasattr(obj, "id") or obj.id is None:
                        obj.id = UUID("44444444-4444-4444-4444-444444444444")
                    if not hasattr(obj, "created_at") or obj.created_at is None:
                        obj.created_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "updated_at") or obj.updated_at is None:
                        obj.updated_at = datetime.now(timezone.utc)
                    if not hasattr(obj, "access_count") or obj.access_count is None:
                        obj.access_count = 0
                    if not hasattr(obj, "is_pinned") or obj.is_pinned is None:
                        obj.is_pinned = False

                db_session.refresh = AsyncMock(side_effect=fake_refresh)

                request_body = {
                    "content": "Corrected content",
                    "memory_type": "semantic",
                    "importance": 8,
                }

                response = await auth_client.post(
                    "/v1/memories/11111111-1111-1111-1111-111111111111/correct",
                    json=request_body,
                )

                assert response.status_code == 201
                data = response.json()
                assert data["content"] == "Corrected content"
                assert data["status"] == "active"

                # Verify original memory was superseded
                assert original_memory.status == "superseded"
                assert original_memory.tier == "cold"

    @pytest.mark.asyncio
    async def test_correct_memory_not_found_404(
        self, auth_client, db_session, test_team_id
    ) -> None:
        """Correct memory returns 404 if original memory not found."""
        # Mock select query to return None — use MagicMock (scalar_one_or_none is sync)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=result_mock)

        request_body = {
            "content": "Corrected content",
            "memory_type": "semantic",
        }

        response = await auth_client.post(
            "/v1/memories/11111111-1111-1111-1111-111111111111/correct",
            json=request_body,
        )

        assert response.status_code == 404
        data = response.json()
        assert "Memory not found" in data["detail"]


class TestAuthenticationRequired:
    """Tests for authentication requirements on memory endpoints.

    When the ``get_current_user`` override is removed and no Authorization
    header is sent, FastAPI returns 422 (missing required header) because
    ``get_current_user`` declares ``authorization: str = Header(...)``.
    These tests verify that unauthenticated requests are rejected.
    """

    @pytest.mark.asyncio
    async def test_list_memories_without_auth_401(self, app, client) -> None:
        """List memories requires authentication."""
        import src.auth.dependencies

        # Remove the get_current_user override so auth is actually required
        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        response = await client.get("/v1/memories")
        # 422: FastAPI rejects the missing required Authorization header
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_memory_without_auth_401(self, app, client) -> None:
        """Create memory requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        response = await client.post(
            "/v1/memories",
            json={"content": "Test", "memory_type": "semantic"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_memories_without_auth_401(self, app, client) -> None:
        """Search memories requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        response = await client.post(
            "/v1/memories/search",
            json={"query": "test"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_memory_without_auth_401(self, app, client) -> None:
        """Delete memory requires authentication."""
        import src.auth.dependencies

        app.dependency_overrides.pop(src.auth.dependencies.get_current_user, None)

        response = await client.delete("/v1/memories/11111111-1111-1111-1111-111111111111")
        assert response.status_code == 422
