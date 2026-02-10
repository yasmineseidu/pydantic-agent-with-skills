"""Redis-backed embedding vector cache."""

import hashlib
import json
import logging
from typing import Optional

from src.cache.client import RedisManager

logger = logging.getLogger(__name__)

_EMBEDDING_CACHE_TTL: int = 86400  # 24 hours


class EmbeddingCache:
    """Redis-backed embedding cache with 24h TTL.

    Supplements Phase 2 in-memory LRU cache with persistent Redis storage.
    Key format: {prefix}embed:{sha256_of_normalized_text}

    Attributes:
        _redis_manager: RedisManager instance for Redis operations.
    """

    def __init__(self, redis_manager: RedisManager) -> None:
        """Initialize the embedding cache.

        Args:
            redis_manager: RedisManager instance for Redis operations.
        """
        self._redis_manager: RedisManager = redis_manager

    async def get_embedding(self, text: str) -> Optional[list[float]]:
        """Check Redis for cached embedding.

        Args:
            text: The text to look up in cache.

        Returns:
            Cached embedding vector, or None if not found or Redis unavailable.
        """
        if not self._redis_manager.available:
            return None

        try:
            client = await self._redis_manager.get_client()
            if client is None:
                return None

            key: str = self._cache_key(text)
            value: Optional[str] = await client.get(key)  # type: ignore[misc, union-attr]

            if value is None:
                logger.info(f"embedding_cache_miss: text_length={len(text)}")
                return None

            embedding: list[float] = json.loads(value)
            logger.info(f"embedding_cache_hit: text_length={len(text)}")
            return embedding

        except json.JSONDecodeError as e:
            logger.warning(f"embedding_cache_json_error: text_length={len(text)}, error={str(e)}")
            return None
        except Exception as e:
            logger.warning(f"embedding_cache_get_error: text_length={len(text)}, error={str(e)}")
            return None

    async def store_embedding(self, text: str, embedding: list[float]) -> None:
        """Store embedding in Redis with 24h TTL.

        Args:
            text: The text that was embedded.
            embedding: The embedding vector to cache.
        """
        if not self._redis_manager.available:
            return

        try:
            client = await self._redis_manager.get_client()
            if client is None:
                return

            key: str = self._cache_key(text)
            value: str = json.dumps(embedding)

            await client.setex(key, _EMBEDDING_CACHE_TTL, value)  # type: ignore[misc, union-attr]
            logger.info(
                f"embedding_cache_store: text_length={len(text)}, "
                f"vector_dimensions={len(embedding)}"
            )

        except Exception as e:
            logger.warning(f"embedding_cache_store_error: text_length={len(text)}, error={str(e)}")

    def _cache_key(self, text: str) -> str:
        """Build Redis key from normalized text SHA-256.

        Args:
            text: Raw input text.

        Returns:
            Redis key with prefix and SHA-256 digest.
        """
        normalized: str = self._normalize(text)
        digest: str = hashlib.sha256(normalized.encode()).hexdigest()
        return f"{self._redis_manager.key_prefix}embed:{digest}"

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for consistent cache keys.

        Args:
            text: Raw input text.

        Returns:
            Normalized text (lowercased and stripped).
        """
        return text.lower().strip()
