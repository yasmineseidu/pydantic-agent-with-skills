"""Unit tests for QueryComplexityScorer heuristic and LLM scoring."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.moe.complexity_scorer import (
    CREATIVITY_KEYWORDS,
    DOMAIN_KEYWORDS,
    REASONING_KEYWORDS,
    QueryComplexityScorer,
)
from src.moe.model_tier import ComplexityScore


class TestHeuristicScoring:
    """Tests for keyword-based heuristic fallback scoring."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_why_query_has_high_reasoning_depth(self) -> None:
        """Heuristic 'why is the sky blue' -> high reasoning_depth from 'why' keyword."""
        scorer = QueryComplexityScorer(api_key="test-key")
        result = scorer._heuristic_score("why is the sky blue")

        # "why" matches 1 reasoning keyword -> 1 * (10 / 8) = 1.25
        expected_reasoning = 1.0 * (10.0 / len(REASONING_KEYWORDS))
        assert result.reasoning_depth == pytest.approx(expected_reasoning)
        # reasoning_depth should be the dominant dimension
        assert result.reasoning_depth > result.domain_specificity
        assert result.reasoning_depth > result.creativity

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_hello_query_has_low_all_dimensions(self) -> None:
        """Heuristic 'hello' -> low all dimensions (no keywords match)."""
        scorer = QueryComplexityScorer(api_key="test-key")
        result = scorer._heuristic_score("hello")

        assert result.reasoning_depth == 0.0
        assert result.domain_specificity == 0.0
        assert result.creativity == 0.0
        assert result.context_dependency == 0.0
        # output_length is only from query_length_factor: len("hello")/200 = 0.025
        assert result.output_length == pytest.approx(len("hello") / 200.0)
        assert result.weighted_total < 1.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_write_poem_has_high_creativity(self) -> None:
        """Heuristic 'write a poem about AI' -> high creativity from 'write' keyword."""
        scorer = QueryComplexityScorer(api_key="test-key")
        result = scorer._heuristic_score("write a poem about AI")

        # "write" matches 1 creativity keyword -> 1 * (10 / 7) ~ 1.4286
        expected_creativity = 1.0 * (10.0 / len(CREATIVITY_KEYWORDS))
        assert result.creativity == pytest.approx(expected_creativity)
        assert result.creativity > result.reasoning_depth
        assert result.creativity > result.domain_specificity

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_compare_database_algorithms_high_reasoning_and_domain(self) -> None:
        """Heuristic 'compare database algorithms' -> high reasoning + domain."""
        scorer = QueryComplexityScorer(api_key="test-key")
        result = scorer._heuristic_score("compare database algorithms")

        # "compare" matches reasoning -> 1 * (10 / 8) = 1.25
        expected_reasoning = 1.0 * (10.0 / len(REASONING_KEYWORDS))
        assert result.reasoning_depth == pytest.approx(expected_reasoning)

        # "database" and "algorithm" match domain -> 2 * (10 / 7) ~ 2.857
        expected_domain = 2.0 * (10.0 / len(DOMAIN_KEYWORDS))
        assert result.domain_specificity == pytest.approx(expected_domain)

        # Both should be higher than creativity (no creativity keywords)
        assert result.reasoning_depth > result.creativity
        assert result.domain_specificity > result.creativity

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_conversation_history_context_zero(self) -> None:
        """Heuristic with no conversation history -> context_dependency = 0.0."""
        scorer = QueryComplexityScorer(api_key="test-key")
        result = scorer._heuristic_score("test query", conversation_history=None)
        assert result.context_dependency == 0.0

        result_empty = scorer._heuristic_score("test query", conversation_history=[])
        assert result_empty.context_dependency == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_five_messages_history_context_six(self) -> None:
        """Heuristic with 5 messages history -> context_dependency = 6.0."""
        scorer = QueryComplexityScorer(api_key="test-key")
        history = [f"message {i}" for i in range(5)]
        result = scorer._heuristic_score("test query", conversation_history=history)

        # 5 messages: 3 < 5 <= 10 -> context_dependency = 6.0
        assert result.context_dependency == 6.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fifteen_messages_history_context_eight(self) -> None:
        """Heuristic with 15 messages history -> context_dependency = 8.0."""
        scorer = QueryComplexityScorer(api_key="test-key")
        history = [f"message {i}" for i in range(15)]
        result = scorer._heuristic_score("test query", conversation_history=history)

        # 15 messages: > 10 -> context_dependency = 8.0
        assert result.context_dependency == 8.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_three_messages_history_context_three(self) -> None:
        """Heuristic with 3 messages -> context_dependency = 3.0 (boundary)."""
        scorer = QueryComplexityScorer(api_key="test-key")
        history = [f"message {i}" for i in range(3)]
        result = scorer._heuristic_score("test query", conversation_history=history)

        # 3 messages: 0 < 3 <= 3 -> context_dependency = 3.0
        assert result.context_dependency == 3.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ten_messages_history_context_six(self) -> None:
        """Heuristic with 10 messages -> context_dependency = 6.0 (boundary)."""
        scorer = QueryComplexityScorer(api_key="test-key")
        history = [f"message {i}" for i in range(10)]
        result = scorer._heuristic_score("test query", conversation_history=history)

        # 10 messages: 3 < 10 <= 10 -> context_dependency = 6.0
        assert result.context_dependency == 6.0


