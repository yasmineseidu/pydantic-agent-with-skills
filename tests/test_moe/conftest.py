"""Shared fixtures for MoE model routing tests."""

import pytest

from src.moe.model_tier import ComplexityScore, ModelTier


@pytest.fixture
def fast_tier() -> ModelTier:
    """Return a fast/cheap model tier (e.g. Haiku).

    Returns:
        A ModelTier configured as the fast tier.
    """
    return ModelTier(
        name="fast",
        model_name="anthropic/claude-haiku-4.5",
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
    )


@pytest.fixture
def balanced_tier() -> ModelTier:
    """Return a balanced model tier (e.g. Sonnet).

    Returns:
        A ModelTier configured as the balanced tier.
    """
    return ModelTier(
        name="balanced",
        model_name="anthropic/claude-sonnet-4.5",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    )


@pytest.fixture
def powerful_tier() -> ModelTier:
    """Return a powerful/expensive model tier (e.g. Opus).

    Returns:
        A ModelTier configured as the powerful tier.
    """
    return ModelTier(
        name="powerful",
        model_name="anthropic/claude-opus-4",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    )


@pytest.fixture
def zero_complexity() -> ComplexityScore:
    """Return a ComplexityScore with all dimensions at zero.

    Returns:
        A ComplexityScore where every dimension is 0.0.
    """
    return ComplexityScore(
        reasoning_depth=0.0,
        domain_specificity=0.0,
        creativity=0.0,
        context_dependency=0.0,
        output_length=0.0,
    )


@pytest.fixture
def max_complexity() -> ComplexityScore:
    """Return a ComplexityScore with all dimensions at maximum (10.0).

    Returns:
        A ComplexityScore where every dimension is 10.0.
    """
    return ComplexityScore(
        reasoning_depth=10.0,
        domain_specificity=10.0,
        creativity=10.0,
        context_dependency=10.0,
        output_length=10.0,
    )
