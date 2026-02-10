"""Tests for ResponseAggregator."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.collaboration.aggregation.response_aggregator import ResponseAggregator
from src.moe.models import ExpertResponse


def _settings(enable_ensemble: bool = True):
    return SimpleNamespace(feature_flags=SimpleNamespace(enable_ensemble_mode=enable_ensemble))


@pytest.mark.asyncio
async def test_aggregate_responses_requires_feature_flag() -> None:
    aggregator = ResponseAggregator(_settings(enable_ensemble=False))

    with pytest.raises(ValueError):
        await aggregator.aggregate_responses(
            [
                ExpertResponse(
                    expert_id="11111111-1111-1111-1111-111111111111",
                    expert_name="Analyst",
                    response="Output",
                    confidence=0.9,
                )
            ]
        )


@pytest.mark.asyncio
async def test_aggregate_responses_synthesis() -> None:
    aggregator = ResponseAggregator(_settings(enable_ensemble=True))

    responses = [
        ExpertResponse(
            expert_id="11111111-1111-1111-1111-111111111111",
            expert_name="Analyst",
            response="First response",
            confidence=0.9,
        ),
        ExpertResponse(
            expert_id="22222222-2222-2222-2222-222222222222",
            expert_name="Reviewer",
            response="Second response",
            confidence=0.8,
        ),
    ]

    aggregated = await aggregator.aggregate_responses(responses, method="synthesis")

    assert aggregated.aggregation_method == "synthesis"
    assert aggregated.confidence > 0
    assert aggregated.expert_responses == responses
