"""Tests for Phase 7 MoE expert models."""

from __future__ import annotations

import pytest

from uuid import uuid4

from src.moe.models import AggregatedResponse, ExpertResponse, ExpertScore, SelectionResult


def test_expert_score_weights_sum_to_one() -> None:
    """ExpertScore weights should sum to 1.0."""
    total = sum(ExpertScore.WEIGHTS.values())
    assert pytest.approx(total, rel=1e-6) == 1.0


def test_expert_score_overall_weighted_sum() -> None:
    """Overall score should match weighted sum of signals."""
    score = ExpertScore(
        skill_match=8.0,
        past_performance=6.0,
        personality_fit=4.0,
        load_balance=2.0,
    )
    expected = (
        8.0 * ExpertScore.WEIGHTS["skill_match"]
        + 6.0 * ExpertScore.WEIGHTS["past_performance"]
        + 4.0 * ExpertScore.WEIGHTS["personality_fit"]
        + 2.0 * ExpertScore.WEIGHTS["load_balance"]
    )
    assert score.overall == expected


def test_expert_score_bounds_validation() -> None:
    """ExpertScore enforces 0-10 bounds for signals."""
    with pytest.raises(ValueError):
        ExpertScore(skill_match=11.0, past_performance=0.0, personality_fit=0.0, load_balance=0.0)


def test_selection_result_schema() -> None:
    """SelectionResult serializes expected fields."""
    score = ExpertScore(
        skill_match=7.0,
        past_performance=7.0,
        personality_fit=7.0,
        load_balance=7.0,
    )
    result = SelectionResult(
        expert_id=uuid4(),
        expert_name="Expert",
        score=score,
        reasoning="Matched skills",
        rank=1,
    )
    assert result.rank == 1
    assert result.score.overall > 0


def test_aggregated_response_contains_experts() -> None:
    """AggregatedResponse should include expert responses."""
    response = ExpertResponse(
        expert_id=uuid4(),
        expert_name="Analyst",
        response="Output",
        confidence=0.9,
    )
    aggregated = AggregatedResponse(
        final_response="Combined",
        expert_responses=[response],
        aggregation_method="synthesis",
        confidence=0.9,
    )
    assert aggregated.expert_responses[0].expert_name == "Analyst"
