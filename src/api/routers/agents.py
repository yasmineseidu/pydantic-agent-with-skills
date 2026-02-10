"""Agent CRUD endpoints for multi-tenant agent management."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.schemas.agents import AgentCreate, AgentResponse, AgentUpdate
from src.api.schemas.common import PaginatedResponse
from src.auth.dependencies import get_current_user, require_role
from src.db.models.agent import AgentORM
from src.db.models.user import UserORM

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/agents", response_model=PaginatedResponse[AgentResponse])
async def list_agents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AgentResponse]:
    """
    List all agents for the current team with pagination.

    All users in the team can list agents. Results are scoped to the team_id
    from the authenticated user's context (JWT or API key).

    Args:
        limit: Max items per page (1-100, default 20)
        offset: Number of items to skip (default 0)
        status_filter: Optional filter by agent status (draft/active/paused/archived)
        current_user: Authenticated user and team_id from get_current_user dependency
        db: Async database session

    Returns:
        Paginated list of agents belonging to the current team

    Raises:
        HTTPException: 401 if team_id not available in auth context
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"list_agents_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Build base query scoped to team
    base_query = select(AgentORM).where(AgentORM.team_id == team_id)

    # Apply status filter if provided
    if status_filter:
        base_query = base_query.where(AgentORM.status == status_filter)

    # Count total items
    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Fetch paginated items (ordered by created_at desc for newest first)
    paginated_query = base_query.order_by(AgentORM.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(paginated_query)
    agents = result.scalars().all()

    # Map ORM to response schema
    items = [
        AgentResponse(
            id=agent.id,
            team_id=agent.team_id,
            name=agent.name,
            slug=agent.slug,
            tagline=agent.tagline,
            avatar_emoji=agent.avatar_emoji,
            personality=agent.personality,
            shared_skill_names=agent.shared_skill_names,
            custom_skill_names=agent.custom_skill_names,
            disabled_skill_names=agent.disabled_skill_names,
            model_config_data=agent.model_config_json,
            memory_config=agent.memory_config,
            boundaries=agent.boundaries,
            status=agent.status,
            created_by=agent.created_by,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
        for agent in agents
    ]

    has_more = (offset + limit) < total

    logger.info(
        f"list_agents_success: user_id={user.id}, team_id={team_id}, "
        f"total={total}, returned={len(items)}, limit={limit}, offset={offset}"
    )

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post("/v1/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """
    Create a new agent in the current team (admin+ only).

    Only admins and owners can create agents. The agent is scoped to the team_id
    from the authenticated user's context.

    Args:
        data: Agent creation data (name, slug, personality, model config, etc.)
        current_user: Authenticated user and team_id from require_role("admin") dependency
        db: Async database session

    Returns:
        Created agent details

    Raises:
        HTTPException: 401 if team_id not available
        HTTPException: 409 if slug already exists in the team
        HTTPException: 422 if validation fails
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"create_agent_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Check if slug already exists in this team
    existing_stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == data.slug)
    existing_result = await db.execute(existing_stmt)
    existing_agent = existing_result.scalar_one_or_none()

    if existing_agent:
        logger.warning(
            f"create_agent_error: user_id={user.id}, team_id={team_id}, "
            f"slug={data.slug}, reason=duplicate_slug"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with slug '{data.slug}' already exists in this team",
        )

    # Map AgentCreate schema → AgentORM
    agent = AgentORM(
        team_id=team_id,
        name=data.name,
        slug=data.slug,
        tagline=data.tagline,
        avatar_emoji=data.avatar_emoji,
        personality=data.personality or {},
        shared_skill_names=data.shared_skill_names,
        custom_skill_names=data.custom_skill_names,
        model_config_json=data.model_config_data or {},
        memory_config=data.memory_config or {},
        boundaries=data.boundaries or {},
        status="draft",  # New agents start as draft
        created_by=user.id,
    )

    db.add(agent)

    try:
        await db.commit()
        await db.refresh(agent)
        logger.info(
            f"create_agent_success: user_id={user.id}, team_id={team_id}, "
            f"agent_id={agent.id}, slug={agent.slug}"
        )
    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            f"create_agent_integrity_error: user_id={user.id}, team_id={team_id}, "
            f"slug={data.slug}, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent with this slug already exists in the team",
        ) from e

    return AgentResponse(
        id=agent.id,
        team_id=agent.team_id,
        name=agent.name,
        slug=agent.slug,
        tagline=agent.tagline,
        avatar_emoji=agent.avatar_emoji,
        personality=agent.personality,
        shared_skill_names=agent.shared_skill_names,
        custom_skill_names=agent.custom_skill_names,
        disabled_skill_names=agent.disabled_skill_names,
        model_config_data=agent.model_config_json,
        memory_config=agent.memory_config,
        boundaries=agent.boundaries,
        status=agent.status,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.get("/v1/agents/{slug}", response_model=AgentResponse)
async def get_agent(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """
    Get an agent by slug within the current team.

    All users in the team can view agents. Slug is unique within a team,
    not globally.

    Args:
        slug: Agent slug (URL-safe identifier)
        current_user: Authenticated user and team_id from get_current_user dependency
        db: Async database session

    Returns:
        Agent details

    Raises:
        HTTPException: 401 if team_id not available
        HTTPException: 404 if agent not found in the team
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"get_agent_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Query agent by slug + team_id
    stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == slug)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        logger.warning(
            f"get_agent_error: user_id={user.id}, team_id={team_id}, slug={slug}, reason=not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with slug '{slug}' not found in this team",
        )

    logger.info(
        f"get_agent_success: user_id={user.id}, team_id={team_id}, agent_id={agent.id}, slug={slug}"
    )

    return AgentResponse(
        id=agent.id,
        team_id=agent.team_id,
        name=agent.name,
        slug=agent.slug,
        tagline=agent.tagline,
        avatar_emoji=agent.avatar_emoji,
        personality=agent.personality,
        shared_skill_names=agent.shared_skill_names,
        custom_skill_names=agent.custom_skill_names,
        disabled_skill_names=agent.disabled_skill_names,
        model_config_data=agent.model_config_json,
        memory_config=agent.memory_config,
        boundaries=agent.boundaries,
        status=agent.status,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.patch("/v1/agents/{slug}", response_model=AgentResponse)
async def update_agent(
    slug: str,
    data: AgentUpdate,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """
    Partially update an agent by slug (admin+ only).

    Only admins and owners can update agents. All fields in AgentUpdate
    are optional - only provided fields will be updated.

    Args:
        slug: Agent slug (URL-safe identifier)
        data: Partial agent update data (all fields optional)
        current_user: Authenticated user and team_id from require_role("admin") dependency
        db: Async database session

    Returns:
        Updated agent details

    Raises:
        HTTPException: 401 if team_id not available
        HTTPException: 404 if agent not found in the team
        HTTPException: 422 if validation fails
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"update_agent_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Query agent by slug + team_id
    stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == slug)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        logger.warning(
            f"update_agent_error: user_id={user.id}, team_id={team_id}, "
            f"slug={slug}, reason=not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with slug '{slug}' not found in this team",
        )

    # Apply partial updates (only update fields that are not None)
    update_data = data.model_dump(exclude_unset=True)
    updated_fields = []

    for field, value in update_data.items():
        # Map schema field names to ORM field names
        if field == "model_config_data":
            setattr(agent, "model_config_json", value)
            updated_fields.append("model_config_json")
        else:
            setattr(agent, field, value)
            updated_fields.append(field)

    try:
        await db.commit()
        await db.refresh(agent)
        logger.info(
            f"update_agent_success: user_id={user.id}, team_id={team_id}, "
            f"agent_id={agent.id}, slug={slug}, updated_fields={updated_fields}"
        )
    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            f"update_agent_integrity_error: user_id={user.id}, team_id={team_id}, "
            f"slug={slug}, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update violates database constraints",
        ) from e

    return AgentResponse(
        id=agent.id,
        team_id=agent.team_id,
        name=agent.name,
        slug=agent.slug,
        tagline=agent.tagline,
        avatar_emoji=agent.avatar_emoji,
        personality=agent.personality,
        shared_skill_names=agent.shared_skill_names,
        custom_skill_names=agent.custom_skill_names,
        disabled_skill_names=agent.disabled_skill_names,
        model_config_data=agent.model_config_json,
        memory_config=agent.memory_config,
        boundaries=agent.boundaries,
        status=agent.status,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.delete("/v1/agents/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft delete an agent by setting status to 'archived' (admin+ only).

    Only admins and owners can delete agents. This is a soft delete -
    the agent record remains in the database but is set to 'archived' status.

    Args:
        slug: Agent slug (URL-safe identifier)
        current_user: Authenticated user and team_id from require_role("admin") dependency
        db: Async database session

    Returns:
        None (204 No Content on success)

    Raises:
        HTTPException: 401 if team_id not available
        HTTPException: 404 if agent not found in the team
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"delete_agent_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Query agent by slug + team_id
    stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == slug)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        logger.warning(
            f"delete_agent_error: user_id={user.id}, team_id={team_id}, "
            f"slug={slug}, reason=not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with slug '{slug}' not found in this team",
        )

    # Soft delete: set status to archived
    agent.status = "archived"

    await db.commit()

    logger.info(
        f"delete_agent_success: user_id={user.id}, team_id={team_id}, "
        f"agent_id={agent.id}, slug={slug}, action=soft_delete_to_archived"
    )
