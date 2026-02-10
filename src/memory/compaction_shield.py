"""Context compaction shield for extracting memories before trimming."""

import logging
from typing import Optional
from uuid import UUID

from src.memory.storage import MemoryExtractor
from src.memory.types import CompactionResult, ExtractionResult
from src.settings import Settings

logger = logging.getLogger(__name__)


class CompactionShield:
    """Extracts memories from conversation messages before context compaction.

    The compaction shield acts as a safety net that runs the double-pass
    memory extractor on conversation messages that are about to be trimmed
    from the context window.  This ensures that important facts, preferences,
    and decisions are persisted to long-term memory before they are lost.

    The shield is gated by the ``enable_compaction_shield`` feature flag.
    When disabled, it returns an empty ``CompactionResult`` with no side
    effects.

    Args:
        extractor: The memory extractor used for double-pass extraction.
        settings: Application settings containing feature flags.
    """

    def __init__(
        self,
        extractor: MemoryExtractor,
        settings: Settings,
    ) -> None:
        """Initialize the compaction shield.

        Args:
            extractor: The memory extractor used for double-pass extraction.
            settings: Application settings containing feature flags.
        """
        self._extractor: MemoryExtractor = extractor
        self._settings: Settings = settings

    async def extract_before_compaction(
        self,
        messages: list[dict[str, str]],
        team_id: UUID,
        agent_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
    ) -> CompactionResult:
        """Extract memories from messages before they are compacted away.

        Checks the ``enable_compaction_shield`` feature flag.  When disabled,
        returns an empty ``CompactionResult`` immediately.  When enabled,
        delegates to ``MemoryExtractor.extract_from_conversation`` and then
        generates a conversation summary stored as an additional episodic
        memory.

        Args:
            messages: Conversation messages as ``[{"role": ..., "content": ...}]``.
            team_id: Team scope for the extracted memories.
            agent_id: Optional agent scope.
            user_id: Optional user scope.
            conversation_id: Optional source conversation UUID.

        Returns:
            CompactionResult with extraction counts and a human-readable summary.
        """
        if not self._settings.feature_flags.enable_compaction_shield:
            logger.info("compaction_shield_disabled: skipping extraction")
            return CompactionResult(
                memories_extracted=0,
                summary="Compaction shield disabled",
                pass1_count=0,
                pass2_additions=0,
            )

        logger.info(
            "compaction_shield_start: messages=%d team_id=%s",
            len(messages),
            team_id,
        )

        # --- Run double-pass extraction ---
        extraction: ExtractionResult = await self._extractor.extract_from_conversation(
            messages=messages,
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        # --- Generate conversation summary ---
        summary_content: str = self._build_summary(messages)

        logger.info(
            "compaction_shield_complete: extracted=%d pass1=%d pass2=%d",
            extraction.memories_created,
            extraction.pass1_count,
            extraction.pass2_additions,
        )

        return CompactionResult(
            memories_extracted=extraction.memories_created,
            summary=summary_content,
            pass1_count=extraction.pass1_count,
            pass2_additions=extraction.pass2_additions,
        )

    @staticmethod
    def _build_summary(messages: list[dict[str, str]]) -> str:
        """Build a brief summary of conversation messages being compacted.

        Summarises up to the first 10 messages, truncating each message
        content to 100 characters.

        Args:
            messages: Conversation messages to summarise.

        Returns:
            A single-line summary string suitable for episodic memory storage.
        """
        truncated_parts: list[str] = [
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}" for msg in messages[:10]
        ]
        return f"Conversation summary ({len(messages)} messages): " + " | ".join(truncated_parts)
