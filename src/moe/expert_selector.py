"""Expert selector for choosing agents based on scoring strategies."""

import logging
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.moe.models import ExpertScore, SelectionResult
from src.settings import Settings

logger = logging.getLogger(__name__)


class SelectionStrategyEnum(str, Enum):
    """Strategy for selecting experts from scored candidates.

    TOP_1: Select single best agent above confidence threshold.
    TOP_K: Select top K agents for parallel execution (ensemble mode).
    ENSEMBLE: Select top K agents for weighted aggregation.
    CASCADE: Try agents in descending score order until success.
    """

    TOP_1 = "top_1"
    TOP_K = "top_k"
    ENSEMBLE = "ensemble"
    CASCADE = "cascade"


class ExpertSelectionResult(BaseModel):
    """Result of expert selection with chosen agents.

    Args:
        agents: List of selected experts ranked by score.
        reasoning: Explanation of selection strategy and choices.
        strategy: The selection strategy used.
        fallback_used: Whether fallback to general agent was used.
    """

    agents: list[SelectionResult] = Field(default_factory=list)
    reasoning: str
    strategy: SelectionStrategyEnum
    fallback_used: bool = False


class ExpertSelector:
    """Expert selector using multiple selection strategies.

    Implements four selection strategies for routing tasks to agents:
    - TOP_1: Single best agent with confidence threshold and fallback
    - TOP_K: Top K agents for parallel execution (feature-flagged)
    - ENSEMBLE: Top K agents for weighted aggregation (feature-flagged)
    - CASCADE: Sequential fallback through ranked agents

    Args:
        settings: Application settings for feature flag checks.
        fallback_agent_id: UUID of general-purpose fallback agent.
        fallback_agent_name: Name of fallback agent for logging.
    """

    def __init__(
        self,
        settings: Settings,
        fallback_agent_id: Optional[UUID] = None,
        fallback_agent_name: str = "general-agent",
    ) -> None:
        """Initialize the expert selector.

        Args:
            settings: Application settings for feature flag checks.
            fallback_agent_id: Optional UUID of fallback agent for low-confidence cases.
            fallback_agent_name: Name of fallback agent for logging and results.
        """
        self._settings: Settings = settings
        self._fallback_agent_id: Optional[UUID] = fallback_agent_id
        self._fallback_agent_name: str = fallback_agent_name

    def select(
        self,
        scores: list[tuple[UUID, str, ExpertScore]],
        strategy: SelectionStrategyEnum = SelectionStrategyEnum.TOP_1,
        k: int = 3,
        confidence_threshold: float = 0.6,
    ) -> ExpertSelectionResult:
        """Select agents based on scores and strategy.

        Args:
            scores: List of (agent_id, agent_name, score) tuples sorted descending.
            strategy: Selection strategy to use.
            k: Number of agents to select for TOP_K/ENSEMBLE strategies.
            confidence_threshold: Minimum overall score (0.0-10.0) for selection.

        Returns:
            ExpertSelectionResult with selected agents and reasoning.
        """
        if not scores:
            logger.warning("expert_selector_no_scores: using_fallback=true")
            return self._fallback_result(
                strategy=strategy,
                reason="No agents available to score",
            )

        # Validate confidence threshold
        if not (0.0 <= confidence_threshold <= 10.0):
            logger.warning(
                f"expert_selector_invalid_threshold: threshold={confidence_threshold}, "
                f"clamping_to_range=true"
            )
            confidence_threshold = max(0.0, min(10.0, confidence_threshold))

        logger.info(
            f"expert_selector: strategy={strategy.value}, "
            f"candidates={len(scores)}, "
            f"threshold={confidence_threshold:.2f}"
        )

        # Route to strategy-specific method
        if strategy == SelectionStrategyEnum.TOP_1:
            return self._select_top_1(scores, confidence_threshold)
        elif strategy == SelectionStrategyEnum.TOP_K:
            return self._select_top_k(scores, k, confidence_threshold)
        elif strategy == SelectionStrategyEnum.ENSEMBLE:
            return self._select_ensemble(scores, k, confidence_threshold)
        elif strategy == SelectionStrategyEnum.CASCADE:
            return self._select_cascade(scores, confidence_threshold)
        else:
            logger.error(f"expert_selector_unknown_strategy: strategy={strategy}")
            return self._fallback_result(
                strategy=strategy,
                reason=f"Unknown strategy: {strategy}",
            )

    def _select_top_1(
        self,
        scores: list[tuple[UUID, str, ExpertScore]],
        threshold: float,
    ) -> ExpertSelectionResult:
        """Select single best agent above confidence threshold.

        Falls back to general agent if best score is below threshold.

        Args:
            scores: List of (agent_id, agent_name, score) tuples sorted descending.
            threshold: Minimum overall score required for selection.

        Returns:
            ExpertSelectionResult with single agent or fallback.
        """
        agent_id, agent_name, score = scores[0]

        if score.overall < threshold:
            logger.warning(
                f"expert_selector_below_threshold: "
                f"agent_name={agent_name}, "
                f"score={score.overall:.2f}, "
                f"threshold={threshold:.2f}, "
                f"using_fallback=true"
            )
            return self._fallback_result(
                strategy=SelectionStrategyEnum.TOP_1,
                reason=f"Best agent {agent_name} scored {score.overall:.2f} below threshold {threshold:.2f}",
            )

        result = SelectionResult(
            expert_id=agent_id,
            expert_name=agent_name,
            score=score,
            reasoning=f"Selected {agent_name} with score {score.overall:.2f}/10 (threshold: {threshold:.2f})",
            rank=1,
        )

        logger.info(f"expert_selector_top_1: agent_name={agent_name}, score={score.overall:.2f}")

        return ExpertSelectionResult(
            agents=[result],
            reasoning=f"TOP_1 strategy selected {agent_name} as best match above threshold",
            strategy=SelectionStrategyEnum.TOP_1,
            fallback_used=False,
        )

    def _select_top_k(
        self,
        scores: list[tuple[UUID, str, ExpertScore]],
        k: int,
        threshold: float,
    ) -> ExpertSelectionResult:
        """Select top K agents for parallel execution.

        Requires enable_expert_gate and enable_ensemble_mode feature flags.

        Args:
            scores: List of (agent_id, agent_name, score) tuples sorted descending.
            k: Number of agents to select.
            threshold: Minimum overall score required for selection.

        Returns:
            ExpertSelectionResult with top K agents above threshold.
        """
        if not self._settings.feature_flags.enable_ensemble_mode:
            logger.warning(
                "expert_selector_ensemble_disabled: "
                "feature_flag=enable_ensemble_mode, "
                "falling_back_to_top_1=true"
            )
            return self._select_top_1(scores, threshold)

        # Filter scores above threshold
        qualified = [
            (agent_id, agent_name, score)
            for agent_id, agent_name, score in scores
            if score.overall >= threshold
        ]

        if not qualified:
            logger.warning(
                f"expert_selector_no_qualified: threshold={threshold:.2f}, using_fallback=true"
            )
            return self._fallback_result(
                strategy=SelectionStrategyEnum.TOP_K,
                reason=f"No agents met confidence threshold {threshold:.2f}",
            )

        # Select top K from qualified agents
        selected = qualified[:k]
        results: list[SelectionResult] = []

        for rank, (agent_id, agent_name, score) in enumerate(selected, start=1):
            results.append(
                SelectionResult(
                    expert_id=agent_id,
                    expert_name=agent_name,
                    score=score,
                    reasoning=f"Rank #{rank} with score {score.overall:.2f}/10",
                    rank=rank,
                )
            )

        agent_names = ", ".join(r.expert_name for r in results)
        logger.info(f"expert_selector_top_k: k={k}, selected={len(results)}, agents={agent_names}")

        return ExpertSelectionResult(
            agents=results,
            reasoning=f"TOP_K strategy selected {len(results)} agents for parallel execution",
            strategy=SelectionStrategyEnum.TOP_K,
            fallback_used=False,
        )

    def _select_ensemble(
        self,
        scores: list[tuple[UUID, str, ExpertScore]],
        k: int,
        threshold: float,
    ) -> ExpertSelectionResult:
        """Select top K agents for weighted aggregation.

        Similar to TOP_K but signals intent for response aggregation.
        Requires enable_expert_gate and enable_ensemble_mode feature flags.

        Args:
            scores: List of (agent_id, agent_name, score) tuples sorted descending.
            k: Number of agents to select for ensemble.
            threshold: Minimum overall score required for selection.

        Returns:
            ExpertSelectionResult with top K agents for aggregation.
        """
        if not self._settings.feature_flags.enable_ensemble_mode:
            logger.warning(
                "expert_selector_ensemble_disabled: "
                "feature_flag=enable_ensemble_mode, "
                "falling_back_to_top_1=true"
            )
            return self._select_top_1(scores, threshold)

        # Filter scores above threshold
        qualified = [
            (agent_id, agent_name, score)
            for agent_id, agent_name, score in scores
            if score.overall >= threshold
        ]

        if not qualified:
            logger.warning(
                f"expert_selector_no_qualified: threshold={threshold:.2f}, using_fallback=true"
            )
            return self._fallback_result(
                strategy=SelectionStrategyEnum.ENSEMBLE,
                reason=f"No agents met confidence threshold {threshold:.2f}",
            )

        # Select top K from qualified agents
        selected = qualified[:k]
        results: list[SelectionResult] = []

        for rank, (agent_id, agent_name, score) in enumerate(selected, start=1):
            results.append(
                SelectionResult(
                    expert_id=agent_id,
                    expert_name=agent_name,
                    score=score,
                    reasoning=f"Ensemble member #{rank} with score {score.overall:.2f}/10",
                    rank=rank,
                )
            )

        agent_names = ", ".join(r.expert_name for r in results)
        logger.info(
            f"expert_selector_ensemble: k={k}, selected={len(results)}, agents={agent_names}"
        )

        return ExpertSelectionResult(
            agents=results,
            reasoning=f"ENSEMBLE strategy selected {len(results)} agents for weighted aggregation",
            strategy=SelectionStrategyEnum.ENSEMBLE,
            fallback_used=False,
        )

    def _select_cascade(
        self,
        scores: list[tuple[UUID, str, ExpertScore]],
        threshold: float,
    ) -> ExpertSelectionResult:
        """Select agents for cascade routing (sequential fallback).

        Returns all agents above threshold ranked by score for sequential attempts.
        Caller will try each agent in order until one succeeds.

        Args:
            scores: List of (agent_id, agent_name, score) tuples sorted descending.
            threshold: Minimum overall score required for selection.

        Returns:
            ExpertSelectionResult with all qualified agents for cascade.
        """
        # Filter scores above threshold
        qualified = [
            (agent_id, agent_name, score)
            for agent_id, agent_name, score in scores
            if score.overall >= threshold
        ]

        if not qualified:
            logger.warning(
                f"expert_selector_no_qualified: threshold={threshold:.2f}, using_fallback=true"
            )
            return self._fallback_result(
                strategy=SelectionStrategyEnum.CASCADE,
                reason=f"No agents met confidence threshold {threshold:.2f}",
            )

        results: list[SelectionResult] = []

        for rank, (agent_id, agent_name, score) in enumerate(qualified, start=1):
            results.append(
                SelectionResult(
                    expert_id=agent_id,
                    expert_name=agent_name,
                    score=score,
                    reasoning=f"Cascade priority #{rank} with score {score.overall:.2f}/10",
                    rank=rank,
                )
            )

        agent_names = ", ".join(r.expert_name for r in results)
        logger.info(f"expert_selector_cascade: qualified={len(results)}, agents={agent_names}")

        return ExpertSelectionResult(
            agents=results,
            reasoning=f"CASCADE strategy ranked {len(results)} agents for sequential fallback",
            strategy=SelectionStrategyEnum.CASCADE,
            fallback_used=False,
        )

    def _fallback_result(
        self,
        strategy: SelectionStrategyEnum,
        reason: str,
    ) -> ExpertSelectionResult:
        """Create a fallback result when no agents qualify.

        Args:
            strategy: The strategy that triggered fallback.
            reason: Explanation of why fallback was used.

        Returns:
            ExpertSelectionResult with fallback agent or empty list.
        """
        if not self._fallback_agent_id:
            logger.warning(
                f"expert_selector_no_fallback: strategy={strategy.value}, reason={reason}"
            )
            return ExpertSelectionResult(
                agents=[],
                reasoning=f"No agents selected: {reason}. No fallback configured.",
                strategy=strategy,
                fallback_used=True,
            )

        # Create fallback agent result with neutral score
        fallback_score = ExpertScore(
            skill_match=5.0,
            past_performance=5.0,
            personality_fit=5.0,
            load_balance=10.0,
        )

        fallback = SelectionResult(
            expert_id=self._fallback_agent_id,
            expert_name=self._fallback_agent_name,
            score=fallback_score,
            reasoning=f"Fallback agent: {reason}",
            rank=1,
        )

        logger.info(
            f"expert_selector_fallback: "
            f"strategy={strategy.value}, "
            f"fallback_agent={self._fallback_agent_name}"
        )

        return ExpertSelectionResult(
            agents=[fallback],
            reasoning=f"Using fallback agent {self._fallback_agent_name}: {reason}",
            strategy=strategy,
            fallback_used=True,
        )
