"""Unit tests for MoE ModelTier, ComplexityScore, and BudgetCheck models."""

import pytest
from pydantic import ValidationError

from src.moe.model_tier import BudgetCheck, ComplexityScore, ModelTier


# ---------------------------------------------------------------------------
# ModelTier
# ---------------------------------------------------------------------------


class TestModelTier:
    """Tests for ModelTier model."""

    @pytest.mark.unit
    def test_model_tier_creation(self, fast_tier: ModelTier) -> None:
        """Test basic creation with all required fields."""
        assert fast_tier.name == "fast"
        assert fast_tier.model_name == "anthropic/claude-haiku-4.5"
        assert fast_tier.cost_per_1k_input == 0.00025
        assert fast_tier.cost_per_1k_output == 0.00125

    @pytest.mark.unit
    def test_model_tier_name_required(self) -> None:
        """Test that name is required."""
        with pytest.raises(ValidationError):
            ModelTier(
                model_name="test/model",
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.002,
            )  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_model_tier_model_name_required(self) -> None:
        """Test that model_name is required."""
        with pytest.raises(ValidationError):
            ModelTier(
                name="test",
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.002,
            )  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_model_tier_positive_costs(self) -> None:
        """Test that zero costs are accepted (ge=0.0)."""
        tier = ModelTier(
            name="free",
            model_name="local/model",
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )
        assert tier.cost_per_1k_input == 0.0
        assert tier.cost_per_1k_output == 0.0

    @pytest.mark.unit
    def test_model_tier_negative_input_cost(self) -> None:
        """Test that cost_per_1k_input < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ModelTier(
                name="bad",
                model_name="test/model",
                cost_per_1k_input=-0.001,
                cost_per_1k_output=0.001,
            )

    @pytest.mark.unit
    def test_model_tier_negative_output_cost(self) -> None:
        """Test that cost_per_1k_output < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ModelTier(
                name="bad",
                model_name="test/model",
                cost_per_1k_input=0.001,
                cost_per_1k_output=-0.001,
            )

    @pytest.mark.unit
    def test_model_tier_all_three_tiers(
        self,
        fast_tier: ModelTier,
        balanced_tier: ModelTier,
        powerful_tier: ModelTier,
    ) -> None:
        """Test that all three fixture tiers have distinct names and costs."""
        tiers = [fast_tier, balanced_tier, powerful_tier]
        names = {t.name for t in tiers}
        assert len(names) == 3
        # Costs should increase from fast to powerful
        assert fast_tier.cost_per_1k_input < balanced_tier.cost_per_1k_input
        assert balanced_tier.cost_per_1k_input < powerful_tier.cost_per_1k_input


# ---------------------------------------------------------------------------
# ComplexityScore
# ---------------------------------------------------------------------------


