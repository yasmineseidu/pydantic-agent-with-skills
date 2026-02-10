"""Unit tests for MemoryExtractor in src/memory/storage.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.db.models.memory import MemorySourceEnum
from src.memory.storage import MemoryExtractor
from src.memory.types import ContradictionResult, ExtractionResult, ExtractedMemory
from src.models.memory_models import MemoryType


def _make_success_response(content: str) -> MagicMock:
    """Build a mock httpx response with the given LLM content.

    Args:
        content: The assistant's response content string.

    Returns:
        MagicMock configured as a successful httpx response.
    """
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def _make_error_response(status_code: int) -> MagicMock:
    """Build a mock httpx error response.

    Args:
        status_code: HTTP status code for the error.

    Returns:
        MagicMock configured as an error httpx response.
    """
    response = MagicMock()
    response.status_code = status_code
    return response


def _build_mock_client(side_effect: list[MagicMock] | MagicMock) -> AsyncMock:
    """Build a mock httpx.AsyncClient with the given post side_effect.

    Args:
        side_effect: Either a single response or list of responses for
            sequential calls.

    Returns:
        AsyncMock configured as an httpx.AsyncClient async context manager.
    """
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if isinstance(side_effect, list):
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        mock_client.post = AsyncMock(return_value=side_effect)
    return mock_client


def _make_extracted_memory(**overrides: object) -> ExtractedMemory:
    """Factory for creating ExtractedMemory instances with defaults.

    Args:
        overrides: Fields to override in the default memory.

    Returns:
        An ExtractedMemory instance with defaults applied.
    """
    defaults = {
        "type": MemoryType.SEMANTIC,
        "content": "User prefers dark mode",
        "subject": "user_preference",
        "importance": 7,
        "confidence": 0.9,
    }
    defaults.update(overrides)
    return ExtractedMemory(**defaults)  # type: ignore[arg-type]


class TestExtractFromConversation:
    """Tests for MemoryExtractor.extract_from_conversation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_single_pass_returns_extraction_result(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that a single-pass extraction returns ExtractionResult with correct fields."""
        team_id = uuid4()
        memories_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers dark mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
                {
                    "type": "semantic",
                    "content": "User works in finance",
                    "subject": "user_context",
                    "importance": 8,
                    "confidence": 0.95,
                },
            ]
        )

        # Mock LLM calls: Pass 1 returns 2 memories, Pass 2 returns empty
        pass1_response = _make_success_response(memories_json)
        pass2_response = _make_success_response("[]")
        mock_client = _build_mock_client([pass1_response, pass2_response])

        # Mock dependencies
        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No contradictions",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        # Mock repository
        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )

            # Mock find_similar to return no duplicates
            extractor._repo.find_similar = AsyncMock(return_value=[])

            result = await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "I prefer dark mode"}],
                team_id=team_id,
            )

        assert isinstance(result, ExtractionResult)
        assert result.memories_created == 2
        assert result.pass1_count == 2
        assert result.pass2_additions == 0
        assert result.duplicates_skipped == 0
        assert result.contradictions_found == 0
        assert mock_add.call_count == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_double_pass_finds_additional_memories(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that Pass 2 finds additional memories missed in Pass 1."""
        team_id = uuid4()

        pass1_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers dark mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        pass2_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User works remotely",
                    "subject": "user_context",
                    "importance": 6,
                    "confidence": 0.85,
                },
            ]
        )

        pass1_response = _make_success_response(pass1_json)
        pass2_response = _make_success_response(pass2_json)
        mock_client = _build_mock_client([pass1_response, pass2_response])

        # Mock dependencies - return orthogonal embeddings to ensure low similarity
        embedding_service = AsyncMock()
        # Create orthogonal vectors for low cosine similarity:
        # Pass 1: first half is 1.0, second half is 0.0
        # Pass 2: first half is 0.0, second half is 1.0
        pass1_embedding = [1.0] * 768 + [0.0] * 768
        pass2_embedding = [0.0] * 768 + [1.0] * 768

        embedding_service.embed_text = AsyncMock(
            side_effect=[
                pass2_embedding,  # Pass 2 memory dedup check (orthogonal to Pass 1)
                pass1_embedding,  # Pass 1 memory persistence
                pass2_embedding,  # Pass 2 memory persistence
            ]
        )
        embedding_service.embed_batch = AsyncMock(return_value=[pass1_embedding])

        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No contradictions",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            result = await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "I prefer dark mode and work remotely"}],
                team_id=team_id,
            )

        assert result.pass1_count == 1
        assert result.pass2_additions == 1
        assert result.memories_created == 2
        assert mock_add.call_count == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dedup_between_passes_skips_similar_memories(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that Pass 2 duplicates of Pass 1 are filtered out by cosine similarity."""
        team_id = uuid4()

        # Both passes return similar content
        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers dark mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        pass1_response = _make_success_response(memory_json)
        pass2_response = _make_success_response(memory_json)
        mock_client = _build_mock_client([pass1_response, pass2_response])

        # Mock dependencies - return very similar embeddings
        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.9] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[[0.9] * 1536])

        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No contradictions",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            result = await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "I prefer dark mode"}],
                team_id=team_id,
            )

        # Only 1 memory should be created (Pass 2 duplicate filtered out)
        assert result.memories_created == 1
        assert result.pass1_count == 1
        assert result.pass2_additions == 1
        assert mock_add.call_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_contradiction_detected_marks_existing_superseded(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that a 'supersede' contradiction action increments contradictions_found."""
        team_id = uuid4()
        old_memory_id = uuid4()

        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers light mode now",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        pass1_response = _make_success_response(memory_json)
        pass2_response = _make_success_response("[]")
        mock_client = _build_mock_client([pass1_response, pass2_response])

        # Mock dependencies
        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[])

        # Mock contradiction returning supersede action
        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[old_memory_id],
                action="supersede",
                reason="New preference supersedes old",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        # Mock old memory
        old_memory_orm = MagicMock()
        old_memory_orm.id = old_memory_id

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
            patch.object(mock_session, "get", new_callable=AsyncMock, return_value=old_memory_orm),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            result = await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "Actually, I prefer light mode"}],
                team_id=team_id,
            )

        assert result.contradictions_found == 1
        assert result.memories_versioned == 1
        assert result.memories_created == 1
        assert mock_add.call_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_contradiction_dispute_still_stores_memory(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that a 'dispute' contradiction action still stores the memory."""
        team_id = uuid4()
        existing_memory_id = uuid4()

        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers light mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        pass1_response = _make_success_response(memory_json)
        pass2_response = _make_success_response("[]")
        mock_client = _build_mock_client([pass1_response, pass2_response])

        # Mock dependencies
        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[])

        # Mock contradiction returning dispute action
        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[existing_memory_id],
                action="dispute",
                reason="Conflicting preferences - both stored",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            result = await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "I prefer light mode"}],
                team_id=team_id,
            )

        # Memory should still be created despite dispute
        assert result.memories_created == 1
        assert result.contradictions_found == 1
        assert result.memories_versioned == 0
        assert mock_add.call_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_conversation_returns_zero_memories(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that an empty conversation returns ExtractionResult with 0 counts."""
        team_id = uuid4()

        # LLM returns empty arrays
        empty_response = _make_success_response("[]")
        mock_client = _build_mock_client([empty_response, empty_response])

        # Mock dependencies
        embedding_service = AsyncMock()
        contradiction_detector = AsyncMock()
        audit_log = AsyncMock()

        with patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )

            result = await extractor.extract_from_conversation(
                messages=[],
                team_id=team_id,
            )

        assert result.memories_created == 0
        assert result.pass1_count == 0
        assert result.pass2_additions == 0
        assert result.duplicates_skipped == 0
        assert result.contradictions_found == 0


