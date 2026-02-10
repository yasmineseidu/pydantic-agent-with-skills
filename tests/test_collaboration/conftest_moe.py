"""Additional fixtures for MoE (Mixture of Experts) testing."""

from typing import List
from uuid import uuid4

import pytest

from src.collaboration.types import ExpertScore


@pytest.fixture
def sample_expert_scores() -> List[ExpertScore]:
    """Sample expert scores with known values for testing.

    Returns:
        A list of 5 ExpertScore instances with predetermined values.
    """
    return [
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.9,
            skill_match=0.95,
            context_match=0.85,
            availability=1.0,
            metadata={"rank": 1},
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.75,
            skill_match=0.80,
            context_match=0.70,
            availability=1.0,
            metadata={"rank": 2},
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.65,
            skill_match=0.70,
            context_match=0.60,
            availability=1.0,
            metadata={"rank": 3},
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.50,
            skill_match=0.55,
            context_match=0.45,
            availability=0.8,
            metadata={"rank": 4},
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.35,
            skill_match=0.40,
            context_match=0.30,
            availability=0.5,
            metadata={"rank": 5},
        ),
    ]


@pytest.fixture
def high_confidence_scores() -> List[ExpertScore]:
    """Expert scores with all high confidence values (>0.6).

    Returns:
        A list of ExpertScore instances with high confidence.
    """
    return [
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.95,
            skill_match=0.97,
            context_match=0.93,
            availability=1.0,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.85,
            skill_match=0.87,
            context_match=0.83,
            availability=1.0,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.75,
            skill_match=0.77,
            context_match=0.73,
            availability=1.0,
        ),
    ]


@pytest.fixture
def low_confidence_scores() -> List[ExpertScore]:
    """Expert scores with all low confidence values (<0.6).

    Returns:
        A list of ExpertScore instances with low confidence.
    """
    return [
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.55,
            skill_match=0.60,
            context_match=0.50,
            availability=1.0,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.45,
            skill_match=0.50,
            context_match=0.40,
            availability=0.8,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.35,
            skill_match=0.40,
            context_match=0.30,
            availability=0.6,
        ),
    ]


@pytest.fixture
def mixed_confidence_scores() -> List[ExpertScore]:
    """Expert scores with mixed confidence values (some high, some low).

    Returns:
        A list of ExpertScore instances with varied confidence levels.
    """
    return [
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.90,
            skill_match=0.92,
            context_match=0.88,
            availability=1.0,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.40,
            skill_match=0.45,
            context_match=0.35,
            availability=0.9,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.70,
            skill_match=0.75,
            context_match=0.65,
            availability=1.0,
        ),
        ExpertScore(
            agent_id=uuid4(),
            confidence=0.25,
            skill_match=0.30,
            context_match=0.20,
            availability=0.5,
        ),
    ]
