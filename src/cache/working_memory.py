"""Working memory cache for active conversation state."""

import json
import logging
from typing import Any, Optional
from uuid import UUID

from src.cache.client import RedisManager

logger = logging.getLogger(__name__)

_WORKING_MEMORY_TTL: int = 7200  # 2 hours


class WorkingMemoryCache:
    """Manage active conversation state in Redis HASH.

    Stores conversation context, turns, and arbitrary fields in a Redis HASH.
    TTL: 2 hours, refreshed on writes.
    Key format: {prefix}working:{conversation_id}

    Attributes:
        _redis_manager: RedisManager instance for Redis operations.
    """

    def __init__(self, redis_manager: RedisManager) -> None:
        """Initialize WorkingMemoryCache.

        Args:
            redis_manager: RedisManager instance for Redis operations.
        """
        self._redis_manager: RedisManager = redis_manager

    async def set_context(self, conversation_id: UUID, context: dict[str, Any]) -> None:
        """Store full context as JSON in HASH field 'context'. TTL 2h.

        Args:
            conversation_id: Unique identifier for the conversation.
            context: Context dictionary to store.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"set_context_skipped: conversation_id={conversation_id}, redis_unavailable=True"
            )
            return

        key = self._key(conversation_id)
        try:
            context_json = json.dumps(context, default=str)
            await client.hset(key, "context", context_json)  # type: ignore[misc, union-attr]
            await client.expire(key, _WORKING_MEMORY_TTL)  # type: ignore[misc, union-attr]
            logger.info(
                f"set_context_success: conversation_id={conversation_id}, ttl={_WORKING_MEMORY_TTL}"
            )
        except Exception as e:
            logger.warning(f"set_context_error: conversation_id={conversation_id}, error={str(e)}")

    async def get_context(self, conversation_id: UUID) -> Optional[dict[str, Any]]:
        """Get context from HASH field 'context'. Returns None on miss or Redis unavailable.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Context dictionary, or None if not found or Redis unavailable.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"get_context_skipped: conversation_id={conversation_id}, redis_unavailable=True"
            )
            return None

        key = self._key(conversation_id)
        try:
            context_json = await client.hget(key, "context")  # type: ignore[misc, union-attr]
            if context_json is None:
                logger.info(f"get_context_miss: conversation_id={conversation_id}")
                return None

            context: dict[str, Any] = json.loads(context_json)
            logger.info(f"get_context_hit: conversation_id={conversation_id}")
            return context
        except Exception as e:
            logger.warning(f"get_context_error: conversation_id={conversation_id}, error={str(e)}")
            return None

    async def append_turn(self, conversation_id: UUID, role: str, content: str) -> None:
        """Append turn to HASH field 'turns' (JSON list). Refresh TTL.

        Args:
            conversation_id: Unique identifier for the conversation.
            role: Role of the message sender (user/assistant/system/tool).
            content: Message content.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"append_turn_skipped: conversation_id={conversation_id}, redis_unavailable=True"
            )
            return

        key = self._key(conversation_id)
        try:
            # Read existing turns
            turns_json = await client.hget(key, "turns")  # type: ignore[misc, union-attr]
            if turns_json is None:
                turns: list[dict[str, str]] = []
            else:
                turns = json.loads(turns_json)

            # Append new turn
            turns.append({"role": role, "content": content})
            new_turns_json = json.dumps(turns, default=str)

            # Write back and refresh TTL
            await client.hset(key, "turns", new_turns_json)  # type: ignore[misc, union-attr]
            await client.expire(key, _WORKING_MEMORY_TTL)  # type: ignore[misc, union-attr]
            logger.info(
                f"append_turn_success: conversation_id={conversation_id}, role={role}, turn_count={len(turns)}, ttl={_WORKING_MEMORY_TTL}"
            )
        except Exception as e:
            logger.warning(f"append_turn_error: conversation_id={conversation_id}, error={str(e)}")

    async def get_turns(self, conversation_id: UUID) -> list[dict[str, str]]:
        """Get list of turns from HASH field 'turns'. Empty list on miss.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            List of {"role": ..., "content": ...} dicts. Empty list on miss.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"get_turns_skipped: conversation_id={conversation_id}, redis_unavailable=True"
            )
            return []

        key = self._key(conversation_id)
        try:
            turns_json = await client.hget(key, "turns")  # type: ignore[misc, union-attr]
            if turns_json is None:
                logger.info(f"get_turns_miss: conversation_id={conversation_id}")
                return []

            turns: list[dict[str, str]] = json.loads(turns_json)
            logger.info(f"get_turns_hit: conversation_id={conversation_id}, count={len(turns)}")
            return turns
        except Exception as e:
            logger.warning(f"get_turns_error: conversation_id={conversation_id}, error={str(e)}")
            return []

    async def set_field(self, conversation_id: UUID, field: str, value: Any) -> None:
        """Set arbitrary HASH field. Refresh TTL.

        Args:
            conversation_id: Unique identifier for the conversation.
            field: Field name to set.
            value: Value to store (will be JSON serialized).
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"set_field_skipped: conversation_id={conversation_id}, field={field}, redis_unavailable=True"
            )
            return

        key = self._key(conversation_id)
        try:
            value_json = json.dumps(value, default=str)
            await client.hset(key, field, value_json)  # type: ignore[misc, union-attr]
            await client.expire(key, _WORKING_MEMORY_TTL)  # type: ignore[misc, union-attr]
            logger.info(
                f"set_field_success: conversation_id={conversation_id}, field={field}, ttl={_WORKING_MEMORY_TTL}"
            )
        except Exception as e:
            logger.warning(
                f"set_field_error: conversation_id={conversation_id}, field={field}, error={str(e)}"
            )

    async def get_field(self, conversation_id: UUID, field: str) -> Optional[Any]:
        """Get arbitrary HASH field. Returns None on miss.

        Args:
            conversation_id: Unique identifier for the conversation.
            field: Field name to get.

        Returns:
            Field value (JSON deserialized), or None if not found or Redis unavailable.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"get_field_skipped: conversation_id={conversation_id}, field={field}, redis_unavailable=True"
            )
            return None

        key = self._key(conversation_id)
        try:
            value_json = await client.hget(key, field)  # type: ignore[misc, union-attr]
            if value_json is None:
                logger.info(f"get_field_miss: conversation_id={conversation_id}, field={field}")
                return None

            value = json.loads(value_json)
            logger.info(f"get_field_hit: conversation_id={conversation_id}, field={field}")
            return value
        except Exception as e:
            logger.warning(
                f"get_field_error: conversation_id={conversation_id}, field={field}, error={str(e)}"
            )
            return None

    async def delete(self, conversation_id: UUID) -> None:
        """Delete the working memory key entirely.

        Args:
            conversation_id: Unique identifier for the conversation.
        """
        client = await self._redis_manager.get_client()
        if client is None:
            logger.warning(
                f"delete_skipped: conversation_id={conversation_id}, redis_unavailable=True"
            )
            return

        key = self._key(conversation_id)
        try:
            deleted = await client.delete(key)  # type: ignore[misc, union-attr]
            logger.info(f"delete_success: conversation_id={conversation_id}, deleted={deleted}")
        except Exception as e:
            logger.warning(f"delete_error: conversation_id={conversation_id}, error={str(e)}")

    def _key(self, conversation_id: UUID) -> str:
        """Generate Redis key for working memory.

        Args:
            conversation_id: Unique identifier for the conversation.

        Returns:
            Redis key string in format {prefix}working:{conversation_id}.
        """
        return f"{self._redis_manager.key_prefix}working:{conversation_id}"
