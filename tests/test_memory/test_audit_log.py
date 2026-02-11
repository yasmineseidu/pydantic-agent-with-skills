"""Unit tests for MemoryAuditLog in src/memory/memory_log.py."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.db.models.memory import MemoryLogORM
from src.memory.memory_log import MemoryAuditLog
from src.memory.types import MemorySnapshot


def _make_mock_session() -> AsyncMock:
    """Build a mock AsyncSession with sync add and async flush.

    Returns:
        AsyncMock configured as a minimal AsyncSession.
    """
    session = AsyncMock()
    session.add = MagicMock()  # add() is synchronous
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


class TestLogCreated:
    """Tests for MemoryAuditLog.log_created."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_created_inserts_with_action_created(self) -> None:
        """Test that log_created adds a MemoryLogORM with action='created' and new_content."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        mid = uuid4()

        await audit.log_created(memory_id=mid, content="test content", source="extraction")

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "created"
        assert added_obj.new_content == "test content"
        assert added_obj.memory_id == mid
        assert added_obj.changed_by == "system"
        assert "extraction" in added_obj.reason

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_created_calls_flush(self) -> None:
        """Test that log_created calls session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_created(memory_id=uuid4(), content="x", source="explicit")

        session.flush.assert_awaited_once()


class TestLogUpdated:
    """Tests for MemoryAuditLog.log_updated."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_updated_stores_old_and_new_content(self) -> None:
        """Test that log_updated stores both old_content and new_content."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        mid = uuid4()

        await audit.log_updated(
            memory_id=mid,
            old_content="old value",
            new_content="new value",
            reason="correction",
        )

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "updated"
        assert added_obj.old_content == "old value"
        assert added_obj.new_content == "new value"
        assert added_obj.reason == "correction"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_updated_calls_add_and_flush(self) -> None:
        """Test that log_updated calls session.add() and session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_updated(
            memory_id=uuid4(),
            old_content="a",
            new_content="b",
            reason="test",
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestLogSuperseded:
    """Tests for MemoryAuditLog.log_superseded."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_superseded_has_related_memory_ids(self) -> None:
        """Test that log_superseded stores new_id in related_memory_ids."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        old_id = uuid4()
        new_id = uuid4()

        await audit.log_superseded(old_id=old_id, new_id=new_id, reason="newer info")

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "superseded"
        assert added_obj.memory_id == old_id
        assert str(new_id) in added_obj.related_memory_ids

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_superseded_calls_add_and_flush(self) -> None:
        """Test that log_superseded calls session.add() and session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_superseded(old_id=uuid4(), new_id=uuid4(), reason="test")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestLogPromoted:
    """Tests for MemoryAuditLog.log_promoted."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_promoted_records_tiers(self) -> None:
        """Test that log_promoted records old_tier and new_tier."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        mid = uuid4()

        await audit.log_promoted(memory_id=mid, old_tier="warm", new_tier="hot")

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "promoted"
        assert added_obj.old_tier == "warm"
        assert added_obj.new_tier == "hot"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_promoted_calls_add_and_flush(self) -> None:
        """Test that log_promoted calls session.add() and session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_promoted(memory_id=uuid4(), old_tier="cold", new_tier="warm")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestLogDemoted:
    """Tests for MemoryAuditLog.log_demoted."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_demoted_records_tiers(self) -> None:
        """Test that log_demoted records old_tier and new_tier with action='demoted'."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        mid = uuid4()

        await audit.log_demoted(memory_id=mid, old_tier="hot", new_tier="warm")

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "demoted"
        assert added_obj.old_tier == "hot"
        assert added_obj.new_tier == "warm"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_demoted_calls_add_and_flush(self) -> None:
        """Test that log_demoted calls session.add() and session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_demoted(memory_id=uuid4(), old_tier="hot", new_tier="cold")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestLogContradiction:
    """Tests for MemoryAuditLog.log_contradiction."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_contradiction_records_both_uuids(self) -> None:
        """Test that log_contradiction stores both memory UUIDs in related_memory_ids."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)
        mem_a = uuid4()
        mem_b = uuid4()

        await audit.log_contradiction(
            memory_a=mem_a,
            memory_b=mem_b,
            resolution="kept newer",
        )

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, MemoryLogORM)
        assert added_obj.action == "contradiction_detected"
        assert str(mem_a) in added_obj.related_memory_ids
        assert str(mem_b) in added_obj.related_memory_ids

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_contradiction_calls_add_and_flush(self) -> None:
        """Test that log_contradiction calls session.add() and session.flush()."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        await audit.log_contradiction(memory_a=uuid4(), memory_b=uuid4(), resolution="test")

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestReconstructAt:
    """Tests for MemoryAuditLog.reconstruct_at."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reconstruct_at_returns_snapshots(self) -> None:
        """Test that reconstruct_at returns MemorySnapshot objects from log entries."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        team_id = uuid4()
        mem_id = uuid4()
        now = datetime.now(tz=timezone.utc)

        # Mock the first query: team memory IDs
        team_result = MagicMock()
        team_result.all.return_value = [(mem_id,)]

        # Mock the second query: log entries
        log_entry = MagicMock()
        log_entry.memory_id = mem_id
        log_entry.action = "created"
        log_entry.new_content = "remembered content"
        log_entry.created_at = now

        log_result = MagicMock()
        log_scalars = MagicMock()
        log_scalars.all.return_value = [log_entry]
        log_result.scalars.return_value = log_scalars

        # Return team_result for first execute, log_result for second
        session.execute = AsyncMock(side_effect=[team_result, log_result])

        snapshots = await audit.reconstruct_at(timestamp=now, team_id=team_id)

        assert len(snapshots) == 1
        assert isinstance(snapshots[0], MemorySnapshot)
        assert snapshots[0].memory_id == mem_id
        assert snapshots[0].content == "remembered content"
        assert snapshots[0].status == "active"
        assert snapshots[0].tier == "warm"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reconstruct_at_empty_team_returns_empty(self) -> None:
        """Test that reconstruct_at returns empty list when team has no memories."""
        session = _make_mock_session()
        audit = MemoryAuditLog(session)

        team_result = MagicMock()
        team_result.all.return_value = []
        session.execute = AsyncMock(return_value=team_result)

        now = datetime.now(tz=timezone.utc)
        snapshots = await audit.reconstruct_at(timestamp=now, team_id=uuid4())

        assert snapshots == []
