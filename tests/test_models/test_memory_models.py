"""Unit tests for memory, conversation, and user models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.conversation_models import (
    ConversationCreate,
    ConversationStatus,
    MessageRole,
)
from src.models.memory_models import (
    MemoryCreate,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemorySource,
    MemoryStatus,
    MemoryTier,
    MemoryType,
)
from src.models.user_models import (
    TeamCreate,
    UserCreate,
    UserRole,
)


class TestMemoryType:
    """Tests for MemoryType enum."""

    @pytest.mark.unit
    def test_memory_type_values(self) -> None:
        """Test that all 7 enum values exist."""
        assert MemoryType.SEMANTIC == "semantic"
        assert MemoryType.EPISODIC == "episodic"
        assert MemoryType.PROCEDURAL == "procedural"
        assert MemoryType.AGENT_PRIVATE == "agent_private"
        assert MemoryType.SHARED == "shared"
        assert MemoryType.IDENTITY == "identity"
        assert MemoryType.USER_PROFILE == "user_profile"
        assert len(MemoryType) == 7


class TestMemoryStatus:
    """Tests for MemoryStatus enum."""

    @pytest.mark.unit
    def test_memory_status_values(self) -> None:
        """Test that all 4 enum values exist."""
        assert MemoryStatus.ACTIVE == "active"
        assert MemoryStatus.SUPERSEDED == "superseded"
        assert MemoryStatus.ARCHIVED == "archived"
        assert MemoryStatus.DISPUTED == "disputed"
        assert len(MemoryStatus) == 4


class TestMemoryTier:
    """Tests for MemoryTier enum."""

    @pytest.mark.unit
    def test_memory_tier_values(self) -> None:
        """Test that all 3 enum values exist."""
        assert MemoryTier.HOT == "hot"
        assert MemoryTier.WARM == "warm"
        assert MemoryTier.COLD == "cold"
        assert len(MemoryTier) == 3


class TestMemorySource:
    """Tests for MemorySource enum."""

    @pytest.mark.unit
    def test_memory_source_values(self) -> None:
        """Test that all 6 enum values exist."""
        assert MemorySource.EXTRACTION == "extraction"
        assert MemorySource.EXPLICIT == "explicit"
        assert MemorySource.SYSTEM == "system"
        assert MemorySource.FEEDBACK == "feedback"
        assert MemorySource.CONSOLIDATION == "consolidation"
        assert MemorySource.COMPACTION == "compaction"
        assert len(MemorySource) == 6


class TestMemoryCreate:
    """Tests for MemoryCreate model."""

    @pytest.mark.unit
    def test_memory_create_defaults(self) -> None:
        """Test defaults: importance=5, confidence=1.0."""
        mem = MemoryCreate(
            team_id=uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content="Test memory",
        )
        assert mem.importance == 5
        assert mem.confidence == 1.0
        assert mem.source_type == MemorySource.EXTRACTION
        assert mem.agent_id is None
        assert mem.user_id is None
        assert mem.subject is None
        assert mem.source_message_ids == []
        assert mem.metadata == {}

    @pytest.mark.unit
    def test_memory_create_importance_too_low(self) -> None:
        """Test that importance < 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                team_id=uuid4(),
                memory_type=MemoryType.SEMANTIC,
                content="Test",
                importance=0,
            )

    @pytest.mark.unit
    def test_memory_create_importance_too_high(self) -> None:
        """Test that importance > 10 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                team_id=uuid4(),
                memory_type=MemoryType.SEMANTIC,
                content="Test",
                importance=11,
            )

    @pytest.mark.unit
    def test_memory_create_confidence_too_low(self) -> None:
        """Test that confidence < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                team_id=uuid4(),
                memory_type=MemoryType.SEMANTIC,
                content="Test",
                confidence=-0.1,
            )

    @pytest.mark.unit
    def test_memory_create_confidence_too_high(self) -> None:
        """Test that confidence > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                team_id=uuid4(),
                memory_type=MemoryType.SEMANTIC,
                content="Test",
                confidence=1.1,
            )

    @pytest.mark.unit
    def test_memory_create_importance_boundaries(self) -> None:
        """Test that importance=1 and importance=10 are valid."""
        low = MemoryCreate(
            team_id=uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content="Test",
            importance=1,
        )
        high = MemoryCreate(
            team_id=uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content="Test",
            importance=10,
        )
        assert low.importance == 1
        assert high.importance == 10


class TestMemorySearchRequest:
    """Tests for MemorySearchRequest model."""

    @pytest.mark.unit
    def test_memory_search_request_defaults(self) -> None:
        """Test default limit=20."""
        req = MemorySearchRequest(team_id=uuid4(), query="test query")
        assert req.limit == 20
        assert req.agent_id is None
        assert req.memory_types == []

    @pytest.mark.unit
    def test_memory_search_request_limit_boundaries(self) -> None:
        """Test that limit=1 and limit=100 are valid."""
        low = MemorySearchRequest(team_id=uuid4(), query="test", limit=1)
        high = MemorySearchRequest(team_id=uuid4(), query="test", limit=100)
        assert low.limit == 1
        assert high.limit == 100

    @pytest.mark.unit
    def test_memory_search_request_limit_too_low(self) -> None:
        """Test that limit < 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemorySearchRequest(team_id=uuid4(), query="test", limit=0)

    @pytest.mark.unit
    def test_memory_search_request_limit_too_high(self) -> None:
        """Test that limit > 100 raises ValidationError."""
        with pytest.raises(ValidationError):
            MemorySearchRequest(team_id=uuid4(), query="test", limit=101)


