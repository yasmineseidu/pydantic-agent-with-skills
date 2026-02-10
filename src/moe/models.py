"""Pydantic models for Mixture-of-Experts selection and aggregation."""

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


class SelectionStrategy(BaseModel):
    """Strategy for selecting experts from a pool.

    Controls whether to use the top N experts, threshold-based selection,
    or weighted sampling.

    Args:
        method: Selection method (top_n, threshold, weighted).
        value: Value for the method (N for top_n, threshold for threshold).
        max_experts: Maximum number of experts to select.
    """

    method: str = Field(default="top_n", pattern="^(top_n|threshold|weighted)$")
    value: float = Field(default=1.0, ge=0.0)
    max_experts: int = Field(default=3, ge=1, le=10)


class ExpertScore(BaseModel):
    """Four-signal scoring for expert selection with weighted aggregation.

    Evaluates an expert's suitability for a task using four signals:
    - skill_match: How well the expert's capabilities match the task
    - past_performance: Historical success rate on similar tasks
    - personality_fit: How well the expert's personality suits the task
    - load_balance: Current workload and availability

    The weighted total is computed using class-level WEIGHTS that sum to 1.0.

    Args:
        skill_match: Skill match score (0.0-10.0).
        past_performance: Performance history score (0.0-10.0).
        personality_fit: Personality compatibility score (0.0-10.0).
        load_balance: Load and availability score (0.0-10.0).
    """

    WEIGHTS: ClassVar[dict[str, float]] = {
        "skill_match": 0.40,
        "past_performance": 0.25,
        "personality_fit": 0.20,
        "load_balance": 0.15,
    }

    skill_match: float = Field(default=0.0, ge=0.0, le=10.0)
    past_performance: float = Field(default=0.0, ge=0.0, le=10.0)
    personality_fit: float = Field(default=0.0, ge=0.0, le=10.0)
    load_balance: float = Field(default=0.0, ge=0.0, le=10.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall(self) -> float:
        """Weighted sum of all four signals.

        Returns:
            Float in [0.0, 10.0] representing overall expert suitability.
        """
        return (
            self.skill_match * self.WEIGHTS["skill_match"]
            + self.past_performance * self.WEIGHTS["past_performance"]
            + self.personality_fit * self.WEIGHTS["personality_fit"]
            + self.load_balance * self.WEIGHTS["load_balance"]
        )


class SelectionResult(BaseModel):
    """Result of expert selection with scoring details.

    Args:
        expert_id: UUID of the selected expert agent.
        expert_name: Human-readable name of the expert.
        score: Four-signal expert score.
        reasoning: Explanation of why this expert was selected.
        rank: Rank in the selection (1=best, 2=second, etc).
    """

    expert_id: UUID
    expert_name: str
    score: ExpertScore
    reasoning: str
    rank: int = Field(ge=1)


class ExpertResponse(BaseModel):
    """Response from a single expert in an ensemble.

    Args:
        expert_id: UUID of the expert that generated this response.
        expert_name: Human-readable name of the expert.
        response: The expert's response or output.
        confidence: Expert's confidence in this response (0.0-1.0).
        metadata: Additional response metadata.
    """

    expert_id: UUID
    expert_name: str
    response: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)


class AggregatedResponse(BaseModel):
    """Aggregated result from multiple expert responses.

    Args:
        final_response: The aggregated or synthesized response.
        expert_responses: Individual responses from each expert.
        aggregation_method: Method used to aggregate (consensus, voting, synthesis).
        confidence: Overall confidence in the aggregated result (0.0-1.0).
    """

    final_response: str
    expert_responses: list[ExpertResponse]
    aggregation_method: str = Field(default="synthesis")
    confidence: float = Field(ge=0.0, le=1.0)
