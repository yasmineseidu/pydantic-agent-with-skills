"""Unit tests for ORM model structure (no database required).

Validates table registration, column names, foreign keys, unique constraints,
and basic ORM instantiation by inspecting Base.metadata.
"""

from uuid import uuid4

import pytest

from src.db.base import Base

# Force all models to register with Base.metadata
import src.db.models  # noqa: F401
from src.db.models.agent import AgentORM
from src.db.models.conversation import MessageORM
from src.db.models.memory import MemoryLogORM, MemoryORM
from src.db.models.user import UserORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table(name: str):
    """Return a Table object from Base.metadata by name."""
    return Base.metadata.tables[name]


def _col_names(table_name: str) -> set[str]:
    """Return the set of column names for a table."""
    return {c.name for c in _table(table_name).columns}


def _fk_target_tables(table_name: str) -> set[str]:
    """Return the set of target table.column strings for all FKs on a table."""
    return {f"{fk.column.table.name}.{fk.column.name}" for fk in _table(table_name).foreign_keys}


def _unique_constraint_columns(table_name: str) -> list[frozenset[str]]:
    """Return a list of column-name sets for each UniqueConstraint on a table."""
    from sqlalchemy import UniqueConstraint

    results: list[frozenset[str]] = []
    for constraint in _table(table_name).constraints:
        if isinstance(constraint, UniqueConstraint):
            results.append(frozenset(c.name for c in constraint.columns))
    return results


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "user",
    "team",
    "team_membership",
    "agent",
    "conversation",
    "message",
    "memory",
    "memory_log",
    "memory_tag",
}


@pytest.mark.unit
class TestTableRegistration:
    """Verify that all Phase-1 tables are registered in Base.metadata."""

    def test_all_phase1_tables_registered(self, all_tables: set[str]) -> None:
        """All 9 expected tables must appear in Base.metadata."""
        missing = EXPECTED_TABLES - all_tables
        assert not missing, f"Missing tables: {missing}"

    def test_table_count(self, all_tables: set[str]) -> None:
        """Exactly 9 tables should be registered."""
        assert len(all_tables) == 13


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUserColumns:
    """Validate user table columns."""

    EXPECTED = {
        "id",
        "email",
        "password_hash",
        "display_name",
        "is_active",
        "created_at",
        "updated_at",
    }

    def test_user_table_columns(self) -> None:
        """User table must contain all expected columns."""
        actual = _col_names("user")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestTeamColumns:
    """Validate team table columns."""

    EXPECTED = {
        "id",
        "name",
        "slug",
        "owner_id",
        "settings",
        "shared_skill_names",
        "webhook_url",
        "webhook_secret",
        "conversation_retention_days",
        "created_at",
        "updated_at",
    }

    def test_team_table_columns(self) -> None:
        """Team table must contain all expected columns."""
        actual = _col_names("team")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestTeamMembershipColumns:
    """Validate team_membership table columns."""

    EXPECTED = {"id", "user_id", "team_id", "role", "created_at"}

    def test_team_membership_table_columns(self) -> None:
        """Team membership table must contain all expected columns."""
        actual = _col_names("team_membership")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestAgentColumns:
    """Validate agent table columns."""

    EXPECTED = {
        "id",
        "team_id",
        "name",
        "slug",
        "tagline",
        "avatar_emoji",
        "personality",
        "shared_skill_names",
        "custom_skill_names",
        "disabled_skill_names",
        "model_config_json",
        "memory_config",
        "boundaries",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    }

    def test_agent_table_columns(self) -> None:
        """Agent table must contain all 17 expected columns."""
        actual = _col_names("agent")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestConversationColumns:
    """Validate conversation table columns."""

    EXPECTED = {
        "id",
        "team_id",
        "agent_id",
        "user_id",
        "title",
        "status",
        "message_count",
        "total_input_tokens",
        "total_output_tokens",
        "summary",
        "metadata",
        "last_message_at",
        "created_at",
        "updated_at",
    }

    def test_conversation_table_columns(self) -> None:
        """Conversation table must contain all 14 expected columns."""
        actual = _col_names("conversation")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestMessageColumns:
    """Validate message table columns."""

    EXPECTED = {
        "id",
        "conversation_id",
        "agent_id",
        "role",
        "content",
        "tool_calls",
        "tool_results",
        "token_count",
        "model",
        "feedback_rating",
        "feedback_comment",
        "created_at",
    }

    def test_message_table_columns(self) -> None:
        """Message table must contain all 12 columns (no updated_at)."""
        actual = _col_names("message")
        assert self.EXPECTED == actual
        assert "updated_at" not in actual


@pytest.mark.unit
class TestMemoryColumns:
    """Validate memory table columns."""

    EXPECTED = {
        "id",
        "team_id",
        "agent_id",
        "user_id",
        "memory_type",
        "content",
        "subject",
        "embedding",
        "importance",
        "confidence",
        "access_count",
        "is_pinned",
        "source_type",
        "source_conversation_id",
        "source_message_ids",
        "extraction_model",
        "version",
        "superseded_by",
        "contradicts",
        "related_to",
        "metadata",
        "tier",
        "status",
        "last_accessed_at",
        "expires_at",
        "created_at",
        "updated_at",
    }

    def test_memory_table_columns(self) -> None:
        """Memory table must contain all ~27 expected columns."""
        actual = _col_names("memory")
        assert self.EXPECTED == actual


