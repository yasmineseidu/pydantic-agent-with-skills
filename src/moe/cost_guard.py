"""Budget enforcement for model routing with daily and monthly limits."""

import asyncio
import logging
from datetime import datetime, timezone

from src.moe.model_tier import BudgetCheck

logger = logging.getLogger(__name__)


class CostGuard:
    """In-memory budget guard with daily per-user and monthly per-team limits.

    Tracks spending in memory with automatic reset at day and month
    boundaries. Thread-safe via asyncio.Lock.

    Args:
        daily_budget_usd: Maximum daily spend per user in USD.
        monthly_budget_usd: Maximum monthly spend per team in USD.
    """

    def __init__(
        self,
        daily_budget_usd: float = 5.0,
        monthly_budget_usd: float = 100.0,
    ) -> None:
        self._daily_budget: float = daily_budget_usd
        self._monthly_budget: float = monthly_budget_usd
        self._daily_counters: dict[str, float] = {}
        self._monthly_counters: dict[str, float] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    def _cleanup_stale_counters(self) -> None:
        """Remove counter keys from previous days/months to prevent unbounded growth.

        Must be called while holding self._lock. Uses UTC to match key
        generation in check_budget() and record_cost().
        """
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        this_month = now.strftime("%Y-%m")

        stale_daily = [k for k in self._daily_counters if not k.endswith(today)]
        for k in stale_daily:
            del self._daily_counters[k]

        stale_monthly = [k for k in self._monthly_counters if not k.endswith(this_month)]
        for k in stale_monthly:
            del self._monthly_counters[k]

        if stale_daily or stale_monthly:
            logger.info(
                f"cost_guard_cleanup: pruned_daily={len(stale_daily)}, "
                f"pruned_monthly={len(stale_monthly)}"
            )

    async def check_budget(
        self,
        user_id: str,
        team_id: str,
        estimated_cost: float,
    ) -> BudgetCheck:
        """Check whether estimated_cost fits within daily and monthly budgets.

        Args:
            user_id: Unique user identifier for daily tracking.
            team_id: Team identifier for monthly tracking.
            estimated_cost: Projected cost in USD for the upcoming request.

        Returns:
            BudgetCheck indicating whether the request is allowed,
            remaining budget, and an optional suggested cheaper tier.
        """
        async with self._lock:
            self._cleanup_stale_counters()
            now = datetime.now(timezone.utc)

            daily_key = f"{user_id}:{now.strftime('%Y-%m-%d')}"
            monthly_key = f"{team_id}:{now.strftime('%Y-%m')}"

            daily_spent = self._daily_counters.get(daily_key, 0.0)
            monthly_spent = self._monthly_counters.get(monthly_key, 0.0)

            # Check daily user budget
            if daily_spent + estimated_cost > self._daily_budget:
                remaining = max(self._daily_budget - daily_spent, 0.0)
                logger.warning(
                    f"cost_guard_daily_exceeded: user={user_id}, "
                    f"spent={daily_spent:.4f}, "
                    f"estimated={estimated_cost:.4f}, "
                    f"budget={self._daily_budget:.2f}"
                )
                return BudgetCheck(
                    allowed=False,
                    remaining=remaining,
                    suggested_tier="fast",
                )

            # Check monthly team budget
            if monthly_spent + estimated_cost > self._monthly_budget:
                remaining = max(self._monthly_budget - monthly_spent, 0.0)
                logger.warning(
                    f"cost_guard_monthly_exceeded: team={team_id}, "
                    f"spent={monthly_spent:.4f}, "
                    f"estimated={estimated_cost:.4f}, "
                    f"budget={self._monthly_budget:.2f}"
                )
                return BudgetCheck(
                    allowed=False,
                    remaining=remaining,
                    suggested_tier="fast",
                )

            # Within budget
            remaining = self._daily_budget - daily_spent - estimated_cost
            logger.info(
                f"cost_guard_allowed: user={user_id}, team={team_id}, "
                f"estimated={estimated_cost:.4f}, remaining={remaining:.4f}"
            )
            return BudgetCheck(
                allowed=True,
                remaining=remaining,
            )

    async def record_cost(
        self,
        user_id: str,
        team_id: str,
        cost: float,
    ) -> None:
        """Record actual cost against daily and monthly counters.

        Args:
            user_id: Unique user identifier for daily tracking.
            team_id: Team identifier for monthly tracking.
            cost: Actual cost in USD to record.
        """
        async with self._lock:
            self._cleanup_stale_counters()
            now = datetime.now(timezone.utc)

            daily_key = f"{user_id}:{now.strftime('%Y-%m-%d')}"
            monthly_key = f"{team_id}:{now.strftime('%Y-%m')}"

            self._daily_counters[daily_key] = self._daily_counters.get(daily_key, 0.0) + cost
            self._monthly_counters[monthly_key] = (
                self._monthly_counters.get(monthly_key, 0.0) + cost
            )

            logger.info(
                f"cost_guard_recorded: user={user_id}, team={team_id}, "
                f"cost={cost:.4f}, "
                f"daily_total={self._daily_counters[daily_key]:.4f}, "
                f"monthly_total={self._monthly_counters[monthly_key]:.4f}"
            )
