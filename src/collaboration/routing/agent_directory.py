"""Agent directory service for querying agent profiles and availability."""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from src.collaboration.models import AgentAvailability, AgentProfile
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.user import TeamMembershipORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentDirectory:
    """Directory service for querying agent profiles and availability.

    Provides methods to list available agents, get agent profiles, check
    availability status, filter by skills, and extract personality traits.
    All database operations are async.

    Args:
        session: AsyncSession for database queries.
    """

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize the agent directory.

        Args:
            session: AsyncSession for database operations.
        """
        self._session = session

    async def get_available_agents(self, team_id: UUID) -> list[AgentORM]:
        """List all ACTIVE agents in a team.

        Args:
            team_id: UUID of the team to query.

        Returns:
            List of AgentORM instances with status=ACTIVE.
        """
        stmt = select(AgentORM).where(
            AgentORM.team_id == team_id,
            AgentORM.status == AgentStatusEnum.ACTIVE,
        )
        result = await self._session.execute(stmt)
        agents = list(result.scalars().all())

        logger.info(f"agents_fetched: count={len(agents)}, team_id={team_id}")
        return agents

    async def list_agents(self, user_id: UUID) -> list[AgentProfile]:
        """List active agent profiles across teams the user belongs to.

        Args:
            user_id: UUID of the user whose team agents should be listed.

        Returns:
            List of AgentProfile for all active agents in the user's teams.
        """
        stmt = (
            select(AgentORM)
            .join(TeamMembershipORM, TeamMembershipORM.team_id == AgentORM.team_id)
            .where(
                TeamMembershipORM.user_id == user_id,
                AgentORM.status == AgentStatusEnum.ACTIVE,
            )
        )
        result = await self._session.execute(stmt)
        agents = list(result.scalars().all())

        profiles: list[AgentProfile] = []
        for agent in agents:
            profiles.append(await self.get_agent_profile(agent))

        logger.info(f"list_agents: user_id={user_id}, count={len(profiles)}")
        return profiles

    async def get_agent_profile(self, agent: AgentORM) -> AgentProfile:
        """Convert AgentORM to AgentProfile Pydantic model.

        Extracts capabilities from shared and custom skills, specializations
        from custom skills, personality summary from personality JSON, and
        uses a default average response time.

        Args:
            agent: AgentORM instance to convert.

        Returns:
            AgentProfile with agent capabilities and metadata.
        """
        # Combine shared and custom skills as capabilities
        capabilities = list(agent.shared_skill_names) + list(agent.custom_skill_names)

        # Use custom skills as specializations (more specific than shared)
        specializations = list(agent.custom_skill_names)

        # Extract personality summary (use tagline or personality traits)
        personality_dict = self.get_personality_traits(agent)
        personality_summary = agent.tagline or personality_dict.get("summary", "")

        # Default average response time (placeholder - would be from metrics in prod)
        average_response_time = 5.0

        profile = AgentProfile(
            agent_id=agent.id,
            name=agent.name,
            capabilities=capabilities,
            specializations=specializations,
            personality_summary=personality_summary,
            average_response_time=average_response_time,
        )

        logger.info(
            f"agent_profile_created: agent_id={agent.id}, capabilities_count={len(capabilities)}"
        )
        return profile

    async def check_availability(self, agent: AgentORM, current_load: int = 0) -> AgentAvailability:
        """Return AgentAvailability with load and concurrent task limits.

        Args:
            agent: AgentORM instance to check.
            current_load: Number of active tasks currently assigned (default: 0).

        Returns:
            AgentAvailability with is_available, current_load, max_concurrent_tasks.
        """
        # Extract max concurrent tasks from boundaries config
        boundaries = agent.boundaries
        max_concurrent_tasks = boundaries.get("max_tool_calls_per_turn", 10)

        # Agent is available if active and under load limit
        is_available = (
            agent.status == AgentStatusEnum.ACTIVE and current_load < max_concurrent_tasks
        )

        # Estimate wait time: 0 if available, otherwise proportional to overload
        estimated_wait_time = 0.0
        if not is_available:
            estimated_wait_time = float(current_load - max_concurrent_tasks + 1) * 30.0

        availability = AgentAvailability(
            agent_id=agent.id,
            is_available=is_available,
            current_load=current_load,
            max_concurrent_tasks=max_concurrent_tasks,
            estimated_wait_time=estimated_wait_time,
        )

        logger.info(
            f"availability_checked: agent_id={agent.id}, is_available={is_available}, "
            f"load={current_load}/{max_concurrent_tasks}"
        )
        return availability

    async def filter_by_skills(
        self, agents: list[AgentORM], required_skills: list[str]
    ) -> list[AgentORM]:
        """Filter agents by required skills.

        Args:
            agents: List of AgentORM instances to filter.
            required_skills: List of skill names to match.

        Returns:
            List of AgentORM instances that have ALL required skills.
        """
        if not required_skills:
            return agents

        filtered_agents = []
        for agent in agents:
            all_skills = set(agent.shared_skill_names) | set(agent.custom_skill_names)
            required_set = set(required_skills)

            # Agent must have all required skills
            if required_set.issubset(all_skills):
                filtered_agents.append(agent)

        logger.info(
            f"agents_filtered: input_count={len(agents)}, "
            f"output_count={len(filtered_agents)}, "
            f"required_skills={required_skills}"
        )
        return filtered_agents

    def get_personality_traits(self, agent: AgentORM) -> dict:
        """Extract personality dict from agent.

        Args:
            agent: AgentORM instance.

        Returns:
            Personality traits as a dictionary (from agent.personality JSON field).
        """
        return agent.personality or {}
