"""Embedding service with caching and retry logic."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from src.cache.embedding_cache import EmbeddingCache

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 1.0  # seconds

# Cache configuration
MAX_CACHE_SIZE: int = 1000


class EmbeddingService:
    """Async embedding service with L1 LRU + optional L2 Redis caching and exponential backoff.

    Provides single-text and batch embedding via the OpenAI-compatible
    embeddings API. Three-tier caching strategy:
    - L1: In-memory LRU cache (1000 entries, instant)
    - L2: Optional Redis cache (24h TTL, milliseconds)
    - L3: API call (seconds, costs money)

    Attributes:
        _api_key: API key for the embeddings provider (never logged).
        _model: Embedding model name.
        _dimensions: Output vector dimensionality.
        _base_url: Base URL for the embeddings API.
        _cache: OrderedDict acting as L1 LRU cache.
        _redis_cache: Optional EmbeddingCache for L2 persistent cache.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        redis_cache: EmbeddingCache | None = None,
    ) -> None:
        """Initialize the embedding service.

        Args:
            api_key: API key for the embeddings provider.
            model: Embedding model name.
            dimensions: Output vector dimensionality.
            base_url: Base URL for the embeddings API.
            redis_cache: Optional Redis cache for L2 persistent caching.
        """
        self._api_key: str = api_key
        self._model: str = model
        self._dimensions: int = dimensions
        self._base_url: str = base_url.rstrip("/")
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._redis_cache: EmbeddingCache | None = redis_cache

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
        """Embed a single text string, using L1 LRU → L2 Redis → L3 API tiers.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            RuntimeError: If the API call fails after retries.
        """
        key: str = self._cache_key(text)

        # L1: Check in-memory LRU cache
        cached: list[float] | None = self._cache_get(key)
        if cached is not None:
            logger.info(f"embedding_generated: text_length={len(text)}, source=l1_lru")
            return cached

        # L2: Check Redis cache
        if self._redis_cache is not None:
            redis_cached: list[float] | None = await self._redis_cache.get_embedding(text)
            if redis_cached is not None:
                # Promote to L1
                self._cache_put(key, redis_cached)
                logger.info(f"embedding_generated: text_length={len(text)}, source=l2_redis")
                return redis_cached

        # L3: Call API
        embeddings: list[list[float]] = await self._call_api(text)
        embedding: list[float] = embeddings[0]

        # Store in L1 + L2
        self._cache_put(key, embedding)
        if self._redis_cache is not None:
            await self._redis_cache.store_embedding(text, embedding)

        logger.info(f"embedding_generated: text_length={len(text)}, source=l3_api")

        return embedding

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float] | None]:
        """Embed a list of texts in batches, using L1 → L2 → L3 cache tiers.

        Splits the input into batches of ``batch_size``. Each batch is
        sent as a single API call. Texts already in L1 or L2 cache are served
        from cache and excluded from the API request.

        Index correspondence is preserved: ``results[i]`` always corresponds
        to ``texts[i]``. If a particular embedding could not be obtained
        (e.g. partial API failure), the slot will be ``None``.

        Args:
            texts: List of texts to embed.
            batch_size: Maximum number of texts per API call.

        Returns:
            List of embedding vectors (or None on failure), one per input
            text, in the same order.

        Raises:
            RuntimeError: If any API call fails after retries.
        """
        if not texts:
            return []

        # L1: Build results array; fill from LRU cache where possible
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []

        for i, text in enumerate(texts):
            key: str = self._cache_key(text)
            cached: list[float] | None = self._cache_get(key)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)

        # L2: Check Redis for remaining uncached texts
        still_uncached_indices: list[int] = []
        if self._redis_cache is not None:
            for i in uncached_indices:
                redis_cached: list[float] | None = await self._redis_cache.get_embedding(texts[i])
                if redis_cached is not None:
                    results[i] = redis_cached
                    # Promote to L1
                    cache_key: str = self._cache_key(texts[i])
                    self._cache_put(cache_key, redis_cached)
                else:
                    still_uncached_indices.append(i)
        else:
            still_uncached_indices = uncached_indices

        # L3: Batch the remaining uncached texts via API
        batch_count: int = 0
        for batch_start in range(0, len(still_uncached_indices), batch_size):
            batch_indices: list[int] = still_uncached_indices[
                batch_start : batch_start + batch_size
            ]
            batch_texts: list[str] = [texts[i] for i in batch_indices]

            embeddings: list[list[float]] = await self._call_api(batch_texts)
            batch_count += 1

            for idx, embedding in zip(batch_indices, embeddings):
                results[idx] = embedding
                cache_key = self._cache_key(texts[idx])
                self._cache_put(cache_key, embedding)
                # Store in L2 Redis
                if self._redis_cache is not None:
                    await self._redis_cache.store_embedding(texts[idx], embedding)

        logger.info(f"embedding_batch: batch_count={batch_count}, total_texts={len(texts)}")

        # Preserve index correspondence: results[i] matches texts[i].
        # Slots that could not be filled remain None so callers can handle them.
        return results
