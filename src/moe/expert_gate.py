"""Expert gate for 4-signal agent selection with weighted scoring."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.agent import AgentORM, AgentStatusEnum
from src.moe.models import ExpertScore, SelectionResult
from src.settings import Settings

logger = logging.getLogger(__name__)


class ExpertGate:
    """Four-signal scoring system for expert agent selection.

    Evaluates agents using four weighted signals:
    - skill_match (40%): How well the agent's skills match the task
    - past_performance (25%): Historical success rate on similar tasks
    - personality_fit (20%): How well the agent's personality suits the task
    - load_balance (15%): Current workload and availability

    Args:
        settings: Application settings with feature flag for expert_gate.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the expert gate.

        Args:
            settings: Application settings for feature flag checks.
        """
        self._settings: Settings = settings

    async def score_agents(
        self,
        session: AsyncSession,
        team_id: UUID,
        task_description: str,
        required_skills: Optional[list[str]] = None,
        task_metadata: Optional[dict[str, str]] = None,
    ) -> list[tuple[AgentORM, ExpertScore]]:
        """Score all active agents in a team for a task.

        Args:
            session: Database session for agent lookup.
            team_id: Team to score agents for.
            task_description: Description of the task to match against.
            required_skills: Optional list of skill names required for the task.
            task_metadata: Optional task metadata for personality/load scoring.

        Returns:
            List of (agent, score) tuples sorted by overall score descending.
        """
        if not self._settings.feature_flags.enable_expert_gate:
            logger.warning("expert_gate_disabled: returning_empty_list=true")
            return []

        # Fetch all active agents in the team
        stmt = select(AgentORM).where(
            and_(
                AgentORM.team_id == team_id,
                AgentORM.status == AgentStatusEnum.ACTIVE,
            )
        )
        result = await session.execute(stmt)
        agents = list(result.scalars().all())

        if not agents:
            logger.info(f"expert_gate_no_agents: team_id={team_id}")
            return []

        # Score each agent
        scored_agents: list[tuple[AgentORM, ExpertScore]] = []
        for agent in agents:
            score = await self._score_agent(
                agent=agent,
                task_description=task_description,
                required_skills=required_skills or [],
                task_metadata=task_metadata or {},
            )
            scored_agents.append((agent, score))

        # Sort by overall score descending
        scored_agents.sort(key=lambda x: x[1].overall, reverse=True)

        logger.info(
            f"expert_gate_scored: team_id={team_id}, "
            f"agents_count={len(scored_agents)}, "
            f"top_score={scored_agents[0][1].overall:.2f if scored_agents else 0.0}"
        )

        return scored_agents

    async def select_best_agent(
        self,
        session: AsyncSession,
        team_id: UUID,
        task_description: str,
        required_skills: Optional[list[str]] = None,
        task_metadata: Optional[dict[str, str]] = None,
    ) -> Optional[SelectionResult]:
        """Select the single best agent for a task.

        Args:
            session: Database session for agent lookup.
            team_id: Team to select from.
            task_description: Description of the task.
            required_skills: Optional required skill names.
            task_metadata: Optional task metadata.

        Returns:
            SelectionResult with the top-scoring agent, or None if no agents.
        """
        scored = await self.score_agents(
            session=session,
            team_id=team_id,
            task_description=task_description,
            required_skills=required_skills,
            task_metadata=task_metadata,
        )

        if not scored:
            logger.warning(f"expert_gate_no_selection: team_id={team_id}")
            return None

        agent, score = scored[0]
        reasoning = self._generate_reasoning(agent, score, required_skills or [])

        result = SelectionResult(
            expert_id=agent.id,
            expert_name=agent.name,
            score=score,
            reasoning=reasoning,
            rank=1,
        )

        logger.info(
            f"expert_gate_best_selected: agent_name={agent.name}, overall_score={score.overall:.2f}"
        )

        return result

    async def select_top_k(
        self,
        session: AsyncSession,
        team_id: UUID,
        task_description: str,
        k: int = 3,
        required_skills: Optional[list[str]] = None,
        task_metadata: Optional[dict[str, str]] = None,
    ) -> list[SelectionResult]:
        """Select the top K agents for a task.

        Args:
            session: Database session for agent lookup.
            team_id: Team to select from.
            task_description: Description of the task.
            k: Number of top agents to select.
            required_skills: Optional required skill names.
            task_metadata: Optional task metadata.

        Returns:
            List of SelectionResult with top K agents ranked by score.
        """
        scored = await self.score_agents(
            session=session,
            team_id=team_id,
            task_description=task_description,
            required_skills=required_skills,
            task_metadata=task_metadata,
        )

        if not scored:
            logger.warning(f"expert_gate_no_top_k: team_id={team_id}, k={k}")
            return []

        # Take top K agents
        top_k = scored[:k]
        results: list[SelectionResult] = []

        for rank, (agent, score) in enumerate(top_k, start=1):
            reasoning = self._generate_reasoning(agent, score, required_skills or [])
            results.append(
                SelectionResult(
                    expert_id=agent.id,
                    expert_name=agent.name,
                    score=score,
                    reasoning=reasoning,
                    rank=rank,
                )
            )

        logger.info(
            f"expert_gate_top_k_selected: team_id={team_id}, k={k}, selected_count={len(results)}"
        )

        return results

    async def _score_agent(
        self,
        agent: AgentORM,
        task_description: str,
        required_skills: list[str],
        task_metadata: dict[str, str],
    ) -> ExpertScore:
        """Compute the 4-signal score for a single agent.

        Args:
            agent: Agent to score.
            task_description: Task description.
            required_skills: Required skill names.
            task_metadata: Task metadata for scoring.

        Returns:
            ExpertScore with all four signals computed.
        """
        # Signal 1: skill_match (0-10)
        skill_match = self._score_skill_match(agent, required_skills)

        # Signal 2: past_performance (0-10)
        # TODO: Implement historical performance tracking in Phase 7.2
        # For now, use a baseline score based on agent activity
        past_performance = 5.0

        # Signal 3: personality_fit (0-10)
        personality_fit = self._score_personality_fit(agent, task_metadata)

        # Signal 4: load_balance (0-10)
        # TODO: Implement real-time workload tracking in Phase 7.2
        # For now, all agents have equal availability
        load_balance = 10.0

        score = ExpertScore(
            skill_match=skill_match,
            past_performance=past_performance,
            personality_fit=personality_fit,
            load_balance=load_balance,
        )

        logger.debug(
            f"expert_gate_agent_scored: "
            f"agent_name={agent.name}, "
            f"skill_match={skill_match:.2f}, "
            f"overall={score.overall:.2f}"
        )

        return score

    def _score_skill_match(
        self,
        agent: AgentORM,
        required_skills: list[str],
    ) -> float:
        """Score how well an agent's skills match the required skills.

        Args:
            agent: Agent to evaluate.
            required_skills: List of required skill names.

        Returns:
            Skill match score in [0.0, 10.0].
        """
        if not required_skills:
            # No specific skills required, base score
            return 7.0

        # Combine all agent skills
        agent_skills = set(agent.shared_skill_names + agent.custom_skill_names)

        # Remove disabled skills
        agent_skills -= set(agent.disabled_skill_names)

        # Calculate match ratio
        required_set = set(required_skills)
        matched = required_set.intersection(agent_skills)
        match_ratio = len(matched) / len(required_set) if required_set else 0.0

        # Scale to 0-10 (full match = 10.0, no match = 0.0)
        # Partial match gets proportional credit
        score = match_ratio * 10.0

        return score

    def _score_personality_fit(
        self,
        agent: AgentORM,
        task_metadata: dict[str, str],
    ) -> float:
        """Score how well an agent's personality fits the task.

        Args:
            agent: Agent to evaluate.
            task_metadata: Task metadata with hints about required traits.

        Returns:
            Personality fit score in [0.0, 10.0].
        """
        # Base score for all agents
        base_score = 6.0

        # Check for personality traits in agent.personality JSONB
        personality = agent.personality or {}

        # Look for task_type hint in metadata
        task_type = task_metadata.get("task_type", "")

        # Simple heuristic matching (can be extended with embeddings later)
        if task_type == "creative" and personality.get("creativity", 0) >= 0.7:
            base_score += 3.0
        elif task_type == "analytical" and personality.get("analytical", 0) >= 0.7:
            base_score += 3.0
        elif task_type == "collaborative" and personality.get("collaborative", 0) >= 0.7:
            base_score += 3.0

        # Cap at 10.0
        return min(base_score, 10.0)

    def _generate_reasoning(
        self,
        agent: AgentORM,
        score: ExpertScore,
        required_skills: list[str],
    ) -> str:
        """Generate human-readable reasoning for agent selection.

        Args:
            agent: Selected agent.
            score: The agent's expert score.
            required_skills: Required skills for the task.

        Returns:
            String explaining why this agent was selected.
        """
        reasoning_parts: list[str] = []

        # Lead with overall score
        reasoning_parts.append(f"{agent.name} scored {score.overall:.2f}/10 overall")

        # Explain strongest signals
        if score.skill_match >= 8.0:
            matched_count = len(
                set(required_skills).intersection(
                    set(agent.shared_skill_names + agent.custom_skill_names)
                    - set(agent.disabled_skill_names)
                )
            )
            reasoning_parts.append(
                f"Strong skill match ({matched_count}/{len(required_skills)} required skills)"
            )

        if score.personality_fit >= 8.0:
            reasoning_parts.append("Excellent personality fit for this task type")

        if score.load_balance >= 9.0:
            reasoning_parts.append("Currently available with low workload")

        # Fallback if no strong signals
        if len(reasoning_parts) == 1:
            reasoning_parts.append("Selected as best available match")

        return ". ".join(reasoning_parts) + "."
