"""Unit tests for workers/schedules.py beat schedule configuration."""

from unittest.mock import MagicMock

import pytest
from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from workers.schedules import BEAT_SCHEDULE, configure_beat_schedule


@pytest.mark.unit
class TestBeatSchedule:
    """Test static beat schedule configuration."""

    def test_beat_schedule_has_six_entries(self) -> None:
        """BEAT_SCHEDULE should contain exactly 6 scheduled tasks."""
        assert len(BEAT_SCHEDULE) == 6

    def test_beat_schedule_entry_keys(self) -> None:
        """Each entry should have task, schedule, and options keys."""
        for name, entry in BEAT_SCHEDULE.items():
            assert "task" in entry, f"Missing 'task' in {name}"
            assert "schedule" in entry, f"Missing 'schedule' in {name}"
            assert "options" in entry, f"Missing 'options' in {name}"

    def test_beat_schedule_tasks_are_strings(self) -> None:
        """Each task value should be a dotted-path string."""
        for name, entry in BEAT_SCHEDULE.items():
            assert isinstance(entry["task"], str), f"task in {name} is not a string"
            assert "." in entry["task"], f"task in {name} missing dotted path"

    def test_beat_schedule_uses_crontab(self) -> None:
        """All schedules should use celery crontab instances."""
        for name, entry in BEAT_SCHEDULE.items():
            assert isinstance(entry["schedule"], crontab), f"schedule in {name} is not a crontab"

    def test_beat_schedule_expected_names(self) -> None:
        """BEAT_SCHEDULE should contain the expected task names."""
        expected = {
            "expire-tokens",
            "close-stale-sessions",
            "archive-old-conversations",
            "archive-expired-memories",
            "consolidate-memories",
            "decay-and-expire-memories",
        }
        assert set(BEAT_SCHEDULE.keys()) == expected

    def test_beat_schedule_queues_are_default(self) -> None:
        """All tasks should be routed to the default queue."""
        for name, entry in BEAT_SCHEDULE.items():
            assert entry["options"]["queue"] == "default", f"queue in {name} is not 'default'"


@pytest.mark.unit
class TestConfigureBeatSchedule:
    """Test configure_beat_schedule applies to Celery app."""

    def test_configure_sets_beat_schedule(self) -> None:
        """configure_beat_schedule should set app.conf.beat_schedule."""
        mock_app = MagicMock(spec=Celery)
        mock_app.conf = MagicMock()

        configure_beat_schedule(mock_app)

        assert mock_app.conf.beat_schedule is not None
        assert len(mock_app.conf.beat_schedule) == 6

    def test_configure_creates_copy(self) -> None:
        """configure_beat_schedule should set a copy, not the original dict."""
        mock_app = MagicMock(spec=Celery)
        mock_app.conf = MagicMock()

        configure_beat_schedule(mock_app)

        assert mock_app.conf.beat_schedule is not BEAT_SCHEDULE
        assert mock_app.conf.beat_schedule == BEAT_SCHEDULE
