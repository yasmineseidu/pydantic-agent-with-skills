"""Unit tests for CompactionShield in src/memory/compaction_shield.py."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.memory.compaction_shield import CompactionShield
from src.memory.storage import MemoryExtractor
from src.memory.types import CompactionResult, ExtractionResult
from src.settings import FeatureFlags, Settings


def _make_mock_extractor() -> AsyncMock:
    """Create a mock MemoryExtractor for testing.

    Returns:
        AsyncMock configured as a MemoryExtractor.
    """
    extractor = AsyncMock(spec=MemoryExtractor)
    extractor.extract_from_conversation = AsyncMock()
    return extractor


def _make_settings(enable_compaction_shield: bool = True) -> Settings:
    """Create a Settings instance with configurable compaction shield flag.

    Args:
        enable_compaction_shield: Whether to enable the compaction shield.

    Returns:
        A Settings instance with the specified feature flag.
    """
    settings = Settings()
    settings.feature_flags = FeatureFlags(enable_compaction_shield=enable_compaction_shield)
    return settings


class TestExtractBeforeCompaction:
    """Tests for CompactionShield.extract_before_compaction."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disabled_flag_returns_empty_result(self) -> None:
        """Test that disabled flag returns CompactionResult with 0 memories_extracted."""
        extractor = _make_mock_extractor()
        settings = _make_settings(enable_compaction_shield=False)

        shield = CompactionShield(extractor=extractor, settings=settings)

        team_id = uuid4()
        messages = [{"role": "user", "content": "Hello world"}]

        result = await shield.extract_before_compaction(
            messages=messages,
            team_id=team_id,
        )

        # Should return empty result without calling extractor
        assert isinstance(result, CompactionResult)
        assert result.memories_extracted == 0
        assert result.summary == "Compaction shield disabled"
        assert result.pass1_count == 0
        assert result.pass2_additions == 0
        extractor.extract_from_conversation.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_enabled_flag_calls_extractor(self) -> None:
        """Test that enabled flag delegates to extractor.extract_from_conversation."""
        extractor = _make_mock_extractor()
        settings = _make_settings(enable_compaction_shield=True)

        # Mock extraction result
        extractor.extract_from_conversation.return_value = ExtractionResult(
            memories_created=2,
            memories_versioned=0,
            duplicates_skipped=0,
            contradictions_found=0,
            pass1_count=2,
            pass2_additions=0,
        )

        shield = CompactionShield(extractor=extractor, settings=settings)

        team_id = uuid4()
        messages = [{"role": "user", "content": "I prefer dark mode"}]

        result = await shield.extract_before_compaction(
            messages=messages,
            team_id=team_id,
        )

        # Should call extractor
        extractor.extract_from_conversation.assert_called_once()
        assert isinstance(result, CompactionResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_compaction_result_with_correct_counts(self) -> None:
        """Test that CompactionResult has correct counts from ExtractionResult."""
        extractor = _make_mock_extractor()
        settings = _make_settings(enable_compaction_shield=True)

        # Mock extraction result with specific counts
        extractor.extract_from_conversation.return_value = ExtractionResult(
            memories_created=3,
            memories_versioned=1,
            duplicates_skipped=2,
            contradictions_found=1,
            pass1_count=2,
            pass2_additions=1,
        )

        shield = CompactionShield(extractor=extractor, settings=settings)

        team_id = uuid4()
        messages = [{"role": "user", "content": "Test message"}]

        result = await shield.extract_before_compaction(
            messages=messages,
            team_id=team_id,
        )

        assert result.memories_extracted == 3
        assert result.pass1_count == 2
        assert result.pass2_additions == 1
        assert "Conversation summary" in result.summary

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passes_team_and_agent_ids_to_extractor(self) -> None:
        """Test that team_id and agent_id are passed through to extractor."""
        extractor = _make_mock_extractor()
        settings = _make_settings(enable_compaction_shield=True)

        extractor.extract_from_conversation.return_value = ExtractionResult(
            memories_created=1,
            memories_versioned=0,
            duplicates_skipped=0,
            contradictions_found=0,
            pass1_count=1,
            pass2_additions=0,
        )

        shield = CompactionShield(extractor=extractor, settings=settings)

        team_id = uuid4()
        agent_id = uuid4()
        user_id = uuid4()
        conversation_id = uuid4()
        messages = [{"role": "user", "content": "Test"}]

        await shield.extract_before_compaction(
            messages=messages,
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        # Verify all IDs were passed through
        extractor.extract_from_conversation.assert_called_once_with(
            messages=messages,
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )


class TestBuildSummary:
    """Tests for CompactionShield._build_summary."""

    @pytest.mark.unit
    def test_build_summary_truncates_long_messages(self) -> None:
        """Test that message content is truncated to 100 characters."""
        long_content = "x" * 200
        messages = [{"role": "user", "content": long_content}]

        summary = CompactionShield._build_summary(messages)

        # Content should be truncated to 100 chars
        assert "x" * 100 in summary
        assert len(long_content) > 100
        # Should not contain full content
        assert "x" * 101 not in summary

    @pytest.mark.unit
    def test_build_summary_limits_to_10_messages(self) -> None:
        """Test that summary only includes first 10 messages."""
        # Create 15 messages
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(15)]

        summary = CompactionShield._build_summary(messages)

        # Should include count of all messages
        assert "(15 messages)" in summary

        # Should include first 10 messages
        assert "Message 0" in summary
        assert "Message 9" in summary

        # Should NOT include messages 10-14
        assert "Message 10" not in summary
        assert "Message 14" not in summary

    @pytest.mark.unit
    def test_build_summary_empty_messages(self) -> None:
        """Test that empty message list returns summary with (0 messages)."""
        messages: list[dict[str, str]] = []

        summary = CompactionShield._build_summary(messages)

        assert "(0 messages)" in summary
        assert "Conversation summary" in summary

    @pytest.mark.unit
    def test_build_summary_handles_missing_role_and_content(self) -> None:
        """Test that messages without role/content keys use defaults."""
        messages = [
            {},  # No keys at all
            {"role": "user"},  # Missing content
            {"content": "Hello"},  # Missing role
        ]

        summary = CompactionShield._build_summary(messages)

        # Should handle missing keys gracefully
        assert "unknown" in summary  # Default role
        assert "(3 messages)" in summary
        assert "Conversation summary" in summary

    @pytest.mark.unit
    def test_build_summary_format(self) -> None:
        """Test that summary has correct format with role and truncated content."""
        messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Second message"},
        ]

        summary = CompactionShield._build_summary(messages)

        # Check format: "Conversation summary (N messages): role: content | role: content"
        assert summary.startswith("Conversation summary (2 messages):")
        assert "user: First message" in summary
        assert "assistant: Second message" in summary
        assert "|" in summary  # Separator between messages
