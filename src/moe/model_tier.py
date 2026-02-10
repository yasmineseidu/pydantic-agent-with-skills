"""Pydantic models for MoE tier selection and complexity scoring."""

from typing import ClassVar, Optional

from pydantic import BaseModel, Field, computed_field


class ModelTier(BaseModel):
    """A single model tier definition with cost metadata.

    Represents one tier in the MoE routing table (e.g. fast, balanced,
    powerful) along with its per-token cost so the router can make
    budget-aware decisions.

    Args:
        name: Human-readable tier label (e.g. "fast", "balanced", "powerful").
        model_name: Provider-qualified model identifier
            (e.g. "anthropic/claude-haiku-4.5").
        cost_per_1k_input: USD cost per 1 000 input tokens.
        cost_per_1k_output: USD cost per 1 000 output tokens.
    """

    name: str
    model_name: str
    cost_per_1k_input: float = Field(ge=0.0)
    cost_per_1k_output: float = Field(ge=0.0)


class ComplexityScore(BaseModel):
    """Five-dimension query complexity analysis for tier routing.

    Each dimension is scored 0-10. The weighted total determines which
    model tier should handle the query:

        haiku  (0-3)  |  sonnet (3-7)  |  opus (7-10)

    Weights are stored as class-level constants and sum to 1.0.

    Args:
        reasoning_depth: How much multi-step reasoning is required.
        domain_specificity: How specialised the domain knowledge is.
        creativity: How much creative or novel generation is needed.
        context_dependency: How much prior conversation context matters.
        output_length: Expected length / detail of the response.
    """

    WEIGHTS: ClassVar[dict[str, float]] = {
        "reasoning_depth": 0.30,
        "domain_specificity": 0.25,
        "creativity": 0.20,
        "context_dependency": 0.15,
        "output_length": 0.10,
    }

    reasoning_depth: float = Field(default=0.0, ge=0.0, le=10.0)
    domain_specificity: float = Field(default=0.0, ge=0.0, le=10.0)
    creativity: float = Field(default=0.0, ge=0.0, le=10.0)
    context_dependency: float = Field(default=0.0, ge=0.0, le=10.0)
    output_length: float = Field(default=0.0, ge=0.0, le=10.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def weighted_total(self) -> float:
        """Weighted sum of all five complexity dimensions.

        Returns:
            Float in [0.0, 10.0] representing overall query complexity.
        """
        return (
            self.reasoning_depth * self.WEIGHTS["reasoning_depth"]
            + self.domain_specificity * self.WEIGHTS["domain_specificity"]
            + self.creativity * self.WEIGHTS["creativity"]
            + self.context_dependency * self.WEIGHTS["context_dependency"]
            + self.output_length * self.WEIGHTS["output_length"]
        )


class BudgetCheck(BaseModel):
    """Result of a budget-availability check before routing.

    Returned by the budget guard to tell the router whether the
    requested tier is affordable and, if not, which cheaper tier
    to fall back to.

    Args:
        allowed: Whether the requested tier fits the remaining budget.
        remaining: Budget remaining in USD after this request (or current
            remaining if the request was denied).
        suggested_tier: Alternative tier name when the requested tier
            is over budget. None when allowed is True.
    """

    allowed: bool
    remaining: float = Field(ge=0.0)
    suggested_tier: Optional[str] = None
