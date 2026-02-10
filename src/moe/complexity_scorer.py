"""Query complexity scoring via LLM classifier with heuristic fallback."""

import json
import logging
from typing import Any

import httpx

from src.moe.model_tier import ComplexityScore

logger = logging.getLogger(__name__)

# Keywords for heuristic scoring
REASONING_KEYWORDS: list[str] = [
    "why",
    "how",
    "compare",
    "debug",
    "explain",
    "analyze",
    "evaluate",
    "difference",
]

DOMAIN_KEYWORDS: list[str] = [
    "algorithm",
    "database",
    "api",
    "kubernetes",
    "machine learning",
    "neural",
    "quantum",
]

CREATIVITY_KEYWORDS: list[str] = [
    "write",
    "create",
    "design",
    "generate",
    "compose",
    "imagine",
    "story",
]

LENGTH_KEYWORDS: list[str] = [
    "list",
    "detailed",
    "comprehensive",
]

_SCORING_PROMPT = """Score this query on 5 dimensions (0-10 each):
1. reasoning_depth: How much multi-step reasoning is required
2. domain_specificity: How specialized the domain knowledge is
3. creativity: How much creative generation is needed
4. context_dependency: How much prior context matters
5. output_length: Expected response length/detail

Query: {query}

Respond with JSON: {{"reasoning_depth": N, "domain_specificity": N, "creativity": N, "context_dependency": N, "output_length": N}}"""


class QueryComplexityScorer:
    """Scores query complexity across five dimensions using an LLM classifier.

    Uses a lightweight classifier model (e.g. Haiku) to produce structured
    complexity scores. Falls back to keyword-based heuristics when the LLM
    call fails.

    Args:
        api_key: API key for the LLM provider (never logged).
        base_url: Base URL for the LLM API.
        classifier_model: Model identifier for the classifier.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        classifier_model: str = "anthropic/claude-haiku-4.5",
    ) -> None:
        self._api_key: str = api_key
        self._base_url: str = base_url.rstrip("/")
        self._classifier_model: str = classifier_model

    async def score(
        self,
        query: str,
        conversation_history: list[str] | None = None,
        agent_dna: Any | None = None,
    ) -> ComplexityScore:
        """Score a query's complexity via LLM, falling back to heuristics.

        Makes an async LLM call to the classifier model for structured
        scoring of five dimensions. On any error, falls back to keyword-based
        heuristic scoring.

        Args:
            query: The user query to score.
            conversation_history: Optional list of prior messages for context.
            agent_dna: Optional agent configuration (reserved for future use).

        Returns:
            ComplexityScore with five dimension scores in [0.0, 10.0].
        """
        try:
            return await self._llm_score(query, conversation_history)
        except Exception as exc:
            logger.warning(f"complexity_scorer_llm_fallback: error={exc}, using_heuristic=true")
            return self._heuristic_score(query, conversation_history)

    async def _llm_score(
        self,
        query: str,
        conversation_history: list[str] | None = None,
    ) -> ComplexityScore:
        """Call the classifier LLM for structured complexity scoring.

        Args:
            query: The user query to score.
            conversation_history: Optional prior messages.

        Returns:
            ComplexityScore parsed from the LLM JSON response.

        Raises:
            httpx.TimeoutException: On request timeout.
            httpx.RequestError: On network errors.
            ValueError: On unparseable LLM response.
        """
        prompt = _SCORING_PROMPT.format(query=query)

        # Include conversation history length as context hint
        if conversation_history:
            prompt += f"\n\nConversation history length: {len(conversation_history)} messages"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._classifier_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
            )

        if response.status_code >= 400:
            logger.error(f"complexity_scorer_api_error: status={response.status_code}")
            raise ValueError(f"Classifier API returned HTTP {response.status_code}")

        data = response.json()
        content: str = data["choices"][0]["message"]["content"]

        # Extract JSON from the response (handle markdown code blocks)
        json_str = content.strip()
        if json_str.startswith("```"):
            # Strip markdown code fences
            lines = json_str.split("\n")
            json_str = "\n".join(line for line in lines if not line.strip().startswith("```"))

        scores = json.loads(json_str)

        logger.info(
            f"complexity_scorer_llm_success: model={self._classifier_model}, "
            f"weighted_total={ComplexityScore(**scores).weighted_total:.2f}"
        )

        return ComplexityScore(**scores)

    def _heuristic_score(
        self,
        query: str,
        conversation_history: list[str] | None = None,
    ) -> ComplexityScore:
        """Keyword-based fallback scoring (no LLM needed).

        Counts keyword matches in the query to produce approximate complexity
        scores across all five dimensions.

        Args:
            query: The user query to score.
            conversation_history: Optional prior messages for context_dependency.

        Returns:
            ComplexityScore based on keyword heuristics.
        """
        query_lower = query.lower()

        # reasoning_depth: count reasoning keywords -> scale 0-10
        reasoning_count = sum(1 for kw in REASONING_KEYWORDS if kw in query_lower)
        reasoning_depth = min(reasoning_count * (10.0 / len(REASONING_KEYWORDS)), 10.0)

        # domain_specificity: count domain terms -> scale 0-10
        domain_count = sum(1 for kw in DOMAIN_KEYWORDS if kw in query_lower)
        domain_specificity = min(domain_count * (10.0 / len(DOMAIN_KEYWORDS)), 10.0)

        # creativity: count creativity keywords -> scale 0-10
        creativity_count = sum(1 for kw in CREATIVITY_KEYWORDS if kw in query_lower)
        creativity = min(creativity_count * (10.0 / len(CREATIVITY_KEYWORDS)), 10.0)

        # context_dependency: based on conversation_history length
        history_len = len(conversation_history) if conversation_history else 0
        if history_len == 0:
            context_dependency = 0.0
        elif history_len <= 3:
            context_dependency = 3.0
        elif history_len <= 10:
            context_dependency = 6.0
        else:
            context_dependency = 8.0

        # output_length: based on query length and keywords
        length_keyword_count = sum(1 for kw in LENGTH_KEYWORDS if kw in query_lower)
        # Longer queries tend to request longer outputs
        query_length_factor = min(len(query) / 200.0, 5.0)
        output_length = min(length_keyword_count * 3.0 + query_length_factor, 10.0)

        score = ComplexityScore(
            reasoning_depth=reasoning_depth,
            domain_specificity=domain_specificity,
            creativity=creativity,
            context_dependency=context_dependency,
            output_length=output_length,
        )

        logger.info(f"complexity_scorer_heuristic: weighted_total={score.weighted_total:.2f}")

        return score
