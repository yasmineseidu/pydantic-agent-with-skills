"""Unit tests for migration 005 phase9 integrations."""

import importlib


class TestMigration005:
    """Tests for phase 9 migration file."""

    def test_revision_chain(self) -> None:
        """Test migration has correct revision identifiers."""
        mod = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert mod.revision == "005"
        assert mod.down_revision == "004"

    def test_upgrade_function_exists(self) -> None:
        """Test upgrade function is defined."""
        mod = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert callable(mod.upgrade)

    def test_downgrade_function_exists(self) -> None:
        """Test downgrade function is defined."""
        mod = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert callable(mod.downgrade)

    def test_branch_labels_none(self) -> None:
        """Test branch_labels is None."""
        mod = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert mod.branch_labels is None

    def test_depends_on_none(self) -> None:
        """Test depends_on is None."""
        mod = importlib.import_module("src.db.migrations.versions.005_phase9_integrations")
        assert mod.depends_on is None