class TestParseExtractedMemories:
    """Tests for MemoryExtractor._parse_extracted_memories."""

    @pytest.mark.unit
    def test_parse_extracted_memories_valid_json(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that valid JSON array is parsed into ExtractedMemory objects."""
        embedding_service = AsyncMock()
        contradiction_detector = AsyncMock()
        audit_log = AsyncMock()

        extractor = MemoryExtractor(
            session=mock_session,
            embedding_service=embedding_service,
            contradiction_detector=contradiction_detector,
            audit_log=audit_log,
            api_key="test-key",
        )

        valid_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers dark mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        memories = extractor._parse_extracted_memories(valid_json)

        assert len(memories) == 1
        assert memories[0].content == "User prefers dark mode"
        assert memories[0].type == MemoryType.SEMANTIC

    @pytest.mark.unit
    def test_parse_extracted_memories_handles_markdown_fences(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that JSON wrapped in markdown code fences is parsed correctly."""
        embedding_service = AsyncMock()
        contradiction_detector = AsyncMock()
        audit_log = AsyncMock()

        extractor = MemoryExtractor(
            session=mock_session,
            embedding_service=embedding_service,
            contradiction_detector=contradiction_detector,
            audit_log=audit_log,
            api_key="test-key",
        )

        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User works remotely",
                    "subject": "user_context",
                    "importance": 6,
                    "confidence": 0.85,
                },
            ]
        )
        wrapped_json = f"```json\n{memory_json}\n```"

        memories = extractor._parse_extracted_memories(wrapped_json)

        assert len(memories) == 1
        assert memories[0].content == "User works remotely"

    @pytest.mark.unit
    def test_parse_extracted_memories_empty_response(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that empty or invalid responses return an empty list."""
        embedding_service = AsyncMock()
        contradiction_detector = AsyncMock()
        audit_log = AsyncMock()

        extractor = MemoryExtractor(
            session=mock_session,
            embedding_service=embedding_service,
            contradiction_detector=contradiction_detector,
            audit_log=audit_log,
            api_key="test-key",
        )

        # Test empty string
        memories = extractor._parse_extracted_memories("")
        assert memories == []

        # Test invalid JSON
        memories = extractor._parse_extracted_memories("not json at all")
        assert memories == []

        # Test non-array JSON
        memories = extractor._parse_extracted_memories('{"type": "semantic"}')
        assert memories == []


class TestCallLLM:
    """Tests for MemoryExtractor._call_llm."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_call_llm_timeout(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that LLM timeout is handled gracefully by raising RuntimeError."""
        import httpx

        # Mock client that raises timeout
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        embedding_service = AsyncMock()
        contradiction_detector = AsyncMock()
        audit_log = AsyncMock()

        with patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )

            with pytest.raises(httpx.TimeoutException):
                await extractor._call_llm("Test prompt")


