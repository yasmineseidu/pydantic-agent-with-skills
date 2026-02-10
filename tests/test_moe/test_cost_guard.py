"""Unit tests for CostGuard budget enforcement."""

import asyncio

import pytest

from src.moe.cost_guard import CostGuard


class TestBudgetChecks:
    """Tests for check_budget allowing and denying requests."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_within_budget_allowed(self) -> None:
        """Within budget -> allowed=True with correct remaining."""
        guard = CostGuard(daily_budget_usd=5.0, monthly_budget_usd=100.0)
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )

        assert result.allowed is True
        assert result.remaining == pytest.approx(4.0)
        assert result.suggested_tier is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_daily_budget_exceeded(self) -> None:
        """Daily budget exceeded -> allowed=False, suggested_tier='fast'."""
        guard = CostGuard(daily_budget_usd=5.0, monthly_budget_usd=100.0)

        # Spend most of the daily budget first
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=4.5)

        # Now try to spend more than remaining daily
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )

        assert result.allowed is False
        assert result.suggested_tier == "fast"
        assert result.remaining == pytest.approx(0.5)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_monthly_budget_exceeded(self) -> None:
        """Monthly budget exceeded -> allowed=False."""
        guard = CostGuard(daily_budget_usd=200.0, monthly_budget_usd=10.0)

        # Spend most of the monthly budget
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=9.5)

        # Now try to spend more than remaining monthly
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )

        assert result.allowed is False
        assert result.suggested_tier == "fast"
        assert result.remaining == pytest.approx(0.5)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_near_boundary_daily_exceeded(self) -> None:
        """Near-boundary: daily_budget=5.0, spent=4.99, cost=0.02 -> exceeded."""
        guard = CostGuard(daily_budget_usd=5.0, monthly_budget_usd=100.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=4.99)

        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=0.02,
        )

        # 4.99 + 0.02 = 5.01 > 5.0 -> exceeded
        assert result.allowed is False
        assert result.suggested_tier == "fast"
        assert result.remaining == pytest.approx(0.01)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_exact_budget_allowed(self) -> None:
        """Spending exactly the remaining budget is not allowed (strict >)."""
        guard = CostGuard(daily_budget_usd=5.0, monthly_budget_usd=100.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=4.0)

        # 4.0 + 1.0 = 5.0, which is not > 5.0 -> allowed
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )

        assert result.allowed is True
        assert result.remaining == pytest.approx(0.0)


class TestRecordCost:
    """Tests for cost recording and accumulation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_record_cost_increments_counters(self) -> None:
        """record_cost increments internal daily and monthly counters."""
        guard = CostGuard(daily_budget_usd=10.0, monthly_budget_usd=100.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=2.0)

        # Verify by checking budget: remaining should be 10.0 - 2.0 - 1.0 = 7.0
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )
        assert result.allowed is True
        assert result.remaining == pytest.approx(7.0)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_record_cost_accumulate(self) -> None:
        """Multiple record_cost calls accumulate spending."""
        guard = CostGuard(daily_budget_usd=10.0, monthly_budget_usd=100.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=2.0)
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=3.0)
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=1.5)

        # Total recorded: 6.5, check budget with 1.0 -> remaining = 10.0 - 6.5 - 1.0 = 2.5
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )
        assert result.allowed is True
        assert result.remaining == pytest.approx(2.5)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_different_users_tracked_separately(self) -> None:
        """Different user_ids have independent daily budgets."""
        guard = CostGuard(daily_budget_usd=5.0, monthly_budget_usd=100.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=4.5)

        # user-2 should have full budget
        result = await guard.check_budget(
            user_id="user-2",
            team_id="team-1",
            estimated_cost=3.0,
        )
        assert result.allowed is True
        assert result.remaining == pytest.approx(2.0)


class TestCustomBudgets:
    """Tests for custom budget amounts in constructor."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_custom_daily_budget(self) -> None:
        """Custom daily_budget_usd is respected."""
        guard = CostGuard(daily_budget_usd=2.0, monthly_budget_usd=100.0)

        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.5,
        )
        assert result.allowed is True
        assert result.remaining == pytest.approx(0.5)

        # Exceed the small daily budget
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=1.5)
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )
        assert result.allowed is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_custom_monthly_budget(self) -> None:
        """Custom monthly_budget_usd is respected."""
        guard = CostGuard(daily_budget_usd=100.0, monthly_budget_usd=3.0)

        await guard.record_cost(user_id="user-1", team_id="team-1", cost=2.5)

        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=1.0,
        )
        assert result.allowed is False
        assert result.suggested_tier == "fast"


class TestThreadSafety:
    """Tests for concurrent access safety via asyncio.Lock."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_check_budget_no_corruption(self) -> None:
        """Concurrent check_budget calls don't corrupt state."""
        guard = CostGuard(daily_budget_usd=100.0, monthly_budget_usd=1000.0)

        # Record a known baseline
        await guard.record_cost(user_id="user-1", team_id="team-1", cost=10.0)

        # Fire 50 concurrent check_budget calls
        tasks = [
            guard.check_budget(
                user_id="user-1",
                team_id="team-1",
                estimated_cost=0.5,
            )
            for _ in range(50)
        ]
        results = await asyncio.gather(*tasks)

        # All should be allowed (10 + 0.5 = 10.5 < 100)
        for result in results:
            assert result.allowed is True
            assert result.remaining == pytest.approx(89.5)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_record_cost_accumulates_correctly(self) -> None:
        """Concurrent record_cost calls accumulate correctly via lock."""
        guard = CostGuard(daily_budget_usd=1000.0, monthly_budget_usd=10000.0)

        # Fire 100 concurrent record_cost calls of 1.0 each
        tasks = [
            guard.record_cost(user_id="user-1", team_id="team-1", cost=1.0) for _ in range(100)
        ]
        await asyncio.gather(*tasks)

        # Total should be exactly 100.0
        result = await guard.check_budget(
            user_id="user-1",
            team_id="team-1",
            estimated_cost=0.0,
        )
        # remaining = 1000.0 - 100.0 - 0.0 = 900.0
        assert result.remaining == pytest.approx(900.0)
