"""Tests for Phase 7 collaboration migration structure."""

from __future__ import annotations

import inspect
import importlib


def test_migration_contains_expected_tables() -> None:
    """Migration should reference all Phase 7 tables."""
    migration = importlib.import_module("src.db.migrations.versions.004_phase7_collaboration")

    source = inspect.getsource(migration)

    expected_tables = {
        "conversation_participant",
        "agent_handoff",
        "routing_decision_log",
        "agent_task",
        "agent_message",
        "collaboration_session",
        "collaboration_participant_v2",
    }

    for table in expected_tables:
        assert table in source
