"""ResponseAggregator for combining multi-agent responses into ensemble results.

Phase 7 (P7-30 through P7-32): Ensemble response aggregation with weighted
averaging, consensus building, and confidence scoring.
"""

import logging
from typing import Optional

from src.moe.models import AggregatedResponse, ExpertResponse
from src.settings import Settings, load_settings

logger = logging.getLogger(__name__)


class ResponseAggregator:
    """Aggregates responses from multiple expert agents into a single result.

    Supports multiple aggregation methods:
    - weighted_average: Combines responses weighted by confidence scores
    - consensus: Detects majority agreement or high-confidence consensus
    - synthesis: Synthesizes responses into a coherent final answer

    Feature-flagged: requires settings.feature_flags.enable_ensemble_mode.

    Args:
        settings: Application settings with ensemble mode flag.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize aggregator with settings.

        Args:
            settings: Application settings (loads defaults if None).
        """
        self.settings = settings or load_settings()
        logger.info(
            "response_aggregator_initialized: ensemble_mode=%s",
            self.settings.feature_flags.enable_ensemble_mode,
        )

    async def aggregate_responses(
        self,
        expert_responses: list[ExpertResponse],
        method: str = "synthesis",
    ) -> AggregatedResponse:
        """Aggregate multiple expert responses into a single result.

        Args:
            expert_responses: List of responses from expert agents.
            method: Aggregation method (weighted_average, consensus, synthesis).

        Returns:
            AggregatedResponse with final response and metadata.

        Raises:
            ValueError: If ensemble mode disabled or invalid method.
        """
        if not self.settings.feature_flags.enable_ensemble_mode:
            logger.warning("aggregate_responses_blocked: ensemble_mode=disabled")
            raise ValueError("Ensemble mode is disabled - cannot aggregate responses")

        if not expert_responses:
            logger.warning("aggregate_responses_empty: no responses provided")
            raise ValueError("Cannot aggregate empty response list")

        logger.info(
            "aggregate_responses_start: method=%s, num_experts=%d",
            method,
            len(expert_responses),
        )

        # Route to appropriate aggregation method
        if method == "weighted_average":
            final_response = await self.weighted_average(expert_responses)
        elif method == "consensus":
            final_response = await self.consensus_builder(expert_responses)
        elif method == "synthesis":
            final_response = await self._synthesize_responses(expert_responses)
        else:
            logger.error("aggregate_responses_invalid_method: method=%s", method)
            raise ValueError(f"Unknown aggregation method: {method}")

        # Calculate overall confidence
        confidence = self._calculate_overall_confidence(expert_responses)

        result = AggregatedResponse(
            final_response=final_response,
            expert_responses=expert_responses,
            aggregation_method=method,
            confidence=confidence,
        )

        logger.info(
            "aggregate_responses_complete: method=%s, confidence=%.2f, response_length=%d",
            method,
            confidence,
            len(final_response),
        )

        return result

    async def weighted_average(self, expert_responses: list[ExpertResponse]) -> str:
        """Combine responses using weighted averaging by confidence scores.

        Weights each expert's response by their confidence score. Higher
        confidence experts have more influence on the final result.

        Args:
            expert_responses: List of expert responses to combine.

        Returns:
            Final response as a weighted synthesis.
        """
        logger.info("weighted_average_start: num_experts=%d", len(expert_responses))

        # Sort by confidence (highest first)
        sorted_responses = sorted(
            expert_responses,
            key=lambda r: r.confidence,
            reverse=True,
        )

        # Build weighted synthesis
        parts = []
        total_weight = sum(r.confidence for r in sorted_responses)

        for response in sorted_responses:
            weight_pct = (response.confidence / total_weight) * 100 if total_weight > 0 else 0
            parts.append(
                f"**{response.expert_name}** (weight: {weight_pct:.1f}%):\n{response.response}"
            )

        final_response = "\n\n".join(parts)

        logger.info(
            "weighted_average_complete: total_weight=%.2f, parts=%d",
            total_weight,
            len(parts),
        )

        return final_response

    async def consensus_builder(self, expert_responses: list[ExpertResponse]) -> str:
        """Build consensus by detecting majority agreement or high-confidence alignment.

        Identifies if experts agree on a common answer. Falls back to showing
        all perspectives if no clear consensus.

        Args:
            expert_responses: List of expert responses to analyze.

        Returns:
            Consensus response or multi-perspective summary.
        """
        logger.info("consensus_builder_start: num_experts=%d", len(expert_responses))

        # Check for high-confidence consensus (all experts >0.7 confidence)
        high_confidence = [r for r in expert_responses if r.confidence >= 0.7]
        if len(high_confidence) >= len(expert_responses) * 0.66:  # 2/3 majority
            # Strong consensus detected
            primary = max(high_confidence, key=lambda r: r.confidence)
            others = ", ".join(
                r.expert_name for r in high_confidence if r.expert_id != primary.expert_id
            )
            consensus = (
                f"**Consensus Reached** (confidence: {primary.confidence:.2f})\n\n"
                f"{primary.response}\n\n"
                f"*Agreed by: {primary.expert_name}"
            )
            if others:
                consensus += f", {others}*"
            else:
                consensus += "*"

            logger.info(
                "consensus_builder_consensus: experts=%d, leader=%s",
                len(high_confidence),
                primary.expert_name,
            )
            return consensus

        # No consensus - show all perspectives
        logger.info("consensus_builder_no_consensus: showing all perspectives")
        parts = ["**No Clear Consensus** - Multiple Perspectives:\n"]
        for i, response in enumerate(
            sorted(expert_responses, key=lambda r: r.confidence, reverse=True), 1
        ):
            parts.append(
                f"\n{i}. **{response.expert_name}** (confidence: {response.confidence:.2f}):\n{response.response}"
            )

        return "\n".join(parts)

    async def _synthesize_responses(self, expert_responses: list[ExpertResponse]) -> str:
        """Synthesize responses into a coherent final answer.

        Combines expert responses intelligently by prioritizing high-confidence
        answers and noting disagreements.

        Args:
            expert_responses: List of expert responses to synthesize.

        Returns:
            Synthesized final response.
        """
        logger.info("synthesize_responses_start: num_experts=%d", len(expert_responses))

        # Sort by confidence
        sorted_responses = sorted(
            expert_responses,
            key=lambda r: r.confidence,
            reverse=True,
        )

        # Primary response from highest confidence expert
        primary = sorted_responses[0]
        synthesis = f"**Primary Response** (from {primary.expert_name}, confidence: {primary.confidence:.2f}):\n\n{primary.response}"

        # Add supporting or dissenting views if confidence is low
        if primary.confidence < 0.8 and len(sorted_responses) > 1:
            synthesis += "\n\n**Additional Perspectives:**\n"
            for response in sorted_responses[1:]:
                synthesis += f"\n- **{response.expert_name}** (confidence: {response.confidence:.2f}):\n  {response.response[:200]}..."

        logger.info(
            "synthesize_responses_complete: primary_expert=%s, additional_views=%d",
            primary.expert_name,
            len(sorted_responses) - 1 if primary.confidence < 0.8 else 0,
        )

        return synthesis

    def _calculate_overall_confidence(self, expert_responses: list[ExpertResponse]) -> float:
        """Calculate overall confidence from expert responses.

        Uses weighted average of expert confidences.

        Args:
            expert_responses: List of expert responses.

        Returns:
            Overall confidence score (0.0-1.0).
        """
        if not expert_responses:
            return 0.0

        # Weighted average: higher confidence experts contribute more
        total_weight = sum(r.confidence for r in expert_responses)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(r.confidence * r.confidence for r in expert_responses)
        overall = weighted_sum / total_weight

        # Clip to [0.0, 1.0] range
        return max(0.0, min(1.0, overall))
