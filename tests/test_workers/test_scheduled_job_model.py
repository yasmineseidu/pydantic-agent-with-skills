"""Unit tests for ScheduledJobORM model structure (no database required).

Validates table registration, column names, foreign keys, indexes,
and basic ORM instantiation by inspecting Base.metadata.
"""

from uuid import uuid4

import pytest

from src.db.base import Base

# Force all models to register with Base.metadata
import src.db.models  # noqa: F401
from src.db.models.scheduled_job import ScheduledJobORM


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


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScheduledJobColumns:
    """Validate scheduled_job table columns."""

    EXPECTED = {
        "id",
        "team_id",
        "agent_id",
        "user_id",
        "name",
        "message",
        "cron_expression",
        "timezone",
        "is_active",
        "last_run_at",
        "next_run_at",
        "run_count",
        "consecutive_failures",
        "last_error",
        "delivery_config",
        "created_at",
        "updated_at",
    }

    def test_scheduled_job_table_exists(self) -> None:
        """scheduled_job table must be registered in Base.metadata."""
        assert "scheduled_job" in Base.metadata.tables

    def test_scheduled_job_tablename(self) -> None:
        """ScheduledJobORM.__tablename__ must be 'scheduled_job'."""
        assert ScheduledJobORM.__tablename__ == "scheduled_job"

    def test_scheduled_job_table_columns(self) -> None:
        """scheduled_job table must contain all 17 expected columns."""
        actual = _col_names("scheduled_job")
        assert self.EXPECTED == actual

    def test_column_count(self) -> None:
        """scheduled_job table must have exactly 17 columns."""
        actual = _col_names("scheduled_job")
        assert len(actual) == 17


# ---------------------------------------------------------------------------
# Foreign key tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScheduledJobForeignKeys:
    """Validate foreign key relationships on scheduled_job table."""

    def test_team_foreign_key(self) -> None:
        """scheduled_job must FK to team.id."""
        fks = _fk_target_tables("scheduled_job")
        assert "team.id" in fks

    def test_agent_foreign_key(self) -> None:
        """scheduled_job must FK to agent.id."""
        fks = _fk_target_tables("scheduled_job")
        assert "agent.id" in fks

    def test_user_foreign_key(self) -> None:
        """scheduled_job must FK to user.id."""
        fks = _fk_target_tables("scheduled_job")
        assert "user.id" in fks

    def test_foreign_key_count(self) -> None:
        """scheduled_job must have exactly 3 foreign keys."""
        fks = _fk_target_tables("scheduled_job")
        assert len(fks) == 3


# ---------------------------------------------------------------------------
# Index tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScheduledJobIndexes:
    """Validate indexes on scheduled_job table."""

    def test_idx_job_next_run_exists(self) -> None:
        """idx_job_next_run partial index must exist on next_run_at."""
        table = _table("scheduled_job")
        index_names = {idx.name for idx in table.indexes}
        assert "idx_job_next_run" in index_names

    def test_idx_job_team_exists(self) -> None:
        """idx_job_team index must exist on team_id."""
        table = _table("scheduled_job")
        index_names = {idx.name for idx in table.indexes}
        assert "idx_job_team" in index_names


# ---------------------------------------------------------------------------
# ORM instantiation tests (without DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScheduledJobInstantiation:
    """Test that ScheduledJobORM can be instantiated without a database."""

    def test_basic_instantiation(self) -> None:
        """ScheduledJobORM() should create an instance with required fields."""
        team_id = uuid4()
        agent_id = uuid4()
        user_id = uuid4()
        job = ScheduledJobORM(
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            name="Daily summary",
            message="Summarize today's activity",
            cron_expression="0 18 * * *",
        )
        assert job.team_id == team_id
        assert job.agent_id == agent_id
        assert job.user_id == user_id
        assert job.name == "Daily summary"
        assert job.message == "Summarize today's activity"
        assert job.cron_expression == "0 18 * * *"

    def test_nullable_fields_default_none(self) -> None:
        """Nullable fields should default to None when not provided."""
        job = ScheduledJobORM(
            team_id=uuid4(),
            agent_id=uuid4(),
            user_id=uuid4(),
            name="Test",
            message="Test message",
            cron_expression="* * * * *",
        )
        assert job.last_run_at is None
        assert job.next_run_at is None
        assert job.last_error is None

    def test_delivery_config_accepts_dict(self) -> None:
        """delivery_config should accept a dict (JSONB column)."""
        job = ScheduledJobORM(
            team_id=uuid4(),
            agent_id=uuid4(),
            user_id=uuid4(),
            name="Webhook Job",
            message="test",
            cron_expression="* * * * *",
            delivery_config={"webhook_url": "https://example.com"},
        )
        assert job.delivery_config == {"webhook_url": "https://example.com"}
