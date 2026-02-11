"""Tests for Phase 9 platform integration migration structure."""

from __future__ import annotations

import importlib
import inspect


def _get_migration_source() -> str:
    """Import migration 005 and return its source code."""
    migration = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
    return inspect.getsource(migration)


class TestMigration005RevisionChain:
    """Tests for migration 005 revision identifiers."""

    def test_revision_is_005(self) -> None:
        """Test migration has correct revision ID."""
        migration = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert migration.revision == "005"

    def test_down_revision_is_004(self) -> None:
        """Test migration chains from 004."""
        migration = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert migration.down_revision == "004"


class TestMigration005Upgrade:
    """Tests for migration 005 upgrade() content."""

    def test_creates_platform_connection_table(self) -> None:
        """Test upgrade creates platform_connection table."""
        source = _get_migration_source()
        assert "platform_connection" in source

    def test_creates_webhook_delivery_log_table(self) -> None:
        """Test upgrade creates webhook_delivery_log table."""
        source = _get_migration_source()
        assert "webhook_delivery_log" in source

    def test_creates_platform_type_enum(self) -> None:
        """Test upgrade creates platform_type ENUM."""
        source = _get_migration_source()
        assert "platform_type" in source
        assert "'telegram'" in source
        assert "'slack'" in source
        assert "'discord'" in source
        assert "'whatsapp'" in source

    def test_creates_platform_status_enum(self) -> None:
        """Test upgrade creates platform_status ENUM."""
        source = _get_migration_source()
        assert "platform_status" in source
        assert "'active'" in source
        assert "'paused'" in source
        assert "'error'" in source
        assert "'disconnected'" in source

    def test_creates_indexes(self) -> None:
        """Test upgrade creates expected indexes."""
        source = _get_migration_source()
        assert "idx_platform_team" in source
        assert "idx_platform_external" in source
        assert "idx_webhook_team" in source
        assert "idx_webhook_pending" in source

    def test_creates_unique_constraints(self) -> None:
        """Test upgrade creates unique constraints."""
        source = _get_migration_source()
        assert "uq_platform_agent" in source
        assert "uq_webhook_event_id" in source

    def test_creates_updated_at_trigger(self) -> None:
        """Test upgrade creates updated_at trigger for platform_connection."""
        source = _get_migration_source()
        assert "set_updated_at_platform_connection" in source
        assert "trigger_set_updated_at" in source


class TestMigration005Downgrade:
    """Tests for migration 005 downgrade() content."""

    def test_downgrade_drops_tables(self) -> None:
        """Test downgrade drops both tables."""
        source = _get_migration_source()
        assert "drop_table" in source

    def test_downgrade_drops_enums(self) -> None:
        """Test downgrade drops both ENUM types."""
        source = _get_migration_source()
        assert "DROP TYPE platform_status" in source
        assert "DROP TYPE platform_type" in source

    def test_has_upgrade_and_downgrade(self) -> None:
        """Test migration defines both upgrade() and downgrade() functions."""
        migration = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert callable(getattr(migration, "upgrade", None))
        assert callable(getattr(migration, "downgrade", None))