class TestComplexityScore:
    """Tests for ComplexityScore model."""

    @pytest.mark.unit
    def test_complexity_score_defaults(self) -> None:
        """Test that all dimensions default to 0.0."""
        cs = ComplexityScore()
        assert cs.reasoning_depth == 0.0
        assert cs.domain_specificity == 0.0
        assert cs.creativity == 0.0
        assert cs.context_dependency == 0.0
        assert cs.output_length == 0.0

    @pytest.mark.unit
    def test_complexity_score_weighted_total_all_zeros(
        self, zero_complexity: ComplexityScore
    ) -> None:
        """Test that all zeros yields weighted_total=0.0."""
        assert zero_complexity.weighted_total == 0.0

    @pytest.mark.unit
    def test_complexity_score_weighted_total_all_tens(
        self, max_complexity: ComplexityScore
    ) -> None:
        """Test that all tens yields weighted_total=10.0."""
        assert max_complexity.weighted_total == 10.0

    @pytest.mark.unit
    def test_complexity_score_weighted_total_known_input(self) -> None:
        """Test weighted_total with known input values.

        reasoning=7, domain=5, creativity=3, context=8, output=2
        -> 7*0.30 + 5*0.25 + 3*0.20 + 8*0.15 + 2*0.10
        -> 2.10 + 1.25 + 0.60 + 1.20 + 0.20 = 5.35
        """
        cs = ComplexityScore(
            reasoning_depth=7.0,
            domain_specificity=5.0,
            creativity=3.0,
            context_dependency=8.0,
            output_length=2.0,
        )
        assert cs.weighted_total == pytest.approx(5.35)

    @pytest.mark.unit
    def test_complexity_score_weighted_total_single_dimension(self) -> None:
        """Test weighted_total with only one non-zero dimension."""
        cs = ComplexityScore(reasoning_depth=10.0)
        # 10.0 * 0.30 = 3.0
        assert cs.weighted_total == pytest.approx(3.0)

    @pytest.mark.unit
    def test_complexity_score_weights_sum_to_one(self) -> None:
        """Test that WEIGHTS class variable sums to 1.0."""
        total = sum(ComplexityScore.WEIGHTS.values())
        assert total == pytest.approx(1.0)

    @pytest.mark.unit
    def test_complexity_score_weights_has_five_keys(self) -> None:
        """Test that WEIGHTS has exactly 5 dimension keys."""
        assert len(ComplexityScore.WEIGHTS) == 5
        expected_keys = {
            "reasoning_depth",
            "domain_specificity",
            "creativity",
            "context_dependency",
            "output_length",
        }
        assert set(ComplexityScore.WEIGHTS.keys()) == expected_keys

    @pytest.mark.unit
    def test_complexity_score_dimension_boundaries(self) -> None:
        """Test that boundary values 0.0 and 10.0 are accepted."""
        cs = ComplexityScore(
            reasoning_depth=0.0,
            domain_specificity=10.0,
            creativity=0.0,
            context_dependency=10.0,
            output_length=0.0,
        )
        assert cs.reasoning_depth == 0.0
        assert cs.domain_specificity == 10.0

    @pytest.mark.unit
    def test_complexity_score_dimension_too_low(self) -> None:
        """Test that a dimension < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ComplexityScore(reasoning_depth=-0.1)

    @pytest.mark.unit
    def test_complexity_score_dimension_too_high(self) -> None:
        """Test that a dimension > 10.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ComplexityScore(creativity=10.1)

    @pytest.mark.unit
    def test_complexity_score_each_dimension_too_high(self) -> None:
        """Test that each dimension validates its upper bound independently."""
        for field_name in ComplexityScore.WEIGHTS:
            with pytest.raises(ValidationError):
                ComplexityScore(**{field_name: 10.1})

    @pytest.mark.unit
    def test_complexity_score_each_dimension_too_low(self) -> None:
        """Test that each dimension validates its lower bound independently."""
        for field_name in ComplexityScore.WEIGHTS:
            with pytest.raises(ValidationError):
                ComplexityScore(**{field_name: -0.1})

    @pytest.mark.unit
    def test_complexity_score_weighted_total_is_computed_field(self) -> None:
        """Test that weighted_total appears in model_dump output."""
        cs = ComplexityScore(reasoning_depth=5.0)
        dumped = cs.model_dump()
        assert "weighted_total" in dumped
        assert dumped["weighted_total"] == pytest.approx(1.5)

    @pytest.mark.unit
    def test_complexity_score_haiku_range(self) -> None:
        """Test a score in haiku range (0-3)."""
        cs = ComplexityScore(
            reasoning_depth=2.0,
            domain_specificity=1.0,
            creativity=1.0,
            context_dependency=1.0,
            output_length=1.0,
        )
        # 2*0.30 + 1*0.25 + 1*0.20 + 1*0.15 + 1*0.10 = 0.60+0.25+0.20+0.15+0.10 = 1.30
        assert cs.weighted_total == pytest.approx(1.30)
        assert cs.weighted_total < 3.0

    @pytest.mark.unit
    def test_complexity_score_sonnet_range(self) -> None:
        """Test a score in sonnet range (3-7)."""
        cs = ComplexityScore(
            reasoning_depth=5.0,
            domain_specificity=5.0,
            creativity=5.0,
            context_dependency=5.0,
            output_length=5.0,
        )
        # All 5s: 5 * (0.30+0.25+0.20+0.15+0.10) = 5 * 1.0 = 5.0
        assert cs.weighted_total == pytest.approx(5.0)
        assert 3.0 <= cs.weighted_total <= 7.0

    @pytest.mark.unit
    def test_complexity_score_opus_range(self) -> None:
        """Test a score in opus range (7-10)."""
        cs = ComplexityScore(
            reasoning_depth=9.0,
            domain_specificity=8.0,
            creativity=7.0,
            context_dependency=9.0,
            output_length=8.0,
        )
        # 9*0.30 + 8*0.25 + 7*0.20 + 9*0.15 + 8*0.10
        # = 2.70 + 2.00 + 1.40 + 1.35 + 0.80 = 8.25
        assert cs.weighted_total == pytest.approx(8.25)
        assert cs.weighted_total >= 7.0


# ---------------------------------------------------------------------------
# BudgetCheck
# ---------------------------------------------------------------------------


class TestBudgetCheck:
    """Tests for BudgetCheck model."""

    @pytest.mark.unit
    def test_budget_check_allowed(self) -> None:
        """Test creation when request is allowed."""
        bc = BudgetCheck(allowed=True, remaining=4.50)
        assert bc.allowed is True
        assert bc.remaining == 4.50
        assert bc.suggested_tier is None

    @pytest.mark.unit
    def test_budget_check_denied_with_suggestion(self) -> None:
        """Test creation when request is denied with suggested_tier."""
        bc = BudgetCheck(allowed=False, remaining=0.50, suggested_tier="fast")
        assert bc.allowed is False
        assert bc.remaining == 0.50
        assert bc.suggested_tier == "fast"

    @pytest.mark.unit
    def test_budget_check_remaining_ge_zero(self) -> None:
        """Test that remaining=0.0 is valid."""
        bc = BudgetCheck(allowed=False, remaining=0.0, suggested_tier="fast")
        assert bc.remaining == 0.0

    @pytest.mark.unit
    def test_budget_check_remaining_negative(self) -> None:
        """Test that remaining < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            BudgetCheck(allowed=False, remaining=-0.01)

    @pytest.mark.unit
    def test_budget_check_suggested_tier_optional(self) -> None:
        """Test that suggested_tier defaults to None."""
        bc = BudgetCheck(allowed=True, remaining=10.0)
        assert bc.suggested_tier is None

    @pytest.mark.unit
    def test_budget_check_missing_required_fields(self) -> None:
        """Test that allowed and remaining are required."""
        with pytest.raises(ValidationError):
            BudgetCheck(remaining=5.0)  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            BudgetCheck(allowed=True)  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_budget_check_allowed_with_suggested_tier(self) -> None:
        """Test that allowed=True can still have a suggested_tier (no constraint)."""
        bc = BudgetCheck(allowed=True, remaining=5.0, suggested_tier="balanced")
        assert bc.allowed is True
        assert bc.suggested_tier == "balanced"
