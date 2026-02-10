"""Tests for ExpertSelector selection strategies."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from src.moe.expert_selector import ExpertSelector, ExpertSelectionResult, SelectionStrategyEnum
from src.moe.models import ExpertScore


def _mock_settings(enable_ensemble: bool = True) -> SimpleNamespace:
    """Create mock settings with feature flags.

    Args:
        enable_ensemble: Whether ensemble mode is enabled.

    Returns:
        Mock settings object with feature flags.
    """
    return SimpleNamespace(
        feature_flags=SimpleNamespace(
            enable_expert_gate=True,
            enable_ensemble_mode=enable_ensemble,
        )
    )


def _create_score(overall: float = 7.0) -> ExpertScore:
    """Create an ExpertScore with specified overall score.

    Args:
        overall: Target overall score (0.0-10.0).

    Returns:
        ExpertScore instance with weighted signals that produce the overall score.
    """
    # Use equal values for all signals to achieve target overall
    # With weights: skill_match=0.40, past_performance=0.25, personality_fit=0.20, load_balance=0.15
    # Equal values produce same overall score
    return ExpertScore(
        skill_match=overall,
        past_performance=overall,
        personality_fit=overall,
        load_balance=overall,
    )


def _create_scores(count: int = 3, start_score: float = 8.0) -> list[tuple[UUID, str, ExpertScore]]:
    """Create a list of scored agents in descending order.

    Args:
        count: Number of agents to create.
        start_score: Score for the best agent (decrements by 1.0 for each).

    Returns:
        List of (agent_id, agent_name, score) tuples sorted by score descending.
    """
    scores = []
    for i in range(count):
        agent_id = uuid4()
        agent_name = f"agent-{i + 1}"
        score = _create_score(max(0.0, start_score - i * 1.0))
        scores.append((agent_id, agent_name, score))
    return scores


# =============================================================================
# TOP_1 Strategy Tests
# =============================================================================


def test_select_top_1_above_threshold() -> None:
    """TOP_1 returns best agent when score >= threshold."""
    selector = ExpertSelector(settings=_mock_settings())
    scores = _create_scores(count=3, start_score=8.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 1
    assert result.agents[0].expert_name == "agent-1"
    assert result.agents[0].score.overall == 8.0
    assert result.fallback_used is False
    assert result.strategy == SelectionStrategyEnum.TOP_1
    assert "TOP_1" in result.reasoning
    assert result.agents[0].rank == 1


def test_select_top_1_below_threshold_fallback() -> None:
    """TOP_1 falls back when best score < threshold."""
    fallback_id = uuid4()
    selector = ExpertSelector(
        settings=_mock_settings(),
        fallback_agent_id=fallback_id,
        fallback_agent_name="fallback-agent",
    )
    scores = _create_scores(count=2, start_score=5.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 1
    assert result.agents[0].expert_id == fallback_id
    assert result.agents[0].expert_name == "fallback-agent"
    assert result.fallback_used is True
    assert "fallback" in result.reasoning.lower()


def test_select_top_1_empty_scores() -> None:
    """TOP_1 returns fallback when scores list is empty."""
    fallback_id = uuid4()
    selector = ExpertSelector(
        settings=_mock_settings(),
        fallback_agent_id=fallback_id,
        fallback_agent_name="fallback-agent",
    )

    result = selector.select(
        scores=[],
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 1
    assert result.agents[0].expert_id == fallback_id
    assert result.fallback_used is True


def test_select_top_1_no_fallback_configured() -> None:
    """TOP_1 returns empty list when no fallback and score below threshold."""
    selector = ExpertSelector(
        settings=_mock_settings(),
        fallback_agent_id=None,
    )
    scores = _create_scores(count=2, start_score=5.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 0
    assert result.fallback_used is True
    assert "No fallback configured" in result.reasoning


# =============================================================================
# TOP_K Strategy Tests
# =============================================================================


def test_select_top_k() -> None:
    """TOP_K returns top K agents above threshold."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_K,
        k=3,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 3
    assert result.agents[0].expert_name == "agent-1"
    assert result.agents[1].expert_name == "agent-2"
    assert result.agents[2].expert_name == "agent-3"
    assert result.agents[0].rank == 1
    assert result.agents[1].rank == 2
    assert result.agents[2].rank == 3
    assert result.fallback_used is False
    assert result.strategy == SelectionStrategyEnum.TOP_K
    assert "parallel execution" in result.reasoning


def test_select_top_k_fewer_than_k() -> None:
    """TOP_K returns all qualified agents when count < k."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    scores = _create_scores(count=2, start_score=8.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_K,
        k=5,
        confidence_threshold=6.0,
    )

    # Should return only 2 agents (all that exist)
    assert len(result.agents) == 2
    assert result.fallback_used is False


def test_select_top_k_feature_flag_disabled() -> None:
    """TOP_K falls back to TOP_1 when ensemble mode disabled."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=False))
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_K,
        k=3,
        confidence_threshold=6.0,
    )

    # Should fall back to TOP_1
    assert len(result.agents) == 1
    assert result.agents[0].expert_name == "agent-1"
    assert result.strategy == SelectionStrategyEnum.TOP_1