class TestExtractPersistence:
    """Tests for database persistence during extraction."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_persists_to_database(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that extracted memories are persisted via session.add."""
        team_id = uuid4()

        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "User prefers dark mode",
                    "subject": "user_preference",
                    "importance": 7,
                    "confidence": 0.9,
                },
            ]
        )

        pass1_response = _make_success_response(memory_json)
        pass2_response = _make_success_response("[]")
        mock_client = _build_mock_client([pass1_response, pass2_response])

        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[])

        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No contradictions",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add") as mock_add,
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "I prefer dark mode"}],
                team_id=team_id,
            )

        # Verify session.add was called once per memory
        assert mock_add.call_count == 1
        # Verify the added object has expected attributes
        added_orm = mock_add.call_args[0][0]
        assert added_orm.content == "User prefers dark mode"
        assert added_orm.source_type == MemorySourceEnum.EXTRACTION.value

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_embeds_each_memory(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that embedding service is called for each extracted memory."""
        team_id = uuid4()

        memory_json = json.dumps(
            [
                {
                    "type": "semantic",
                    "content": "First memory",
                    "subject": "test",
                    "importance": 5,
                    "confidence": 0.8,
                },
                {
                    "type": "semantic",
                    "content": "Second memory",
                    "subject": "test",
                    "importance": 6,
                    "confidence": 0.9,
                },
            ]
        )

        pass1_response = _make_success_response(memory_json)
        pass2_response = _make_success_response("[]")
        mock_client = _build_mock_client([pass1_response, pass2_response])

        embedding_service = AsyncMock()
        embedding_service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding_service.embed_batch = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        contradiction_detector = AsyncMock()
        contradiction_detector.check_on_store = AsyncMock(
            return_value=ContradictionResult(
                contradicts=[],
                action="coexist",
                reason="No contradictions",
            )
        )

        audit_log = AsyncMock()
        audit_log.log_created = AsyncMock()

        with (
            patch("src.memory.storage.httpx.AsyncClient", return_value=mock_client),
            patch.object(mock_session, "add"),
            patch.object(mock_session, "flush", new_callable=AsyncMock),
            patch.object(mock_session, "refresh", new_callable=AsyncMock),
        ):
            extractor = MemoryExtractor(
                session=mock_session,
                embedding_service=embedding_service,
                contradiction_detector=contradiction_detector,
                audit_log=audit_log,
                api_key="test-key",
            )
            extractor._repo.find_similar = AsyncMock(return_value=[])

            await extractor.extract_from_conversation(
                messages=[{"role": "user", "content": "Test"}],
                team_id=team_id,
            )

        # embed_text should be called once per memory for persistence
        assert embedding_service.embed_text.await_count == 2
