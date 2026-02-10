"""Embedding service with caching and retry logic."""

import asyncio
import hashlib
import logging
from collections import OrderedDict

import httpx

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 1.0  # seconds

# Cache configuration
MAX_CACHE_SIZE: int = 1000


class EmbeddingService:
    """Async embedding service with LRU caching and exponential backoff.

    Provides single-text and batch embedding via the OpenAI-compatible
    embeddings API. Caches results in an in-memory LRU dict keyed by
    SHA-256 of normalized text.

    Attributes:
        _api_key: API key for the embeddings provider (never logged).
        _model: Embedding model name.
        _dimensions: Output vector dimensionality.
        _base_url: Base URL for the embeddings API.
        _cache: OrderedDict acting as an LRU cache.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        """Initialize the embedding service.

        Args:
            api_key: API key for the embeddings provider.
            model: Embedding model name.
            dimensions: Output vector dimensionality.
            base_url: Base URL for the embeddings API.
        """
        self._api_key: str = api_key
        self._model: str = model
        self._dimensions: int = dimensions
        self._base_url: str = base_url.rstrip("/")
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    def _cache_key(self, text: str) -> str:
        """Compute a cache key from normalized text.

        Args:
            text: Raw input text.

        Returns:
            SHA-256 hex digest of lowercased, stripped text.
        """
        normalized: str = text.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _cache_get(self, key: str) -> list[float] | None:
        """Retrieve a cached embedding, promoting it to most-recent.

        Args:
            key: SHA-256 cache key.

        Returns:
            Cached embedding vector, or None if not found.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, embedding: list[float]) -> None:
        """Store an embedding in the LRU cache, evicting if full.

        Args:
            key: SHA-256 cache key.
            embedding: The embedding vector to cache.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = embedding
            return

        if len(self._cache) >= MAX_CACHE_SIZE:
            self._cache.popitem(last=False)

        self._cache[key] = embedding

    async def _call_api(
        self,
        input_data: str | list[str],
    ) -> list[list[float]]:
        """Call the embeddings API with exponential backoff on 429.

        Args:
            input_data: A single text string or list of strings to embed.

        Returns:
            List of embedding vectors, one per input text.

        Raises:
            RuntimeError: On non-429 HTTP errors or exhausted retries.
        """
        last_error: str | None = None

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self._model,
                            "input": input_data,
                            "dimensions": self._dimensions,
                        },
                    )

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    delay: float = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"embedding_rate_limited: attempt={attempt + 1}/{MAX_RETRIES}, "
                        f"retrying_in={delay}s"
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise RuntimeError(
                            f"Embedding API rate limited (HTTP 429) after {MAX_RETRIES} retries"
                        )

                # Handle other HTTP errors
                if response.status_code >= 400:
                    error_msg = (
                        f"Embedding API error: HTTP {response.status_code} - {response.text[:200]}"
                    )
                    logger.error(f"embedding_api_error: status={response.status_code}")
                    raise RuntimeError(error_msg)

                # Parse successful response
                data = response.json()
                embeddings: list[list[float]] = [item["embedding"] for item in data["data"]]
                return embeddings

            except httpx.TimeoutException:
                last_error = "Embedding API request timed out"
                logger.error(f"embedding_timeout: attempt={attempt + 1}/{MAX_RETRIES}")
            except httpx.RequestError as e:
                last_error = f"Embedding API request failed: {e}"
                logger.error(
                    f"embedding_request_error: attempt={attempt + 1}/{MAX_RETRIES}, error={e}"
                )
            except RuntimeError:
                raise
            except Exception as e:
                last_error = f"Embedding API unexpected error: {e}"
                logger.error(
                    f"embedding_unexpected_error: attempt={attempt + 1}/{MAX_RETRIES}, error={e}"
                )

        raise RuntimeError(last_error or "Embedding API failed after retries")

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string, using cache when available.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            RuntimeError: If the API call fails after retries.
        """
        key: str = self._cache_key(text)
        cached: list[float] | None = self._cache_get(key)

        if cached is not None:
            logger.info(f"embedding_generated: text_length={len(text)}, cached=True")
            return cached

        embeddings: list[list[float]] = await self._call_api(text)
        embedding: list[float] = embeddings[0]

        self._cache_put(key, embedding)
        logger.info(f"embedding_generated: text_length={len(text)}, cached=False")

        return embedding

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Embed a list of texts in batches, using cache when available.

        Splits the input into batches of ``batch_size``. Each batch is
        sent as a single API call. Texts already in the cache are served
        from cache and excluded from the API request.

        Args:
            texts: List of texts to embed.
            batch_size: Maximum number of texts per API call.

        Returns:
            List of embedding vectors, one per input text, in the same order.

        Raises:
            RuntimeError: If any API call fails after retries.
        """
        if not texts:
            return []

        # Build results array; fill from cache where possible
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []

        for i, text in enumerate(texts):
            key: str = self._cache_key(text)
            cached: list[float] | None = self._cache_get(key)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)

        # Batch the uncached texts
        batch_count: int = 0
        for batch_start in range(0, len(uncached_indices), batch_size):
            batch_indices: list[int] = uncached_indices[batch_start : batch_start + batch_size]
            batch_texts: list[str] = [texts[i] for i in batch_indices]

            embeddings: list[list[float]] = await self._call_api(batch_texts)
            batch_count += 1

            for idx, embedding in zip(batch_indices, embeddings):
                results[idx] = embedding
                cache_key: str = self._cache_key(texts[idx])
                self._cache_put(cache_key, embedding)

        logger.info(f"embedding_batch: batch_count={batch_count}, total_texts={len(texts)}")

        # All slots should be filled; cast away the None possibility
        return [r for r in results if r is not None]
