"""Agent routing service for selecting optimal agents based on query and capabilities."""

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from src.collaboration.models import RoutingDecision, AgentRecommendation

if TYPE_CHECKING:
    from src.collaboration.routing.agent_directory import AgentDirectory
    from src.settings import Settings

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes queries to optimal agents based on skill matching and personality.

    Analyzes user queries and agent profiles to determine the best single agent
    or recommend multi-agent collaboration when diverse expertise is needed.

    Args:
        agent_directory: Registry of available agents and their capabilities.
        settings: Application settings including feature flags.
    """

    def __init__(
        self,
        agent_directory: "AgentDirectory",
        settings: "Settings",
    ) -> None:
        self._directory = agent_directory
        self._settings = settings

    async def route_to_agent(
        self,
        query: str,
        user_id: UUID,
        current_agent_id: Optional[UUID] = None,
        conversation_history: Optional[list[str]] = None,
    ) -> RoutingDecision:
        """Route a query to the single best agent based on capabilities.

        Analyzes query requirements and matches against agent skills and
        personality traits. Returns the agent with highest confidence match.

        Args:
            query: User query to route.
            user_id: UUID of the user making the request.
            current_agent_id: UUID of current agent (to avoid routing to self).
            conversation_history: Optional conversation context.

        Returns:
            RoutingDecision with selected agent, confidence, and reasoning.
        """
        # Check feature flag
        if not self._settings.feature_flags.enable_expert_gate:
            logger.info(
                f"route_to_agent_disabled: feature_flag=enable_expert_gate, user_id={user_id}"
            )
            return RoutingDecision(
                selected_agent_id=current_agent_id or UUID(int=0),
                confidence=0.0,
                reasoning="Error: Agent routing disabled (enable_expert_gate=False)",
                alternatives=[],
            )

        try:
            # Get all available agents
            agents = await self._directory.list_agents(user_id=user_id)

            if not agents:
                logger.warning(f"route_to_agent_no_agents: user_id={user_id}")
                return RoutingDecision(
                    selected_agent_id=current_agent_id or UUID(int=0),
                    confidence=0.0,
                    reasoning="Error: No agents available in directory",
                    alternatives=[],
                )

            # Filter out current agent
            if current_agent_id:
                agents = [a for a in agents if a.agent_id != current_agent_id]

            if not agents:
                logger.info(
                    f"route_to_agent_only_self: "
                    f"user_id={user_id}, current_agent_id={current_agent_id}"
                )
                return RoutingDecision(
                    selected_agent_id=current_agent_id or UUID(int=0),
                    confidence=1.0,
                    reasoning="Only current agent available",
                    alternatives=[],
                )

            # Calculate skill match scores for all agents
            scored_agents: list[tuple[UUID, float, str]] = []
            for agent in agents:
                skill_score = self._calculate_skill_match(
                    query=query,
                    agent_capabilities=agent.capabilities,
                    agent_specializations=agent.specializations,
                )

                # Check personality compatibility
                personality_boost = (
                    0.1
                    if self._personality_compatible(
                        query=query,
                        personality_summary=agent.personality_summary,
                    )
                    else 0.0
                )

                total_score = min(1.0, skill_score + personality_boost)

                reasoning = (
                    f"Skill match: {skill_score:.2f}, "
                    f"Personality boost: {personality_boost:.2f}, "
                    f"Capabilities: {', '.join(agent.capabilities[:3])}"
                )

                scored_agents.append((agent.agent_id, total_score, reasoning))

            # Sort by score descending
            scored_agents.sort(key=lambda x: x[1], reverse=True)

            # Select best agent
            best_agent_id, best_score, best_reasoning = scored_agents[0]

            # Extract alternatives
            alternatives = [agent_id for agent_id, _, _ in scored_agents[1:4]]

            logger.info(
                f"route_decision: agent_id={best_agent_id}, "
                f"confidence={best_score:.2f}, "
                f"user_id={user_id}, "
                f"alternatives_count={len(alternatives)}"
            )

            return RoutingDecision(
                selected_agent_id=best_agent_id,
                confidence=best_score,
                reasoning=best_reasoning,
                alternatives=alternatives,
            )

        except Exception as e:
            logger.error(f"route_to_agent_error: user_id={user_id}, error={str(e)}")
            return RoutingDecision(
                selected_agent_id=current_agent_id or UUID(int=0),
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                alternatives=[],
            )

    async def suggest_collaboration(
        self,
        query: str,
        user_id: UUID,
        min_agents: int = 2,
        max_agents: int = 4,
    ) -> list[AgentRecommendation]:
        """Recommend multiple agents for collaborative work on complex queries.

        Identifies queries that require diverse expertise and suggests a team
        of complementary agents. Useful for tasks like research synthesis,
        multi-perspective analysis, or cross-domain problem solving.

        Args:
            query: User query to analyze.
            user_id: UUID of the user making the request.
            min_agents: Minimum number of agents to recommend.
            max_agents: Maximum number of agents to recommend.

        Returns:
            List of AgentRecommendation objects sorted by match score.
        """
        # Check feature flag
        if not self._settings.feature_flags.enable_collaboration:
            logger.info(
                f"suggest_collaboration_disabled: feature_flag=enable_collaboration, "
                f"user_id={user_id}"
            )
            return []

        try:
            # Get all available agents
            agents = await self._directory.list_agents(user_id=user_id)

            if len(agents) < min_agents:
                logger.warning(
                    f"suggest_collaboration_insufficient_agents: "
                    f"available={len(agents)}, min_required={min_agents}, "
                    f"user_id={user_id}"
                )
                return []

            # Score all agents
            recommendations: list[AgentRecommendation] = []
            for agent in agents:
                skill_score = self._calculate_skill_match(
                    query=query,
                    agent_capabilities=agent.capabilities,
                    agent_specializations=agent.specializations,
                )

                # Weight specialization higher for collaboration
                specialization_bonus = 0.15 if agent.specializations else 0.0
                total_score = min(1.0, skill_score + specialization_bonus)

                reasoning = (
                    f"Specialist in: {', '.join(agent.specializations[:2]) if agent.specializations else 'general'}, "
                    f"Skills: {', '.join(agent.capabilities[:2])}"
                )

                recommendations.append(
                    AgentRecommendation(
                        agent_id=agent.agent_id,
                        agent_name=agent.name,
                        match_score=total_score,
                        reasoning=reasoning,
                    )
                )

            # Sort by score descending and take top N
            recommendations.sort(key=lambda x: x.match_score, reverse=True)
            result = recommendations[:max_agents]

            logger.info(
                f"suggest_collaboration: user_id={user_id}, "
                f"recommended_count={len(result)}, "
                f"total_available={len(agents)}"
            )

            return result

        except Exception as e:
            logger.error(f"suggest_collaboration_error: user_id={user_id}, error={str(e)}")
            return []

    def _calculate_skill_match(
        self,
        query: str,
        agent_capabilities: list[str],
        agent_specializations: list[str],
    ) -> float:
        """Calculate skill match score between query and agent capabilities.

        Uses keyword matching and capability overlap to determine how well
        an agent's skills align with query requirements.

        Args:
            query: User query to match.
            agent_capabilities: List of agent capability tags.
            agent_specializations: List of agent specialization domains.

        Returns:
            Match score between 0.0 and 1.0.
        """
        query_lower = query.lower()
        score = 0.0

        # Check capability matches (0.5 weight)
        capability_matches = sum(1 for cap in agent_capabilities if cap.lower() in query_lower)
        if agent_capabilities:
            capability_score = min(1.0, capability_matches / len(agent_capabilities))
            score += capability_score * 0.5

        # Check specialization matches (0.5 weight)
        specialization_matches = sum(
            1 for spec in agent_specializations if spec.lower() in query_lower
        )
        if agent_specializations:
            specialization_score = min(1.0, specialization_matches / len(agent_specializations))
            score += specialization_score * 0.5

        # Boost for any match
        if capability_matches > 0 or specialization_matches > 0:
            score = max(score, 0.3)  # Minimum score for any match

        # Cap at 1.0
        return min(1.0, score)

    def _personality_compatible(
        self,
        query: str,
        personality_summary: str,
    ) -> bool:
        """Check if agent personality traits align with query tone.

        Detects query characteristics (formal, creative, analytical) and
        matches against agent personality descriptions.

        Args:
            query: User query to analyze.
            personality_summary: Agent personality description.

        Returns:
            True if personality appears compatible, False otherwise.
        """
        query_lower = query.lower()
        personality_lower = personality_summary.lower()

        # Formal/professional queries
        formal_keywords = ["please", "could you", "would you", "formal", "professional"]
        is_formal = any(kw in query_lower for kw in formal_keywords)
        if is_formal and any(
            trait in personality_lower for trait in ["professional", "formal", "precise", "careful"]
        ):
            return True

        # Creative queries
        creative_keywords = ["create", "imagine", "design", "story", "creative"]
        is_creative = any(kw in query_lower for kw in creative_keywords)
        if is_creative and any(
            trait in personality_lower
            for trait in ["creative", "imaginative", "innovative", "artistic"]
        ):
            return True

        # Analytical queries
        analytical_keywords = ["analyze", "compare", "evaluate", "debug", "why", "how"]
        is_analytical = any(kw in query_lower for kw in analytical_keywords)
        if is_analytical and any(
            trait in personality_lower
            for trait in ["analytical", "logical", "systematic", "thorough"]
        ):
            return True

        # Default: no strong compatibility signal
        return False