class TestMemorySearchResult:
    """Tests for MemorySearchResult model."""

    @pytest.mark.unit
    def test_memory_search_result_creation(self) -> None:
        """Test creation with a MemoryRecord and similarity score."""
        now = datetime.now(tz=timezone.utc)
        record = MemoryRecord(
            id=uuid4(),
            team_id=uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content="Test memory",
            importance=5,
            confidence=1.0,
            source_type=MemorySource.EXTRACTION,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        )
        result = MemorySearchResult(memory=record, similarity=0.95)
        assert result.similarity == 0.95
        assert result.memory.content == "Test memory"

    @pytest.mark.unit
    def test_memory_search_result_similarity_boundaries(self) -> None:
        """Test that similarity=0.0 and similarity=1.0 are valid."""
        now = datetime.now(tz=timezone.utc)
        record = MemoryRecord(
            id=uuid4(),
            team_id=uuid4(),
            memory_type=MemoryType.SEMANTIC,
            content="Test",
            importance=5,
            confidence=1.0,
            source_type=MemorySource.EXTRACTION,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        )
        low = MemorySearchResult(memory=record, similarity=0.0)
        high = MemorySearchResult(memory=record, similarity=1.0)
        assert low.similarity == 0.0
        assert high.similarity == 1.0


class TestConversationStatus:
    """Tests for ConversationStatus enum."""

    @pytest.mark.unit
    def test_conversation_status_values(self) -> None:
        """Test that all 3 enum values exist."""
        assert ConversationStatus.ACTIVE == "active"
        assert ConversationStatus.IDLE == "idle"
        assert ConversationStatus.CLOSED == "closed"
        assert len(ConversationStatus) == 3


class TestMessageRole:
    """Tests for MessageRole enum."""

    @pytest.mark.unit
    def test_message_role_values(self) -> None:
        """Test that all 4 enum values exist."""
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.TOOL == "tool"
        assert len(MessageRole) == 4


class TestConversationCreate:
    """Tests for ConversationCreate model."""

    @pytest.mark.unit
    def test_conversation_create_required_fields(self) -> None:
        """Test that team_id, agent_id, user_id are required."""
        conv = ConversationCreate(
            team_id=uuid4(),
            agent_id=uuid4(),
            user_id=uuid4(),
        )
        assert conv.title is None

    @pytest.mark.unit
    def test_conversation_create_missing_fields(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            ConversationCreate(team_id=uuid4(), agent_id=uuid4())


class TestUserRole:
    """Tests for UserRole enum."""

    @pytest.mark.unit
    def test_user_role_values(self) -> None:
        """Test that all 4 enum values exist."""
        assert UserRole.OWNER == "owner"
        assert UserRole.ADMIN == "admin"
        assert UserRole.MEMBER == "member"
        assert UserRole.VIEWER == "viewer"
        assert len(UserRole) == 4


class TestUserCreate:
    """Tests for UserCreate model."""

    @pytest.mark.unit
    def test_user_create_required_fields(self) -> None:
        """Test that email, password, display_name are all required."""
        user = UserCreate(
            email="test@example.com",
            password="securepassword123",
            display_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"

    @pytest.mark.unit
    def test_user_create_missing_email(self) -> None:
        """Test that missing email raises ValidationError."""
        with pytest.raises(ValidationError):
            UserCreate(password="pass", display_name="Test")

    @pytest.mark.unit
    def test_user_create_missing_password(self) -> None:
        """Test that missing password raises ValidationError."""
        with pytest.raises(ValidationError):
            UserCreate(email="test@example.com", display_name="Test")

    @pytest.mark.unit
    def test_user_create_missing_display_name(self) -> None:
        """Test that missing display_name raises ValidationError."""
        with pytest.raises(ValidationError):
            UserCreate(email="test@example.com", password="pass")


class TestTeamCreate:
    """Tests for TeamCreate model."""

    @pytest.mark.unit
    def test_team_create_required_fields(self) -> None:
        """Test that name, slug, owner_id are all required."""
        team = TeamCreate(name="My Team", slug="my-team", owner_id=uuid4())
        assert team.name == "My Team"
        assert team.slug == "my-team"

    @pytest.mark.unit
    def test_team_create_missing_name(self) -> None:
        """Test that missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamCreate(slug="my-team", owner_id=uuid4())

    @pytest.mark.unit
    def test_team_create_missing_slug(self) -> None:
        """Test that missing slug raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamCreate(name="My Team", owner_id=uuid4())

    @pytest.mark.unit
    def test_team_create_missing_owner_id(self) -> None:
        """Test that missing owner_id raises ValidationError."""
        with pytest.raises(ValidationError):
            TeamCreate(name="My Team", slug="my-team")
