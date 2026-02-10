"""Unit tests for ModelRouter tier selection and overrides."""

import pytest

from src.moe.model_router import ModelRouter
from src.moe.model_tier import ComplexityScore, ModelTier


def _uniform_score(value: float) -> ComplexityScore:
    """Create a ComplexityScore with all dimensions set to the same value.

    When all dimensions equal N, weighted_total = N * 1.0 = N (since weights sum to 1.0).

    Args:
        value: The value to assign to every dimension (0.0-10.0).

    Returns:
        ComplexityScore where weighted_total equals the given value.
    """
    return ComplexityScore(
        reasoning_depth=value,
        domain_specificity=value,
        creativity=value,
        context_dependency=value,
        output_length=value,
    )


class TestTierSelection:
    """Tests for basic complexity-to-tier routing."""

    @pytest.mark.unit
    def test_score_2_routes_to_fast(self) -> None:
        """Score 2.0 -> fast tier."""
        router = ModelRouter()
        score = _uniform_score(2.0)
        result = router.route(score)

        assert result.name == "fast"

    @pytest.mark.unit
    def test_score_5_routes_to_balanced(self) -> None:
        """Score 5.0 -> balanced tier."""
        router = ModelRouter()
        score = _uniform_score(5.0)
        result = router.route(score)

        assert result.name == "balanced"

    @pytest.mark.unit
    def test_score_8_routes_to_powerful(self) -> None:
        """Score 8.0 -> powerful tier."""
        router = ModelRouter()
        score = _uniform_score(8.0)
        result = router.route(score)

        assert result.name == "powerful"


class TestBoundaryConditions:
    """Tests for exact boundary values between tiers."""

    @pytest.mark.unit
    def test_score_3_routes_to_fast(self) -> None:
        """Boundary: score 3.0 -> fast (total <= 3.0)."""
        router = ModelRouter()
        score = _uniform_score(3.0)

        assert score.weighted_total == pytest.approx(3.0)
        result = router.route(score)
        assert result.name == "fast"

    @pytest.mark.unit
    def test_score_just_above_3_routes_to_balanced(self) -> None:
        """Boundary: score 3.001 -> balanced (total > 3.0)."""
        router = ModelRouter()
        score = _uniform_score(3.001)

        assert score.weighted_total == pytest.approx(3.001)
        result = router.route(score)
        assert result.name == "balanced"

    @pytest.mark.unit
    def test_score_6_routes_to_balanced(self) -> None:
        """Boundary: score 6.0 -> balanced (total <= 6.0)."""
        router = ModelRouter()
        score = _uniform_score(6.0)

        assert score.weighted_total == pytest.approx(6.0)
        result = router.route(score)
        assert result.name == "balanced"

    @pytest.mark.unit
    def test_score_just_above_6_routes_to_powerful(self) -> None:
        """Boundary: score 6.001 -> powerful (total > 6.0)."""
        router = ModelRouter()
        score = _uniform_score(6.001)

        assert score.weighted_total == pytest.approx(6.001)
        result = router.route(score)
        assert result.name == "powerful"

    @pytest.mark.unit
    def test_zero_score_routes_to_fast(self, zero_complexity: ComplexityScore) -> None:
        """Score 0.0 -> fast tier."""
        router = ModelRouter()
        result = router.route(zero_complexity)
        assert result.name == "fast"

    @pytest.mark.unit
    def test_max_score_routes_to_powerful(self, max_complexity: ComplexityScore) -> None:
        """Score 10.0 -> powerful tier."""
        router = ModelRouter()
        result = router.route(max_complexity)
        assert result.name == "powerful"


class TestForceTier:
    """Tests for force_tier override."""

    @pytest.mark.unit
    def test_force_tier_overrides_high_score(self) -> None:
        """force_tier='fast' with score 9.0 -> fast regardless of score."""
        router = ModelRouter()
        score = _uniform_score(9.0)
        result = router.route(score, force_tier="fast")

        assert result.name == "fast"

    @pytest.mark.unit
    def test_force_tier_overrides_low_score(self) -> None:
        """force_tier='powerful' with score 1.0 -> powerful regardless of score."""
        router = ModelRouter()
        score = _uniform_score(1.0)
        result = router.route(score, force_tier="powerful")

        assert result.name == "powerful"

    @pytest.mark.unit
    def test_force_tier_invalid_name_raises_value_error(self) -> None:
        """force_tier with invalid name -> raises ValueError."""
        router = ModelRouter()
        score = _uniform_score(5.0)

        with pytest.raises(ValueError, match="force_tier 'nonexistent' not found"):
            router.route(score, force_tier="nonexistent")


