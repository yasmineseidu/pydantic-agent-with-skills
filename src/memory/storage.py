"""Double-pass memory extraction from conversations."""

import json
import logging
import re
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.memory import (
    MemoryORM,
    MemorySourceEnum,
    MemoryStatusEnum,
    MemoryTierEnum,
)
from src.db.repositories.memory_repo import MemoryRepository
from src.memory.contradiction import ContradictionDetector
from src.memory.embedding import EmbeddingService
from src.memory.memory_log import MemoryAuditLog
from src.memory.types import (
    ContradictionResult,
    ExtractionResult,
    ExtractedMemory,
)
from src.prompts import EXTRACTION_PROMPT, VERIFICATION_PROMPT

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """Extracts memories from conversations using double-pass LLM extraction.

    Pass 1 performs high-confidence extraction of facts, preferences, and
    decisions.  Pass 2 reviews the original conversation alongside Pass 1
    results to catch anything missed.  The two passes are merged with cosine
    deduplication before persistence.

    Args:
        session: Async SQLAlchemy session for database operations.
        embedding_service: Service for generating text embeddings.
        contradiction_detector: Detector for memory contradictions.
        audit_log: Append-only audit log for memory lifecycle events.
        api_key: API key for the LLM provider (never logged).
        base_url: Base URL for the LLM chat completions API.
        extraction_model: Model identifier used for extraction calls.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        contradiction_detector: ContradictionDetector,
        audit_log: MemoryAuditLog,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        extraction_model: str = "anthropic/claude-sonnet-4.5",
    ) -> None:
        """Initialize the memory extractor.

        Args:
            session: Async SQLAlchemy session for database operations.
            embedding_service: Service for generating text embeddings.
            contradiction_detector: Detector for memory contradictions.
            audit_log: Append-only audit log for memory lifecycle events.
            api_key: API key for the LLM provider (never logged).
            base_url: Base URL for the LLM chat completions API.
            extraction_model: Model identifier used for extraction calls.
        """
        self._session: AsyncSession = session
        self._embedding_service: EmbeddingService = embedding_service
        self._contradiction_detector: ContradictionDetector = contradiction_detector
        self._audit_log: MemoryAuditLog = audit_log
        self._api_key: str = api_key
        self._base_url: str = base_url.rstrip("/")
        self._extraction_model: str = extraction_model
        self._repo: MemoryRepository = MemoryRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_from_conversation(
        self,
        messages: list[dict[str, str]],
        team_id: UUID,
        agent_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
    ) -> ExtractionResult:
        """Extract and persist memories from a conversation using double-pass extraction.

        Pass 1 extracts high-confidence memories.  Pass 2 reviews the
        conversation with Pass 1 results to fill gaps.  Results are merged
        (deduplicated by cosine > 0.95), then each memory is checked for
        contradictions and duplicates before persistence.

        Args:
            messages: Conversation messages as ``[{"role": ..., "content": ...}]``.
            team_id: Team scope for the extracted memories.
            agent_id: Optional agent scope.
            user_id: Optional user scope.
            conversation_id: Optional source conversation UUID.

        Returns:
            ExtractionResult with counts of created, versioned, and skipped memories.
        """
        formatted_messages: str = self._format_messages(messages)

        # --- Pass 1: High-confidence extraction ---
        pass1_memories: list[ExtractedMemory] = await self._run_pass1(formatted_messages)
        logger.info("extract_pass1: count=%d", len(pass1_memories))

        # --- Pass 2: Gap-filling verification ---
        pass2_memories: list[ExtractedMemory] = await self._run_pass2(
            pass1_memories, formatted_messages
        )
        logger.info("extract_pass2: count=%d", len(pass2_memories))

        # --- Merge and deduplicate ---
        merged: list[ExtractedMemory] = await self._deduplicate_extractions(
            pass1_memories, pass2_memories
        )
        logger.info(
            "extract_merged: pass1=%d pass2=%d merged=%d",
            len(pass1_memories),
            len(pass2_memories),
            len(merged),
        )

        # --- Persist each memory ---
        memories_created: int = 0
        memories_versioned: int = 0
        duplicates_skipped: int = 0
        contradictions_found: int = 0

        for extracted in merged:
            # Step a: Generate embedding
            embedding: list[float] = await self._embedding_service.embed_text(extracted.content)

            # Step b: Check contradictions
            contradiction: ContradictionResult = await self._contradiction_detector.check_on_store(
                new_memory=extracted,
                team_id=team_id,
                agent_id=agent_id,
            )

            if contradiction.contradicts:
                contradictions_found += len(contradiction.contradicts)

            # Step c: Check duplicates in the database
            duplicates: list[MemoryORM] = await self._repo.find_similar(
                embedding=embedding,
                team_id=team_id,
                threshold=0.92,
            )

            # Step d: If duplicate, skip
            if duplicates:
                duplicates_skipped += 1
                logger.info(
                    "extract_duplicate_skipped: content=%s similar_count=%d",
                    extracted.content[:80],
                    len(duplicates),
                )
                continue

            # Step e: If contradiction with action='supersede', version old memories
            if contradiction.action == "supersede" and contradiction.contradicts:
                for old_id in contradiction.contradicts:
                    await self._supersede_memory(old_id)
                memories_versioned += 1

            # Step f: Insert new memory
            new_orm: MemoryORM = self._build_memory_orm(
                extracted=extracted,
                embedding=embedding,
                team_id=team_id,
                agent_id=agent_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )
            self._session.add(new_orm)
            await self._session.flush()
            await self._session.refresh(new_orm)

            # Log creation
            await self._audit_log.log_created(
                memory_id=new_orm.id,
                content=extracted.content,
                source=MemorySourceEnum.EXTRACTION.value,
                changed_by="memory_extractor",
            )
            memories_created += 1

            logger.info(
                "extract_memory_created: id=%s type=%s importance=%d",
                new_orm.id,
                extracted.type.value,
                extracted.importance,
            )

        result = ExtractionResult(
            memories_created=memories_created,
            memories_versioned=memories_versioned,
            duplicates_skipped=duplicates_skipped,
            contradictions_found=contradictions_found,
            pass1_count=len(pass1_memories),
            pass2_additions=len(pass2_memories),
        )

        logger.info(
            "extract_complete: created=%d versioned=%d skipped=%d contradictions=%d",
            result.memories_created,
            result.memories_versioned,
            result.duplicates_skipped,
            result.contradictions_found,
        )

        return result

    # ------------------------------------------------------------------
    # Pass execution
    # ------------------------------------------------------------------

    async def _run_pass1(
        self,
        formatted_messages: str,
    ) -> list[ExtractedMemory]:
        """Execute Pass 1: high-confidence extraction.

        Args:
            formatted_messages: Pre-formatted conversation text.

        Returns:
            List of extracted memories from Pass 1.
        """
        prompt: str = EXTRACTION_PROMPT.format(messages=formatted_messages)

        try:
            raw_response: str = await self._call_llm(prompt)
        except RuntimeError:
            logger.error("extract_pass1_llm_failed: returning empty list")
            return []

        return self._parse_extracted_memories(raw_response)

    async def _run_pass2(
        self,
        pass1_memories: list[ExtractedMemory],
        formatted_messages: str,
    ) -> list[ExtractedMemory]:
        """Execute Pass 2: gap-filling verification.

        Args:
            pass1_memories: Memories extracted in Pass 1.
            formatted_messages: Pre-formatted conversation text.

        Returns:
            List of additional memories found in Pass 2.
        """
        pass1_dicts: list[dict[str, object]] = [m.model_dump() for m in pass1_memories]

        prompt: str = VERIFICATION_PROMPT.format(
            pass1_extractions=json.dumps(pass1_dicts, default=str),
            messages=formatted_messages,
        )

        try:
            raw_response: str = await self._call_llm(prompt)
        except RuntimeError:
            logger.error("extract_pass2_llm_failed: returning empty list")
            return []

        return self._parse_extracted_memories(raw_response)

    # ------------------------------------------------------------------
    # LLM communication
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM chat completions API.

        Args:
            prompt: The full prompt text to send as a user message.

        Returns:
            The assistant's response content string.

        Raises:
            RuntimeError: If the API returns an HTTP error status.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._extraction_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
            )

        if response.status_code >= 400:
            raise RuntimeError(f"LLM API error: HTTP {response.status_code}")

        return response.json()["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_extracted_memories(self, raw_response: str) -> list[ExtractedMemory]:
        """Parse LLM JSON output into ExtractedMemory models.

        Handles responses wrapped in markdown code fences (```json ... ```)
        as well as bare JSON arrays.

        Args:
            raw_response: Raw LLM response string.

        Returns:
            List of parsed ExtractedMemory objects. Returns empty list on
            parse failure.
        """
        cleaned: str = self._strip_code_fences(raw_response)

        try:
            parsed: list[dict[str, object]] = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(
                "extract_parse_failed: could not parse LLM response as JSON, length=%d",
                len(raw_response),
            )
            return []

        if not isinstance(parsed, list):
            logger.error("extract_parse_failed: expected JSON array, got %s", type(parsed).__name__)
            return []

        memories: list[ExtractedMemory] = []
        for item in parsed:
            try:
                memory = ExtractedMemory.model_validate(item)
                memories.append(memory)
            except Exception:
                logger.warning(
                    "extract_parse_item_skipped: invalid item=%s",
                    str(item)[:120],
                )

        return memories

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown code fences from LLM output.

        Args:
            text: Raw text potentially wrapped in ```json ... ``` or ``` ... ```.

        Returns:
            Text with outermost code fences removed.
        """
        stripped: str = text.strip()
        # Match ```json ... ``` or ``` ... ```
        match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
        if match:
            return match.group(1).strip()
        return stripped

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    async def _deduplicate_extractions(
        self,
        pass1: list[ExtractedMemory],
        pass2: list[ExtractedMemory],
    ) -> list[ExtractedMemory]:
        """Merge pass1 and pass2, removing near-duplicates by cosine > 0.95.

        Args:
            pass1: Memories from the first extraction pass.
            pass2: Memories from the second extraction pass.

        Returns:
            Merged list with pass2 duplicates removed.
        """
        if not pass2:
            return list(pass1)

        # Embed all pass1 memories
        pass1_texts: list[str] = [m.content for m in pass1]
        pass1_embeddings: list[list[float]] = (
            await self._embedding_service.embed_batch(pass1_texts) if pass1_texts else []
        )

        merged: list[ExtractedMemory] = list(pass1)

        for p2_mem in pass2:
            p2_embedding: list[float] = await self._embedding_service.embed_text(p2_mem.content)
            is_duplicate: bool = False

            for p1_emb in pass1_embeddings:
                similarity: float = self._cosine_similarity(p2_embedding, p1_emb)
                if similarity > 0.95:
                    is_duplicate = True
                    break

            if not is_duplicate:
                merged.append(p2_mem)

        return merged

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors.

        Args:
            a: First embedding vector.
            b: Second embedding vector.

        Returns:
            Cosine similarity in [-1.0, 1.0]. Returns 0.0 if either vector
            has zero magnitude.
        """
        dot: float = sum(x * y for x, y in zip(a, b))
        norm_a: float = sum(x * x for x in a) ** 0.5
        norm_b: float = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _supersede_memory(self, old_id: UUID) -> None:
        """Mark an existing memory as superseded.

        Args:
            old_id: UUID of the memory to supersede.
        """
        old_memory: Optional[MemoryORM] = await self._session.get(MemoryORM, old_id)
        if old_memory is None:
            logger.warning("supersede_memory_not_found: id=%s", old_id)
            return

        old_memory.status = MemoryStatusEnum.SUPERSEDED.value
        old_memory.tier = MemoryTierEnum.COLD.value
        await self._session.flush()

        logger.info("memory_superseded: id=%s", old_id)

    def _build_memory_orm(
        self,
        extracted: ExtractedMemory,
        embedding: list[float],
        team_id: UUID,
        agent_id: Optional[UUID],
        user_id: Optional[UUID],
        conversation_id: Optional[UUID],
    ) -> MemoryORM:
        """Build a MemoryORM instance from an ExtractedMemory.

        Args:
            extracted: The extracted memory data.
            embedding: Pre-computed embedding vector.
            team_id: Team scope.
            agent_id: Optional agent scope.
            user_id: Optional user scope.
            conversation_id: Optional source conversation UUID.

        Returns:
            A new MemoryORM instance ready for session insertion.
        """
        tier: str = (
            MemoryTierEnum.HOT.value if extracted.importance >= 9 else MemoryTierEnum.WARM.value
        )

        return MemoryORM(
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            memory_type=extracted.type.value,
            content=extracted.content,
            subject=extracted.subject,
            embedding=embedding,
            importance=extracted.importance,
            confidence=extracted.confidence,
            source_type=MemorySourceEnum.EXTRACTION.value,
            source_conversation_id=conversation_id,
            extraction_model=self._extraction_model,
            tier=tier,
            status=MemoryStatusEnum.ACTIVE.value,
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict[str, str]]) -> str:
        """Format conversation messages for LLM prompt injection.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Formatted string with one line per message.
        """
        lines: list[str] = []
        for msg in messages:
            role: str = msg.get("role", "unknown")
            content: str = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