class TestLLMScoring:
    """Tests for LLM-based scoring with mocked httpx calls."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_fallback_on_error_uses_heuristic(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When httpx raises an exception, fall back to heuristic with warning log."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=RuntimeError("Connection refused"))

        with patch("src.moe.complexity_scorer.httpx.AsyncClient", return_value=mock_client):
            scorer = QueryComplexityScorer(api_key="test-key")
            with caplog.at_level(logging.WARNING, logger="src.moe.complexity_scorer"):
                result = await scorer.score("hello")

        # Should return heuristic result (same as calling _heuristic_score directly)
        expected = scorer._heuristic_score("hello")
        assert result.reasoning_depth == expected.reasoning_depth
        assert result.domain_specificity == expected.domain_specificity
        assert result.creativity == expected.creativity
        assert result.context_dependency == expected.context_dependency
        assert result.output_length == pytest.approx(expected.output_length)

        # Should have logged a warning about fallback
        assert any("complexity_scorer_llm_fallback" in record.message for record in caplog.records)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_score_success_returns_complexity_score(self) -> None:
        """Mock httpx 200 with valid JSON -> returns ComplexityScore from LLM."""
        llm_scores = {
            "reasoning_depth": 5.0,
            "domain_specificity": 3.0,
            "creativity": 2.0,
            "context_dependency": 4.0,
            "output_length": 3.0,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"reasoning_depth": 5, "domain_specificity": 3, '
                            '"creativity": 2, "context_dependency": 4, "output_length": 3}'
                        )
                    }
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.moe.complexity_scorer.httpx.AsyncClient", return_value=mock_client):
            scorer = QueryComplexityScorer(api_key="test-key")
            result = await scorer.score("test query")

        assert isinstance(result, ComplexityScore)
        assert result.reasoning_depth == pytest.approx(llm_scores["reasoning_depth"])
        assert result.domain_specificity == pytest.approx(llm_scores["domain_specificity"])
        assert result.creativity == pytest.approx(llm_scores["creativity"])
        assert result.context_dependency == pytest.approx(llm_scores["context_dependency"])
        assert result.output_length == pytest.approx(llm_scores["output_length"])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_score_with_markdown_fences(self) -> None:
        """Mock httpx 200 with markdown code-fenced JSON -> still parses correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            '{"reasoning_depth": 7, "domain_specificity": 4, '
                            '"creativity": 1, "context_dependency": 6, "output_length": 5}\n'
                            "```"
                        )
                    }
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.moe.complexity_scorer.httpx.AsyncClient", return_value=mock_client):
            scorer = QueryComplexityScorer(api_key="test-key")
            result = await scorer.score("complex query")

        assert isinstance(result, ComplexityScore)
        assert result.reasoning_depth == pytest.approx(7.0)
        assert result.context_dependency == pytest.approx(6.0)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_score_http_error_falls_back(self) -> None:
        """Mock httpx 500 -> ValueError raised internally -> heuristic fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.moe.complexity_scorer.httpx.AsyncClient", return_value=mock_client):
            scorer = QueryComplexityScorer(api_key="test-key")
            result = await scorer.score("hello")

        # Falls back to heuristic
        expected = scorer._heuristic_score("hello")
        assert result.reasoning_depth == expected.reasoning_depth
        assert result.output_length == pytest.approx(expected.output_length)
