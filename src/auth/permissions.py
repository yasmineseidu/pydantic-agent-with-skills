"""Team-scoped RBAC permission checks."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.user import TeamMembershipORM, UserRole

logger = logging.getLogger(__name__)

# Role hierarchy: higher values mean more permissions
ROLE_HIERARCHY: dict[str, int] = {
    UserRole.OWNER.value: 4,
    UserRole.ADMIN.value: 3,
    UserRole.MEMBER.value: 2,
    UserRole.VIEWER.value: 1,
}


async def get_user_team_role(
    session: AsyncSession,
    user_id: UUID,
    team_id: UUID,
) -> Optional[str]:
    """Get the user's role in a specific team.

    Args:
        session: Async SQLAlchemy session for database operations.
        user_id: UUID of the user.
        team_id: UUID of the team.

    Returns:
        Role string (owner/admin/member/viewer) if user is a member, None otherwise.
    """
    stmt = select(TeamMembershipORM.role).where(
        TeamMembershipORM.user_id == user_id,
        TeamMembershipORM.team_id == team_id,
    )
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()

    if role:
        logger.info(f"get_user_team_role: user_id={user_id}, team_id={team_id}, role={role}")
    else:
        logger.info(
            f"get_user_team_role_not_found: user_id={user_id}, team_id={team_id}, role=None"
        )

    return role


async def check_team_permission(
    session: AsyncSession,
    user_id: UUID,
    team_id: UUID,
    required_role: str,
) -> bool:
    """Check if user has required permission level in a team.

    Uses role hierarchy: higher roles inherit permissions from lower roles.
    OWNER (4) > ADMIN (3) > MEMBER (2) > VIEWER (1).

    Args:
        session: Async SQLAlchemy session for database operations.
        user_id: UUID of the user.
        team_id: UUID of the team.
        required_role: Minimum role required (owner/admin/member/viewer).

    Returns:
        True if user has required permission level or higher, False otherwise.
    """
    user_role = await get_user_team_role(session, user_id, team_id)

    if user_role is None:
        logger.warning(
            f"check_team_permission_denied: user_id={user_id}, team_id={team_id}, "
            f"required_role={required_role}, reason=not_member"
        )
        return False

    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)

    has_permission = user_level >= required_level

    if has_permission:
        logger.info(
            f"check_team_permission_granted: user_id={user_id}, team_id={team_id}, "
            f"user_role={user_role}, required_role={required_role}"
        )
    else:
        logger.warning(
            f"check_team_permission_denied: user_id={user_id}, team_id={team_id}, "
            f"user_role={user_role}, required_role={required_role}, "
            f"reason=insufficient_level"
        )

    return has_permission


async def get_user_teams(
    session: AsyncSession,
    user_id: UUID,
) -> list[tuple[UUID, str]]:
    """Get all teams a user belongs to with their roles.

    Args:
        session: Async SQLAlchemy session for database operations.
        user_id: UUID of the user.

    Returns:
        List of (team_id, role) tuples for all teams the user is a member of.
        Returns empty list if user has no team memberships.
    """
    stmt = select(TeamMembershipORM.team_id, TeamMembershipORM.role).where(
        TeamMembershipORM.user_id == user_id
    )
    result = await session.execute(stmt)
    teams = [(row[0], row[1]) for row in result.all()]

    logger.info(f"get_user_teams: user_id={user_id}, team_count={len(teams)}")

    return teams
