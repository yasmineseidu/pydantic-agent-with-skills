"""Collaboration endpoints for routing, handoffs, and multi-agent sessions."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_settings
from src.api.schemas.collaboration import (
    CollaborationParticipantsRequest,
    CollaborationRecommendRequest,
    CollaborationRouteRequest,
    CollaborationSessionCreateRequest,
    CollaborationStatusUpdateRequest,
    HandoffRecordResponse,
    HandoffRequest,
)
from src.auth.dependencies import get_current_user
from src.collaboration.coordination.handoff_manager import HandoffManager
from src.collaboration.coordination.multi_agent_manager import MultiAgentManager
from src.collaboration.models import AgentRecommendation, CollaborationSession, HandoffResult, RoutingDecision
from src.collaboration.routing.agent_directory import AgentDirectory
from src.collaboration.routing.agent_router import AgentRouter
from src.db.models.user import UserORM
from src.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/v1/collaboration/route", response_model=RoutingDecision)
async def route_to_agent(
    payload: CollaborationRouteRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RoutingDecision:
    """Route a query to the best agent for the current user."""
    user, _team_id = current_user

    directory = AgentDirectory(db)
    agent_router = AgentRouter(directory, settings)

    return await agent_router.route_to_agent(
        query=payload.query,
        user_id=user.id,
        current_agent_id=payload.current_agent_id,
        conversation_history=payload.conversation_history,
    )


@router.post("/v1/collaboration/recommendations", response_model=list[AgentRecommendation])
async def recommend_agents(
    payload: CollaborationRecommendRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AgentRecommendation]:
    """Recommend multiple agents for collaborative work."""
    user, _team_id = current_user

    directory = AgentDirectory(db)
    agent_router = AgentRouter(directory, settings)

    return await agent_router.suggest_collaboration(
        query=payload.query,
        user_id=user.id,
        min_agents=payload.min_agents,
        max_agents=payload.max_agents,
    )


@router.post("/v1/collaboration/handoff", response_model=HandoffResult)
async def initiate_handoff(
    payload: HandoffRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HandoffResult:
    """Initiate a handoff between agents for a conversation."""
    user, _team_id = current_user

    manager = HandoffManager(db)
    result = await manager.initiate_handoff(
        conversation_id=payload.conversation_id,
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        reason=payload.reason,
        context_transferred=payload.context_transferred,
    )

    if result.success:
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(f"handoff_commit_failed: user_id={user.id}, error={str(exc)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist handoff",
            ) from exc

    return result


@router.get(
    "/v1/collaboration/handoffs/{conversation_id}", response_model=list[HandoffRecordResponse]
)
async def list_handoffs(
    conversation_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HandoffRecordResponse]:
    """List recent handoffs for a conversation."""
    user, _team_id = current_user

    manager = HandoffManager(db)
    records = await manager.get_handoff_history(conversation_id=conversation_id, limit=limit)

    logger.info(
        f"handoff_history_listed: user_id={user.id}, conversation_id={conversation_id}, "
        f"count={len(records)}"
    )

    return [
        HandoffRecordResponse(
            id=record.id,
            conversation_id=record.conversation_id,
            from_agent_id=record.from_agent_id,
            to_agent_id=record.to_agent_id,
            reason=record.reason,
            context_transferred=record.context_transferred,
            handoff_at=record.handoff_at,
        )
        for record in records
    ]


@router.post("/v1/collaboration/sessions", response_model=CollaborationSession)
async def create_session(
    payload: CollaborationSessionCreateRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollaborationSession:
    """Create a new collaboration session."""
    user, _team_id = current_user

    manager = MultiAgentManager(db)
    session = await manager.create_collaboration(
        conversation_id=payload.conversation_id,
        pattern=payload.pattern,
        goal=payload.goal,
        initiator_id=payload.initiator_id,
    )

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"collaboration_create_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist collaboration session",
        ) from exc

    return session


@router.post(
    "/v1/collaboration/sessions/{session_id}/participants",
    response_model=CollaborationSession,
)
async def add_participants(
    session_id: UUID,
    payload: CollaborationParticipantsRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollaborationSession:
    """Add participants to an existing collaboration session."""
    user, _team_id = current_user

    manager = MultiAgentManager(db)
    participants = [(item.agent_id, item.role) for item in payload.participants]
    session = await manager.add_participants(session_id=session_id, participants=participants)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"collaboration_participants_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist participants",
        ) from exc

    return session


@router.patch(
    "/v1/collaboration/sessions/{session_id}/status",
    response_model=CollaborationSession,
)
async def update_session_status(
    session_id: UUID,
    payload: CollaborationStatusUpdateRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollaborationSession:
    """Update collaboration session status."""
    user, _team_id = current_user

    manager = MultiAgentManager(db)
    session = await manager.update_session_status(
        session_id=session_id,
        status=payload.status,
        final_result=payload.final_result,
    )

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"collaboration_status_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist session status",
        ) from exc

    return session
