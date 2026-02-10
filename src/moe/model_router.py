"""Model tier routing based on complexity scores and budget constraints."""

import logging

from src.moe.model_tier import ComplexityScore, ModelTier

logger = logging.getLogger(__name__)

# Tier ordering for cap comparisons (higher value = more powerful)
TIER_ORDER: dict[str, int] = {
    "fast": 0,
    "balanced": 1,
    "powerful": 2,
}

DEFAULT_TIERS: list[ModelTier] = [
    ModelTier(
        name="fast",
        model_name="anthropic/claude-haiku-4.5",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
    ),
    ModelTier(
        name="balanced",
        model_name="anthropic/claude-sonnet-4.5",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    ModelTier(
        name="powerful",
        model_name="anthropic/claude-opus-4",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    ),
]


class ModelRouter:
    """Routes queries to the appropriate model tier based on complexity.

    Maps a ComplexityScore's weighted total to a model tier, respecting
    optional force/max tier constraints and budget limits.

    Args:
        tiers: Ordered list of model tiers. Defaults to DEFAULT_TIERS.
    """

    def __init__(self, tiers: list[ModelTier] | None = None) -> None:
        self._tiers: list[ModelTier] = tiers if tiers is not None else list(DEFAULT_TIERS)

    def route(
        self,
        score: ComplexityScore,
        force_tier: str | None = None,
        max_tier: str | None = None,
        budget_remaining: float | None = None,
        custom_tiers: list[ModelTier] | None = None,
    ) -> ModelTier:
        """Select the best model tier for a given complexity score.

        Applies overrides in priority order: force_tier, then budget
        downgrade, then max_tier cap.

        Args:
            score: The complexity score to route on.
            force_tier: If set, return this exact tier (by name).
            max_tier: If set, cap the selected tier at this level.
            budget_remaining: Remaining budget in USD. If < 0.01,
                downgrades to the cheapest tier.
            custom_tiers: Optional override tier list for this call.

        Returns:
            The selected ModelTier.

        Raises:
            ValueError: If force_tier or max_tier name is not found in
                the active tier list.
        """
        active_tiers = custom_tiers if custom_tiers is not None else self._tiers

        # Build a name -> tier lookup
        tier_map: dict[str, ModelTier] = {t.name: t for t in active_tiers}

        # Force tier: exact match, return immediately
        if force_tier is not None:
            if force_tier not in tier_map:
                raise ValueError(
                    f"force_tier '{force_tier}' not found in tiers: {list(tier_map.keys())}"
                )
            logger.info(f"model_router_force: tier={force_tier}")
            return tier_map[force_tier]

        # Map weighted_total to tier name
        total = score.weighted_total
        if total <= 3.0:
            selected_name = "fast"
        elif total <= 6.0:
            selected_name = "balanced"
        else:
            selected_name = "powerful"

        # Fallback: if the mapped name doesn't exist in active_tiers, pick
        # the closest available tier by TIER_ORDER
        if selected_name not in tier_map:
            selected_name = self._closest_tier(selected_name, tier_map)

        # Budget downgrade: if budget is nearly exhausted, use cheapest
        if budget_remaining is not None and budget_remaining < 0.01:
            cheapest = min(
                active_tiers,
                key=lambda t: TIER_ORDER.get(t.name, 0),
            )
            logger.info(
                f"model_router_budget_downgrade: "
                f"from={selected_name}, to={cheapest.name}, "
                f"budget_remaining={budget_remaining:.4f}"
            )
            selected_name = cheapest.name

        # Max tier cap
        if max_tier is not None:
            if max_tier not in tier_map:
                raise ValueError(
                    f"max_tier '{max_tier}' not found in tiers: {list(tier_map.keys())}"
                )
            max_order = TIER_ORDER.get(max_tier, 0)
            selected_order = TIER_ORDER.get(selected_name, 0)
            if selected_order > max_order:
                logger.info(f"model_router_cap: from={selected_name}, to={max_tier}")
                selected_name = max_tier

        result = tier_map[selected_name]
        logger.info(
            f"model_router_selected: tier={result.name}, "
            f"model={result.model_name}, "
            f"weighted_total={total:.2f}"
        )
        return result

    @staticmethod
    def _closest_tier(
        target_name: str,
        tier_map: dict[str, ModelTier],
    ) -> str:
        """Find the closest available tier by TIER_ORDER distance.

        Args:
            target_name: The desired tier name that isn't in tier_map.
            tier_map: Available tiers keyed by name.

        Returns:
            Name of the closest available tier.
        """
        target_order = TIER_ORDER.get(target_name, 0)
        return min(
            tier_map.keys(),
            key=lambda name: abs(TIER_ORDER.get(name, 0) - target_order),
        )
