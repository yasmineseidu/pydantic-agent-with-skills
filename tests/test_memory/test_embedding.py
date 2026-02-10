"""Unit tests for EmbeddingService in src/memory/embedding.py."""

import hashlib
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.embedding import EmbeddingService, MAX_CACHE_SIZE


def _make_success_response(embeddings: list[list[float]]) -> MagicMock:
    """Build a mock httpx response with the given embeddings.

    Args:
        embeddings: List of embedding vectors to include in the response.

    Returns:
        MagicMock configured as a successful httpx response.
    """
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [{"embedding": emb} for emb in embeddings]}
    return response


def _make_error_response(status_code: int, body: str = "error") -> MagicMock:
    """Build a mock httpx error response.

    Args:
        status_code: HTTP status code for the error.
        body: Response text body.

    Returns:
        MagicMock configured as an error httpx response.
    """
    response = MagicMock()
    response.status_code = status_code
    response.text = body
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


class TestEmbedText:
    """Tests for EmbeddingService.embed_text."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_single_text_embedding_returns_correct_dimensions(self) -> None:
        """Test that embed_text returns a vector with the configured dimensions."""
        embedding_vec = [0.1] * 1536
        response = _make_success_response([embedding_vec])
        mock_client = _build_mock_client(response)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService(api_key="test-key")
            result = await service.embed_text("hello world")

        assert len(result) == 1536
        assert result == embedding_vec

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self) -> None:
        """Test that embedding the same text twice only makes 1 API call."""
        embedding_vec = [0.2] * 1536
        response = _make_success_response([embedding_vec])
        mock_client = _build_mock_client(response)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService(api_key="test-key")
            result1 = await service.embed_text("hello")
            result2 = await service.embed_text("hello")

        assert result1 == result2
        # Only 1 API call should have been made
        assert mock_client.post.await_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_429_retry_succeeds_after_backoff(self) -> None:
        """Test that a 429 response triggers retry and succeeds on next attempt."""
        rate_limit_response = _make_error_response(429)
        embedding_vec = [0.3] * 1536
        success_response = _make_success_response([embedding_vec])

        # First call returns 429, second returns 200
        mock_client = _build_mock_client([rate_limit_response, success_response])

        with (
            patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client),
            patch("src.memory.embedding.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            service = EmbeddingService(api_key="test-key")
            result = await service.embed_text("hello")

        assert result == embedding_vec
        mock_sleep.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_500_error_raises_runtime_error(self) -> None:
        """Test that a 500 response raises RuntimeError immediately."""
        error_response = _make_error_response(500, "Internal Server Error")
        mock_client = _build_mock_client(error_response)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService(api_key="test-key")
            with pytest.raises(RuntimeError, match="HTTP 500"):
                await service.embed_text("hello")

    @pytest.mark.unit
    def test_cache_key_is_sha256_of_normalized_text(self) -> None:
        """Test that the cache key is SHA-256 of lowercased, stripped text."""
        service = EmbeddingService(api_key="test-key")

        raw_text = "  Hello World  "
        normalized = raw_text.lower().strip()
        expected_key = hashlib.sha256(normalized.encode()).hexdigest()

        actual_key = service._cache_key(raw_text)
        assert actual_key == expected_key

    @pytest.mark.unit
    def test_cache_key_normalization_equivalence(self) -> None:
        """Test that differently-cased/padded texts produce the same cache key."""
        service = EmbeddingService(api_key="test-key")

        key1 = service._cache_key("Hello World")
        key2 = service._cache_key("  hello world  ")
        key3 = service._cache_key("HELLO WORLD")

        assert key1 == key2 == key3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lru_eviction_when_cache_full(self) -> None:
        """Test that adding beyond MAX_CACHE_SIZE evicts the oldest entry."""
        service = EmbeddingService(api_key="test-key")

        # Fill cache to capacity manually
        for i in range(MAX_CACHE_SIZE):
            key = service._cache_key(f"text_{i}")
            service._cache_put(key, [float(i)] * 10)

        assert len(service._cache) == MAX_CACHE_SIZE

        # The oldest key should be text_0
        oldest_key = service._cache_key("text_0")
        assert oldest_key in service._cache

        # Add one more entry to trigger eviction
        new_key = service._cache_key("text_new")
        service._cache_put(new_key, [999.0] * 10)

        assert len(service._cache) == MAX_CACHE_SIZE
        assert oldest_key not in service._cache
        assert new_key in service._cache


class TestEmbedBatch:
    """Tests for EmbeddingService.embed_batch."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty_list(self) -> None:
        """Test that an empty input list returns an empty output list."""
        service = EmbeddingService(api_key="test-key")
        result = await service.embed_batch([])
        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_splits_into_correct_api_calls(self) -> None:
        """Test that 250 texts with batch_size=100 produces 3 API calls."""
        num_texts = 250
        batch_size = 100
        expected_calls = math.ceil(num_texts / batch_size)  # 3

        embedding_vec = [0.5] * 1536

        # Build responses for each batch: 100, 100, 50
        responses = []
        for i in range(expected_calls):
            if i < expected_calls - 1:
                count = batch_size
            else:
                count = num_texts - batch_size * (expected_calls - 1)
            responses.append(_make_success_response([embedding_vec] * count))

        mock_client = _build_mock_client(responses)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client):
            service = EmbeddingService(api_key="test-key")
            texts = [f"text_{i}" for i in range(num_texts)]
            result = await service.embed_batch(texts, batch_size=batch_size)

        assert len(result) == num_texts
        assert mock_client.post.await_count == expected_calls

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_uses_cache_for_already_embedded_texts(self) -> None:
        """Test that cached texts are excluded from API batch calls."""
        embedding_a = [0.1] * 1536
        embedding_b = [0.2] * 1536

        # Pre-embed "hello" so it is cached
        response_single = _make_success_response([embedding_a])
        mock_client_single = _build_mock_client(response_single)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client_single):
            service = EmbeddingService(api_key="test-key")
            await service.embed_text("hello")

        # Now batch embed ["hello", "world"] -- only "world" should hit API
        response_batch = _make_success_response([embedding_b])
        mock_client_batch = _build_mock_client(response_batch)

        with patch("src.memory.embedding.httpx.AsyncClient", return_value=mock_client_batch):
            result = await service.embed_batch(["hello", "world"])

        assert len(result) == 2
        assert result[0] == embedding_a  # from cache
        assert result[1] == embedding_b  # from API
        assert mock_client_batch.post.await_count == 1
