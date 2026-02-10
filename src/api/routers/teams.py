"""Team CRUD and membership management endpoints."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.schemas.teams import (
    MemberAdd,
    MemberResponse,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
    UsageSummary,
)
from src.auth.dependencies import get_current_user
from src.auth.permissions import check_team_permission, get_user_team_role
from src.db.models.tracking import UsageLogORM
from src.db.models.user import TeamMembershipORM, TeamORM, UserORM, UserRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/teams", response_model=list[TeamResponse])
async def list_teams(
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamResponse]:
    """
    List all teams the authenticated user is a member of.

    Returns teams with full details including settings and shared skills.
    Ordered by team creation date (newest first).

    Args:
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        List of TeamResponse objects for all teams the user belongs to.

    Example:
        >>> GET /v1/teams
        >>> Authorization: Bearer <jwt>
        >>> [
        >>>   {
        >>>     "id": "...",
        >>>     "name": "My Team",
        >>>     "slug": "my-team",
        >>>     "owner_id": "...",
        >>>     "settings": {},
        >>>     "shared_skill_names": [],
        >>>     "created_at": "2026-02-10T...",
        >>>     "updated_at": "2026-02-10T..."
        >>>   }
        >>> ]
    """
    user, _ = current_user

    # Query teams via TeamMembershipORM join
    stmt = (
        select(TeamORM)
        .join(TeamMembershipORM, TeamMembershipORM.team_id == TeamORM.id)
        .where(TeamMembershipORM.user_id == user.id)
        .order_by(TeamORM.created_at.desc())
    )

    result = await db.execute(stmt)
    teams = result.scalars().all()

    logger.info(f"list_teams_success: user_id={user.id}, team_count={len(teams)}")

    return [
        TeamResponse(
            id=team.id,
            name=team.name,
            slug=team.slug,
            owner_id=team.owner_id,
            settings=team.settings,
            shared_skill_names=team.shared_skill_names,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )
        for team in teams
    ]


@router.post("/v1/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """
    Create a new team with the authenticated user as owner.

    Creates TeamORM record and TeamMembershipORM record with role='owner'.
    Team slug must be globally unique (enforced by database constraint).

    Args:
        team_data: TeamCreate schema with name and slug.
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        TeamResponse with created team details.

    Raises:
        HTTPException: 409 if team slug already exists.
        HTTPException: 500 if database operation fails.

    Example:
        >>> POST /v1/teams
        >>> Authorization: Bearer <jwt>
        >>> {"name": "My Team", "slug": "my-team"}
        >>> Response: 201 Created with TeamResponse
    """
    user, _ = current_user

    # Create team record
    team = TeamORM(
        name=team_data.name,
        slug=team_data.slug,
        owner_id=user.id,
        settings={},
        shared_skill_names=[],
    )

    try:
        db.add(team)
        await db.flush()  # Get team.id before creating membership

        # Create owner membership
        membership = TeamMembershipORM(
            user_id=user.id,
            team_id=team.id,
            role=UserRole.OWNER.value,
        )
        db.add(membership)

        await db.commit()
        await db.refresh(team)

        logger.info(
            f"create_team_success: user_id={user.id}, team_id={team.id}, "
            f"slug={team.slug}, name={team.name}"
        )

        return TeamResponse(
            id=team.id,
            name=team.name,
            slug=team.slug,
            owner_id=team.owner_id,
            settings=team.settings,
            shared_skill_names=team.shared_skill_names,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )

    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            f"create_team_error: user_id={user.id}, slug={team_data.slug}, "
            f"reason=duplicate_slug, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team slug '{team_data.slug}' already exists",
        ) from e
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"create_team_error: user_id={user.id}, slug={team_data.slug}, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team",
        ) from e


@router.get("/v1/teams/{slug}", response_model=TeamResponse)
async def get_team(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """
    Get team details by slug.

    User must be a member of the team to view it (any role).

    Args:
        slug: Team slug (URL-safe identifier).
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        TeamResponse with team details.

    Raises:
        HTTPException: 404 if team not found.
        HTTPException: 403 if user is not a member.

    Example:
        >>> GET /v1/teams/my-team
        >>> Authorization: Bearer <jwt>
        >>> Response: TeamResponse
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(f"get_team_error: user_id={user.id}, slug={slug}, reason=not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user is a member
    user_role = await get_user_team_role(db, user.id, team.id)
    if user_role is None:
        logger.warning(
            f"get_team_error: user_id={user.id}, team_id={team.id}, slug={slug}, reason=not_member"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )

    logger.info(f"get_team_success: user_id={user.id}, team_id={team.id}, slug={slug}")

    return TeamResponse(
        id=team.id,
        name=team.name,
        slug=team.slug,
        owner_id=team.owner_id,
        settings=team.settings,
        shared_skill_names=team.shared_skill_names,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.patch("/v1/teams/{slug}", response_model=TeamResponse)
async def update_team(
    slug: str,
    team_data: TeamUpdate,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamResponse:
    """
    Update team settings (owner only).

    Only team owners can update team settings. Supports partial updates
    (only provided fields are updated).

    Args:
        slug: Team slug (URL-safe identifier).
        team_data: TeamUpdate schema with optional fields to update.
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        TeamResponse with updated team details.

    Raises:
        HTTPException: 404 if team not found.
        HTTPException: 403 if user is not the team owner.

    Example:
        >>> PATCH /v1/teams/my-team
        >>> Authorization: Bearer <jwt>
        >>> {"name": "Updated Name", "settings": {"max_tokens": 8000}}
        >>> Response: TeamResponse with updated fields
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(f"update_team_error: user_id={user.id}, slug={slug}, reason=not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user is owner
    has_permission = await check_team_permission(db, user.id, team.id, UserRole.OWNER.value)
    if not has_permission:
        logger.warning(
            f"update_team_error: user_id={user.id}, team_id={team.id}, "
            f"slug={slug}, reason=not_owner"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owner can update team settings",
        )

    # Update fields (partial update)
    if team_data.name is not None:
        team.name = team_data.name
    if team_data.settings is not None:
        team.settings = team_data.settings
    if team_data.shared_skill_names is not None:
        team.shared_skill_names = team_data.shared_skill_names

    team.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
        await db.refresh(team)

        logger.info(
            f"update_team_success: user_id={user.id}, team_id={team.id}, slug={slug}, "
            f"updated_fields={list(team_data.model_dump(exclude_unset=True).keys())}"
        )

        return TeamResponse(
            id=team.id,
            name=team.name,
            slug=team.slug,
            owner_id=team.owner_id,
            settings=team.settings,
            shared_skill_names=team.shared_skill_names,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )

    except Exception as e:
        await db.rollback()
        logger.exception(
            f"update_team_error: user_id={user.id}, team_id={team.id}, slug={slug}, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team",
        ) from e


@router.get("/v1/teams/{slug}/members", response_model=list[MemberResponse])
async def list_members(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    """
    List all members of a team.

    User must be a member of the team to view members (any role).

    Args:
        slug: Team slug (URL-safe identifier).
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        List of MemberResponse objects for all team members.

    Raises:
        HTTPException: 404 if team not found.
        HTTPException: 403 if user is not a member.

    Example:
        >>> GET /v1/teams/my-team/members
        >>> Authorization: Bearer <jwt>
        >>> Response: [MemberResponse, ...]
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(f"list_members_error: user_id={user.id}, slug={slug}, reason=not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user is a member
    user_role = await get_user_team_role(db, user.id, team.id)
    if user_role is None:
        logger.warning(
            f"list_members_error: user_id={user.id}, team_id={team.id}, "
            f"slug={slug}, reason=not_member"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )

    # Query all members with user details
    member_stmt = (
        select(TeamMembershipORM, UserORM)
        .join(UserORM, UserORM.id == TeamMembershipORM.user_id)
        .where(TeamMembershipORM.team_id == team.id)
        .order_by(TeamMembershipORM.created_at.asc())
    )

    result = await db.execute(member_stmt)
    rows = result.all()

    logger.info(
        f"list_members_success: user_id={user.id}, team_id={team.id}, "
        f"slug={slug}, member_count={len(rows)}"
    )

    return [
        MemberResponse(
            user_id=membership.user_id,
            team_id=membership.team_id,
            role=membership.role,
            display_name=member_user.display_name,
            email=member_user.email,
            created_at=membership.created_at,
        )
        for membership, member_user in rows
    ]


@router.post(
    "/v1/teams/{slug}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    slug: str,
    member_data: MemberAdd,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """
    Add a new member to a team (admin+ only).

    Requires admin or owner role to add members. Looks up user by email.

    Args:
        slug: Team slug (URL-safe identifier).
        member_data: MemberAdd schema with email and role.
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        MemberResponse with added member details.

    Raises:
        HTTPException: 404 if team or user not found.
        HTTPException: 403 if user lacks admin permission.
        HTTPException: 409 if user is already a member.

    Example:
        >>> POST /v1/teams/my-team/members
        >>> Authorization: Bearer <jwt>
        >>> {"email": "newuser@example.com", "role": "member"}
        >>> Response: 201 Created with MemberResponse
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(f"add_member_error: user_id={user.id}, slug={slug}, reason=team_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user has admin or owner role
    has_permission = await check_team_permission(db, user.id, team.id, UserRole.ADMIN.value)
    if not has_permission:
        logger.warning(
            f"add_member_error: user_id={user.id}, team_id={team.id}, "
            f"slug={slug}, reason=insufficient_permissions"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and owners can add members",
        )

    # Look up user by email
    user_stmt = select(UserORM).where(UserORM.email == member_data.email)
    user_result = await db.execute(user_stmt)
    new_member: Optional[UserORM] = user_result.scalar_one_or_none()

    if not new_member:
        logger.warning(
            f"add_member_error: user_id={user.id}, team_id={team.id}, "
            f"email={member_data.email}, reason=user_not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{member_data.email}' not found",
        )

    # Create membership
    membership = TeamMembershipORM(
        user_id=new_member.id,
        team_id=team.id,
        role=member_data.role,
    )

    try:
        db.add(membership)
        await db.commit()
        await db.refresh(membership)

        logger.info(
            f"add_member_success: user_id={user.id}, team_id={team.id}, "
            f"new_member_id={new_member.id}, role={member_data.role}"
        )

        return MemberResponse(
            user_id=membership.user_id,
            team_id=membership.team_id,
            role=membership.role,
            display_name=new_member.display_name,
            email=new_member.email,
            created_at=membership.created_at,
        )

    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            f"add_member_error: user_id={user.id}, team_id={team.id}, "
            f"new_member_id={new_member.id}, reason=already_member, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{member_data.email}' is already a member of this team",
        ) from e
    except Exception as e:
        await db.rollback()
        logger.exception(f"add_member_error: user_id={user.id}, team_id={team.id}, error={str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add member",
        ) from e


@router.delete("/v1/teams/{slug}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    slug: str,
    member_user_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a member from a team (admin+ only).

    Requires admin or owner role to remove members. CANNOT remove owner.

    Args:
        slug: Team slug (URL-safe identifier).
        member_user_id: UUID of the user to remove.
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        None (204 No Content).

    Raises:
        HTTPException: 404 if team or membership not found.
        HTTPException: 403 if user lacks admin permission.
        HTTPException: 400 if attempting to remove owner.

    Example:
        >>> DELETE /v1/teams/my-team/members/123e4567-...
        >>> Authorization: Bearer <jwt>
        >>> Response: 204 No Content
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(
            f"remove_member_error: user_id={user.id}, slug={slug}, reason=team_not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user has admin or owner role
    has_permission = await check_team_permission(db, user.id, team.id, UserRole.ADMIN.value)
    if not has_permission:
        logger.warning(
            f"remove_member_error: user_id={user.id}, team_id={team.id}, "
            f"slug={slug}, reason=insufficient_permissions"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and owners can remove members",
        )

    # Look up membership
    membership_stmt = select(TeamMembershipORM).where(
        TeamMembershipORM.team_id == team.id,
        TeamMembershipORM.user_id == member_user_id,
    )
    membership_result = await db.execute(membership_stmt)
    membership: Optional[TeamMembershipORM] = membership_result.scalar_one_or_none()

    if not membership:
        logger.warning(
            f"remove_member_error: user_id={user.id}, team_id={team.id}, "
            f"member_user_id={member_user_id}, reason=membership_not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this team",
        )

    # CANNOT remove owner
    if membership.role == UserRole.OWNER.value:
        logger.warning(
            f"remove_member_error: user_id={user.id}, team_id={team.id}, "
            f"member_user_id={member_user_id}, reason=cannot_remove_owner"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove team owner from team",
        )

    try:
        await db.delete(membership)
        await db.commit()

        logger.info(
            f"remove_member_success: user_id={user.id}, team_id={team.id}, "
            f"removed_user_id={member_user_id}"
        )

    except Exception as e:
        await db.rollback()
        logger.exception(
            f"remove_member_error: user_id={user.id}, team_id={team.id}, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove member",
        ) from e


@router.get("/v1/teams/{slug}/usage", response_model=UsageSummary)
async def get_usage(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSummary:
    """
    Get aggregated usage statistics for a team.

    Aggregates token counts and costs from UsageLogORM for the team.
    User must be a member of the team (any role).

    Args:
        slug: Team slug (URL-safe identifier).
        current_user: Authenticated user from get_current_user dependency.
        db: Async database session from get_db dependency.

    Returns:
        UsageSummary with aggregated token counts, costs, and request count.

    Raises:
        HTTPException: 404 if team not found.
        HTTPException: 403 if user is not a member.

    Example:
        >>> GET /v1/teams/my-team/usage
        >>> Authorization: Bearer <jwt>
        >>> Response: UsageSummary with total_input_tokens, total_output_tokens, etc.
    """
    user, _ = current_user

    # Look up team by slug
    stmt = select(TeamORM).where(TeamORM.slug == slug)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if not team:
        logger.warning(f"get_usage_error: user_id={user.id}, slug={slug}, reason=not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{slug}' not found",
        )

    # Check if user is a member
    user_role = await get_user_team_role(db, user.id, team.id)
    if user_role is None:
        logger.warning(
            f"get_usage_error: user_id={user.id}, team_id={team.id}, slug={slug}, reason=not_member"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team",
        )

    # Aggregate usage from UsageLogORM
    stats_stmt = select(
        func.coalesce(func.sum(UsageLogORM.input_tokens), 0).label("total_input"),
        func.coalesce(func.sum(UsageLogORM.output_tokens), 0).label("total_output"),
        func.coalesce(func.sum(UsageLogORM.embedding_tokens), 0).label("total_embedding"),
        func.coalesce(func.sum(UsageLogORM.estimated_cost_usd), Decimal("0")).label("total_cost"),
        func.count(UsageLogORM.id).label("request_count"),
        func.min(UsageLogORM.created_at).label("period_start"),
        func.max(UsageLogORM.created_at).label("period_end"),
    ).where(UsageLogORM.team_id == team.id)

    result = await db.execute(stats_stmt)
    row = result.one()

    # Handle case where no usage logs exist
    now = datetime.now(timezone.utc)
    period_start = row.period_start if row.period_start else team.created_at
    period_end = row.period_end if row.period_end else now

    logger.info(
        f"get_usage_success: user_id={user.id}, team_id={team.id}, slug={slug}, "
        f"request_count={row.request_count}, total_cost_usd={float(row.total_cost)}"
    )

    return UsageSummary(
        team_id=team.id,
        total_input_tokens=int(row.total_input),
        total_output_tokens=int(row.total_output),
        total_embedding_tokens=int(row.total_embedding),
        estimated_cost_usd=float(row.total_cost),
        request_count=int(row.request_count),
        period_start=period_start,
        period_end=period_end,
    )