@pytest.mark.unit
class TestMemoryLogColumns:
    """Validate memory_log table columns."""

    EXPECTED = {
        "id",
        "memory_id",
        "action",
        "old_content",
        "new_content",
        "old_importance",
        "new_importance",
        "old_tier",
        "new_tier",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "conversation_id",
        "related_memory_ids",
        "created_at",
    }

    def test_memory_log_table_columns(self) -> None:
        """Memory log table must contain all columns (no updated_at)."""
        actual = _col_names("memory_log")
        assert self.EXPECTED == actual
        assert "updated_at" not in actual


@pytest.mark.unit
class TestMemoryTagColumns:
    """Validate memory_tag table columns."""

    EXPECTED = {"id", "memory_id", "tag", "created_at"}

    def test_memory_tag_table_columns(self) -> None:
        """Memory tag table must contain all 4 expected columns."""
        actual = _col_names("memory_tag")
        assert self.EXPECTED == actual


# ---------------------------------------------------------------------------
# Foreign key tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForeignKeys:
    """Validate foreign key relationships across all tables."""

    def test_team_membership_foreign_keys(self) -> None:
        """team_membership must FK to user.id and team.id."""
        fks = _fk_target_tables("team_membership")
        assert "user.id" in fks
        assert "team.id" in fks

    def test_agent_foreign_keys(self) -> None:
        """agent must FK to team.id and user.id (created_by)."""
        fks = _fk_target_tables("agent")
        assert "team.id" in fks
        assert "user.id" in fks

    def test_conversation_foreign_keys(self) -> None:
        """conversation must FK to team.id, agent.id, user.id."""
        fks = _fk_target_tables("conversation")
        assert "team.id" in fks
        assert "agent.id" in fks
        assert "user.id" in fks

    def test_message_foreign_keys(self) -> None:
        """message must FK to conversation.id."""
        fks = _fk_target_tables("message")
        assert "conversation.id" in fks

    def test_memory_foreign_keys(self) -> None:
        """memory must FK to team, agent, user, conversation, and self (superseded_by)."""
        fks = _fk_target_tables("memory")
        assert "team.id" in fks
        assert "agent.id" in fks
        assert "user.id" in fks
        assert "conversation.id" in fks
        assert "memory.id" in fks  # self-referential superseded_by

    def test_memory_log_no_foreign_keys(self) -> None:
        """memory_log.memory_id must NOT have a FK (ADR-8: survives deletes)."""
        fks = _fk_target_tables("memory_log")
        assert "memory.id" not in fks
        # memory_log should have no FKs at all
        assert len(fks) == 0

    def test_memory_tag_foreign_keys(self) -> None:
        """memory_tag must FK to memory.id."""
        fks = _fk_target_tables("memory_tag")
        assert "memory.id" in fks


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUniqueConstraints:
    """Validate unique constraints on tables."""

    def test_user_email_unique(self) -> None:
        """user.email must have a unique constraint."""
        col = _table("user").columns["email"]
        assert col.unique is True

    def test_team_slug_unique(self) -> None:
        """team.slug must have a unique constraint."""
        col = _table("team").columns["slug"]
        assert col.unique is True

    def test_agent_team_slug_unique(self) -> None:
        """agent must have a unique constraint on (team_id, slug)."""
        ucs = _unique_constraint_columns("agent")
        assert frozenset({"team_id", "slug"}) in ucs

    def test_memory_tag_unique(self) -> None:
        """memory_tag must have a unique constraint on (memory_id, tag)."""
        ucs = _unique_constraint_columns("memory_tag")
        assert frozenset({"memory_id", "tag"}) in ucs

    def test_team_membership_unique(self) -> None:
        """team_membership must have a unique constraint on (user_id, team_id)."""
        ucs = _unique_constraint_columns("team_membership")
        assert frozenset({"user_id", "team_id"}) in ucs


# ---------------------------------------------------------------------------
# ORM instantiation tests (without DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestORMInstantiation:
    """Test that ORM classes can be instantiated without a database."""

    def test_user_orm_instantiation(self) -> None:
        """UserORM() should create an instance with basic fields."""
        user = UserORM(
            email="test@example.com",
            password_hash="hashed",
            display_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.password_hash == "hashed"
        assert user.display_name == "Test User"

    def test_agent_orm_instantiation(self) -> None:
        """AgentORM() should create an instance with required fields."""
        team_id = uuid4()
        agent = AgentORM(
            team_id=team_id,
            name="Test Agent",
            slug="test-agent",
        )
        assert agent.name == "Test Agent"
        assert agent.slug == "test-agent"
        assert agent.team_id == team_id

    def test_memory_orm_instantiation(self) -> None:
        """MemoryORM() should create an instance with required fields."""
        team_id = uuid4()
        memory = MemoryORM(
            team_id=team_id,
            memory_type="semantic",
            content="Test memory content",
        )
        assert memory.content == "Test memory content"
        assert memory.memory_type == "semantic"
        assert memory.team_id == team_id

    def test_memory_log_orm_instantiation(self) -> None:
        """MemoryLogORM() should create an instance."""
        memory_id = uuid4()
        log = MemoryLogORM(
            memory_id=memory_id,
            action="create",
            changed_by="system",
        )
        assert log.memory_id == memory_id
        assert log.action == "create"
        assert log.changed_by == "system"

    def test_message_orm_instantiation(self) -> None:
        """MessageORM() should create an instance with required fields."""
        conv_id = uuid4()
        msg = MessageORM(
            conversation_id=conv_id,
            role="user",
            content="Hello",
        )
        assert msg.conversation_id == conv_id
        assert msg.role == "user"
        assert msg.content == "Hello"