def test_select_top_k_threshold_filters() -> None:
    """TOP_K filters out agents below confidence threshold."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    # Create scores: 9.0, 8.0, 7.0, 6.0, 5.0
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_K,
        k=5,
        confidence_threshold=7.5,  # Only first 2 qualify
    )

    assert len(result.agents) == 2
    assert all(agent.score.overall >= 7.5 for agent in result.agents)


# =============================================================================
# ENSEMBLE Strategy Tests
# =============================================================================


def test_select_ensemble() -> None:
    """ENSEMBLE returns top K agents for weighted aggregation."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.ENSEMBLE,
        k=3,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 3
    assert result.agents[0].expert_name == "agent-1"
    assert result.agents[1].expert_name == "agent-2"
    assert result.agents[2].expert_name == "agent-3"
    assert result.fallback_used is False
    assert result.strategy == SelectionStrategyEnum.ENSEMBLE
    assert "weighted aggregation" in result.reasoning


def test_select_ensemble_feature_flag_disabled() -> None:
    """ENSEMBLE falls back to TOP_1 when ensemble mode disabled."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=False))
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.ENSEMBLE,
        k=3,
        confidence_threshold=6.0,
    )

    # Should fall back to TOP_1
    assert len(result.agents) == 1
    assert result.agents[0].expert_name == "agent-1"
    assert result.strategy == SelectionStrategyEnum.TOP_1


def test_select_ensemble_confidence_filtering() -> None:
    """ENSEMBLE only includes agents >= threshold."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.ENSEMBLE,
        k=5,
        confidence_threshold=8.5,  # Only first agent qualifies (score 9.0)
    )

    assert len(result.agents) == 1
    assert result.agents[0].score.overall >= 8.5


# =============================================================================
# CASCADE Strategy Tests
# =============================================================================


def test_select_cascade_all_qualified() -> None:
    """CASCADE returns all agents >= threshold."""
    selector = ExpertSelector(settings=_mock_settings())
    scores = _create_scores(count=5, start_score=9.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.CASCADE,
        confidence_threshold=7.0,
    )

    # Scores: 9.0, 8.0, 7.0, 6.0, 5.0 -> first 3 qualify
    assert len(result.agents) == 3
    assert result.fallback_used is False
    assert result.strategy == SelectionStrategyEnum.CASCADE
    assert "sequential fallback" in result.reasoning


def test_select_cascade_with_fallback() -> None:
    """CASCADE uses fallback when no agents meet threshold."""
    fallback_id = uuid4()
    selector = ExpertSelector(
        settings=_mock_settings(),
        fallback_agent_id=fallback_id,
        fallback_agent_name="fallback-agent",
    )
    scores = _create_scores(count=3, start_score=5.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.CASCADE,
        confidence_threshold=6.0,
    )

    assert len(result.agents) == 1
    assert result.agents[0].expert_id == fallback_id
    assert result.fallback_used is True


def test_select_cascade_ordering() -> None:
    """CASCADE returns agents sorted by score descending."""
    selector = ExpertSelector(settings=_mock_settings())
    scores = _create_scores(count=4, start_score=10.0)

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.CASCADE,
        confidence_threshold=0.0,  # Accept all
    )

    assert len(result.agents) == 4
    # Verify descending order
    for i in range(len(result.agents) - 1):
        assert result.agents[i].score.overall >= result.agents[i + 1].score.overall
    # Verify ranks are sequential
    for i, agent in enumerate(result.agents, start=1):
        assert agent.rank == i


# =============================================================================
# Edge Cases & Validation
# =============================================================================


def test_confidence_threshold_validation() -> None:
    """Confidence threshold is clamped to 0.0-10.0 range."""
    selector = ExpertSelector(settings=_mock_settings())
    scores = _create_scores(count=2, start_score=8.0)

    # Test negative threshold (clamped to 0.0)
    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=-5.0,
    )
    assert len(result.agents) == 1  # Best agent selected (>= 0.0)

    # Test excessive threshold (clamped to 10.0)
    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=15.0,
    )
    # Score is 8.0, threshold clamped to 10.0, so fallback should trigger
    # But with no fallback configured, should return empty
    selector_no_fallback = ExpertSelector(settings=_mock_settings(), fallback_agent_id=None)
    result_no_fallback = selector_no_fallback.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=15.0,
    )
    assert result_no_fallback.fallback_used is True


def test_selection_result_reasoning() -> None:
    """Verify reasoning field is populated for all strategies."""
    selector = ExpertSelector(settings=_mock_settings(enable_ensemble=True))
    scores = _create_scores(count=3, start_score=8.0)

    strategies = [
        SelectionStrategyEnum.TOP_1,
        SelectionStrategyEnum.TOP_K,
        SelectionStrategyEnum.ENSEMBLE,
        SelectionStrategyEnum.CASCADE,
    ]

    for strategy in strategies:
        result = selector.select(
            scores=scores,
            strategy=strategy,
            k=2,
            confidence_threshold=6.0,
        )
        assert result.reasoning
        assert len(result.reasoning) > 0
        # Verify each agent also has reasoning
        for agent in result.agents:
            assert agent.reasoning
            assert len(agent.reasoning) > 0


def test_expert_selection_result_model() -> None:
    """Test ExpertSelectionResult Pydantic model."""
    scores = _create_scores(count=2, start_score=8.0)
    selector = ExpertSelector(settings=_mock_settings())

    result = selector.select(
        scores=scores,
        strategy=SelectionStrategyEnum.TOP_1,
        confidence_threshold=6.0,
    )

    # Verify model fields
    assert isinstance(result, ExpertSelectionResult)
    assert isinstance(result.agents, list)
    assert isinstance(result.reasoning, str)
    assert isinstance(result.strategy, SelectionStrategyEnum)
    assert isinstance(result.fallback_used, bool)

    # Should be JSON serializable
    result_dict = result.model_dump()
    assert "agents" in result_dict
    assert "reasoning" in result_dict
    assert "strategy" in result_dict
    assert "fallback_used" in result_dict
