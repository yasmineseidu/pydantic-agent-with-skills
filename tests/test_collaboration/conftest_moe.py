"""Additional fixtures for MoE (Mixture of Experts) testing."""

from typing import List

import pytest

from src.moe.models import ExpertScore


@pytest.fixture
def sample_expert_scores() -> List[ExpertScore]:
    """Sample expert scores with known values for testing.

    Returns:
        A list of 5 ExpertScore instances with predetermined values.
    """
    return [
        ExpertScore(
            skill_match=0.95,
            past_performance=0.85,
            personality_fit=0.75,
            load_balance=0.90,
        ),
        ExpertScore(
            skill_match=0.80,
            past_performance=0.70,
            personality_fit=0.65,
            load_balance=0.85,
        ),
        ExpertScore(
            skill_match=0.70,
            past_performance=0.60,
            personality_fit=0.55,
            load_balance=0.80,
        ),
        ExpertScore(
            skill_match=0.55,
            past_performance=0.45,
            personality_fit=0.40,
            load_balance=0.75,
        ),
        ExpertScore(
            skill_match=0.40,
            past_performance=0.30,
            personality_fit=0.25,
            load_balance=0.60,
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
            skill_match=0.97,
            past_performance=0.93,
            personality_fit=0.90,
            load_balance=0.95,
        ),
        ExpertScore(
            skill_match=0.87,
            past_performance=0.83,
            personality_fit=0.80,
            load_balance=0.90,
        ),
        ExpertScore(
            skill_match=0.77,
            past_performance=0.73,
            personality_fit=0.70,
            load_balance=0.85,
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
            skill_match=0.60,
            past_performance=0.50,
            personality_fit=0.45,
            load_balance=0.55,
        ),
        ExpertScore(
            skill_match=0.50,
            past_performance=0.40,
            personality_fit=0.35,
            load_balance=0.50,
        ),
        ExpertScore(
            skill_match=0.40,
            past_performance=0.30,
            personality_fit=0.25,
            load_balance=0.45,
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
            skill_match=0.92,
            past_performance=0.88,
            personality_fit=0.84,
            load_balance=0.90,
        ),
        ExpertScore(
            skill_match=0.45,
            past_performance=0.35,
            personality_fit=0.30,
            load_balance=0.40,
        ),
        ExpertScore(
            skill_match=0.75,
            past_performance=0.65,
            personality_fit=0.60,
            load_balance=0.70,
        ),
        ExpertScore(
            skill_match=0.30,
            past_performance=0.20,
            personality_fit=0.15,
            load_balance=0.25,
        ),
    ]