class TestMaxTier:
    """Tests for max_tier cap."""

    @pytest.mark.unit
    def test_max_tier_caps_powerful_to_balanced(self) -> None:
        """max_tier='balanced' caps score 9.0 -> balanced instead of powerful."""
        router = ModelRouter()
        score = _uniform_score(9.0)
        result = router.route(score, max_tier="balanced")

        assert result.name == "balanced"

    @pytest.mark.unit
    def test_max_tier_does_not_affect_lower(self) -> None:
        """max_tier='balanced' with score 2.0 -> fast (no upward change)."""
        router = ModelRouter()
        score = _uniform_score(2.0)
        result = router.route(score, max_tier="balanced")

        assert result.name == "fast"

    @pytest.mark.unit
    def test_max_tier_invalid_name_raises_value_error(self) -> None:
        """max_tier with invalid name -> raises ValueError."""
        router = ModelRouter()
        score = _uniform_score(5.0)

        with pytest.raises(ValueError, match="max_tier 'nonexistent' not found"):
            router.route(score, max_tier="nonexistent")


class TestBudgetConstraints:
    """Tests for budget_remaining downgrade logic."""

    @pytest.mark.unit
    def test_budget_nearly_exhausted_downgrades_to_fast(self) -> None:
        """budget_remaining=0.001 downgrades to fast regardless of score."""
        router = ModelRouter()
        score = _uniform_score(9.0)
        result = router.route(score, budget_remaining=0.001)

        assert result.name == "fast"

    @pytest.mark.unit
    def test_budget_zero_downgrades_to_fast(self) -> None:
        """budget_remaining=0.0 downgrades to fast."""
        router = ModelRouter()
        score = _uniform_score(8.0)
        result = router.route(score, budget_remaining=0.0)

        assert result.name == "fast"

    @pytest.mark.unit
    def test_budget_none_no_constraint(self) -> None:
        """budget_remaining=None -> no budget constraint (normal routing)."""
        router = ModelRouter()
        score = _uniform_score(8.0)
        result = router.route(score, budget_remaining=None)

        assert result.name == "powerful"

    @pytest.mark.unit
    def test_budget_sufficient_no_downgrade(self) -> None:
        """budget_remaining=10.0 -> no downgrade, routes normally."""
        router = ModelRouter()
        score = _uniform_score(8.0)
        result = router.route(score, budget_remaining=10.0)

        assert result.name == "powerful"

    @pytest.mark.unit
    def test_budget_at_threshold_no_downgrade(self) -> None:
        """budget_remaining=0.01 -> at threshold, no downgrade (< 0.01 triggers)."""
        router = ModelRouter()
        score = _uniform_score(8.0)
        result = router.route(score, budget_remaining=0.01)

        assert result.name == "powerful"


class TestCustomTiers:
    """Tests for custom_tiers override."""

    @pytest.mark.unit
    def test_custom_tiers_override_defaults(self) -> None:
        """custom_tiers replace the default tiers for routing."""
        custom = [
            ModelTier(
                name="fast",
                model_name="custom/fast-model",
                cost_per_1k_input=0.0001,
                cost_per_1k_output=0.0005,
            ),
            ModelTier(
                name="balanced",
                model_name="custom/balanced-model",
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.005,
            ),
            ModelTier(
                name="powerful",
                model_name="custom/powerful-model",
                cost_per_1k_input=0.01,
                cost_per_1k_output=0.05,
            ),
        ]

        router = ModelRouter()
        score = _uniform_score(5.0)
        result = router.route(score, custom_tiers=custom)

        assert result.name == "balanced"
        assert result.model_name == "custom/balanced-model"

    @pytest.mark.unit
    def test_custom_tiers_fast_selection(self) -> None:
        """custom_tiers are used for fast tier selection."""
        custom = [
            ModelTier(
                name="fast",
                model_name="custom/speedy",
                cost_per_1k_input=0.0001,
                cost_per_1k_output=0.0005,
            ),
            ModelTier(
                name="balanced",
                model_name="custom/mid",
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.005,
            ),
        ]

        router = ModelRouter()
        score = _uniform_score(2.0)
        result = router.route(score, custom_tiers=custom)

        assert result.name == "fast"
        assert result.model_name == "custom/speedy"
