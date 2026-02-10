"""Shared fixtures for memory system tests."""

from datetime import datetime, timezone
from typing import Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.agent_models import (
    AgentBoundaries,
    AgentDNA,
    AgentMemoryConfig,
    AgentModelConfig,
    AgentPersonality,
    AgentStatus,
)
from src.models.memory_models import (
    MemoryRecord,
    MemorySource,
    MemoryStatus,
    MemoryTier,
    MemoryType,
)


@pytest.fixture
def sample_memory_record() -> Callable[..., MemoryRecord]:
    """Factory fixture that returns a valid MemoryRecord.

    Returns:
        A callable that creates MemoryRecord instances with optional overrides.
    """

    def _factory(**overrides: object) -> MemoryRecord:
        now = datetime.now(tz=timezone.utc)
        defaults: dict[str, object] = {
            "id": uuid4(),
            "team_id": uuid4(),
            "memory_type": MemoryType.SEMANTIC,
            "content": "The user prefers dark mode in all applications.",
            "subject": "user_preference",
            "importance": 7,
            "confidence": 0.9,
            "access_count": 3,
            "is_pinned": False,
            "source_type": MemorySource.EXTRACTION,
            "source_conversation_id": uuid4(),
            "source_message_ids": [],
            "extraction_model": "anthropic/claude-sonnet-4.5",
            "version": 1,
            "superseded_by": None,
            "contradicts": [],
            "related_to": [],
            "metadata": {},
            "tier": MemoryTier.WARM,
            "status": MemoryStatus.ACTIVE,
            "created_at": now,
            "updated_at": now,
            "last_accessed_at": now,
            "expires_at": None,
        }
        defaults.update(overrides)
        return MemoryRecord(**defaults)  # type: ignore[arg-type]

    return _factory


@pytest.fixture
def sample_agent_dna() -> Callable[..., AgentDNA]:
    """Factory fixture that returns a valid AgentDNA.

    Returns:
        A callable that creates AgentDNA instances with optional overrides.
    """

    def _factory(**overrides: object) -> AgentDNA:
        now = datetime.now(tz=timezone.utc)
        defaults: dict[str, object] = {
            "id": uuid4(),
            "team_id": uuid4(),
            "name": "Memory Test Agent",
            "slug": "memory-test-agent",
            "tagline": "An agent for memory testing",
            "personality": AgentPersonality(system_prompt_template="You are a memory test agent."),
            "shared_skill_names": ["search"],
            "custom_skill_names": [],
            "disabled_skill_names": [],
            "model": AgentModelConfig(),
            "memory": AgentMemoryConfig(),
            "boundaries": AgentBoundaries(),
            "status": AgentStatus.ACTIVE,
            "created_at": now,
            "updated_at": now,
            "created_by": uuid4(),
        }
        defaults.update(overrides)
        return AgentDNA(**defaults)  # type: ignore[arg-type]

    return _factory


@pytest.fixture
def mock_embedding() -> list[float]:
    """Return a 1536-dimensional embedding vector of zeros.

    Returns:
        A list of 1536 floats suitable for use as a mock embedding.
    """
    return [0.0] * 1536


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a mock AsyncSession for database testing.

    Returns:
        An AsyncMock configured to behave like an AsyncSession.
    """
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    # Support async context manager protocol
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session
