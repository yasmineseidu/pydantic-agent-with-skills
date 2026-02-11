"""Collaboration endpoints for routing, handoffs, and multi-agent sessions."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_settings
from src.api.schemas.collaboration import (
    AgentMessageSendRequest,
    CollaborationParticipantsRequest,
    CollaborationRecommendRequest,
    CollaborationRouteRequest,
    CollaborationSessionCreateRequest,
    CollaborationStatusUpdateRequest,
    HandoffRecordResponse,
    HandoffRequest,
    TaskCancelRequest,
    TaskDelegateRequest,
)
from src.auth.dependencies import get_current_user
from src.collaboration.coordination.handoff_manager import HandoffManager
from src.collaboration.coordination.multi_agent_manager import MultiAgentManager
from src.collaboration.delegation.delegation_manager import DelegationManager
from src.collaboration.messaging.agent_message_bus import AgentMessageBus
from src.collaboration.models import (
    AgentMessage,
    AgentRecommendation,
    AgentTask,
    AgentTaskStatus,
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    HandoffResult,
    RoutingDecision,
)
from src.collaboration.routing.agent_directory import AgentDirectory
from src.collaboration.routing.agent_router import AgentRouter
from src.db.models.agent import AgentORM
from src.db.models.collaboration import AgentTaskORM, CollaborationSessionORM
from src.db.models.conversation import ConversationORM
from src.db.models.user import UserORM
from src.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_feature_flag(enabled: bool, flag_name: str) -> None:
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Feature flag disabled: {flag_name}",
        )


async def _verify_conversation_ownership(
    db: AsyncSession, conversation_id: UUID, team_id: Optional[UUID]
) -> None:
    """Verify the conversation belongs to the user's team.

    Args:
        db: Async database session.
        conversation_id: Conversation UUID to check.
        team_id: Current user's team UUID.

    Raises:
        HTTPException: 404 if conversation not found or not in user's team.
    """
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team membership required",
        )
    stmt = select(ConversationORM.id).where(
        ConversationORM.id == conversation_id,
        ConversationORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )


async def _verify_session_ownership(
    db: AsyncSession, session_id: UUID, team_id: Optional[UUID]
) -> None:
    """Verify the collaboration session belongs to the user's team.

    Args:
        db: Async database session.
        session_id: CollaborationSession UUID to check.
        team_id: Current user's team UUID.

    Raises:
        HTTPException: 404 if session not found or not in user's team.
    """
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team membership required",
        )
    stmt = (
        select(CollaborationSessionORM.id)
        .join(
            ConversationORM,
            CollaborationSessionORM.conversation_id == ConversationORM.id,
        )
        .where(
            CollaborationSessionORM.id == session_id,
            ConversationORM.team_id == team_id,
        )
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )


@router.post("/v1/collaboration/route", response_model=RoutingDecision)
async def route_to_agent(
    payload: CollaborationRouteRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RoutingDecision:
    """Route a query to the best agent for the current user."""
    user, _team_id = current_user
    _require_feature_flag(
        settings.feature_flags.enable_agent_collaboration
        or settings.feature_flags.enable_expert_gate,
        "enable_agent_collaboration",
    )

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
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

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
    settings: Settings = Depends(get_settings),
) -> HandoffResult:
    """Initiate a handoff between agents for a conversation."""
    user, team_id = current_user
    _require_feature_flag(
        settings.feature_flags.enable_agent_collaboration, "enable_agent_collaboration"
    )

    await _verify_conversation_ownership(db, payload.conversation_id, team_id)

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
            logger.error("handoff_commit_failed: user_id=%s error=%s", user.id, str(exc))
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
    settings: Settings = Depends(get_settings),
) -> list[HandoffRecordResponse]:
    """List recent handoffs for a conversation."""
    user, team_id = current_user
    _require_feature_flag(
        settings.feature_flags.enable_agent_collaboration, "enable_agent_collaboration"
    )

    await _verify_conversation_ownership(db, conversation_id, team_id)

    manager = HandoffManager(db)
    records = await manager.get_handoff_history(conversation_id=conversation_id, limit=limit)

    logger.info(
        "handoff_history_listed: user_id=%s conversation_id=%s count=%d",
        user.id,
        conversation_id,
        len(records),
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
    settings: Settings = Depends(get_settings),
) -> CollaborationSession:
    """Create a new collaboration session."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    await _verify_conversation_ownership(db, payload.conversation_id, team_id)

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
        logger.error("collaboration_create_commit_failed: user_id=%s error=%s", user.id, str(exc))
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
    settings: Settings = Depends(get_settings),
) -> CollaborationSession:
    """Add participants to an existing collaboration session."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    await _verify_session_ownership(db, session_id, team_id)

    manager = MultiAgentManager(db)
    participants = [(item.agent_id, item.role) for item in payload.participants]
    session = await manager.add_participants(session_id=session_id, participants=participants)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            f"collaboration_participants_commit_failed: user_id={user.id}, error={str(exc)}"
        )
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
    settings: Settings = Depends(get_settings),
) -> CollaborationSession:
    """Update collaboration session status."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    await _verify_session_ownership(db, session_id, team_id)

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


@router.get("/v1/collaborations/{session_id}", response_model=CollaborationSession)
async def get_session(
    session_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CollaborationSession:
    """Get a collaboration session by ID."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    await _verify_session_ownership(db, session_id, team_id)

    session_orm = await db.get(CollaborationSessionORM, session_id)
    if not session_orm:
        logger.warning(
            f"collaboration_session_not_found: user_id={user.id}, session_id={session_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        pattern = CollaborationPattern(session_orm.session_type)
    except ValueError:
        pattern = CollaborationPattern.DELEGATION

    try:
        status_value = CollaborationStatus(session_orm.status)
    except ValueError:
        status_value = CollaborationStatus.FAILED

    return CollaborationSession(
        id=session_orm.id,
        pattern=pattern,
        status=status_value,
        initiator_id=UUID(int=0),
        participants=[],
        started_at=session_orm.started_at,
        completed_at=session_orm.completed_at,
        stage_outputs=[],
        final_result=None,
        metadata={
            "conversation_id": str(session_orm.conversation_id),
            "goal": session_orm.goal,
            "total_cost": session_orm.total_cost,
            "total_duration_ms": session_orm.total_duration_ms,
        },
    )


@router.post("/v1/tasks/delegate", response_model=AgentTask)
async def delegate_task(
    payload: TaskDelegateRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentTask:
    """Delegate a task to another agent."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_task_delegation, "enable_task_delegation")

    await _verify_conversation_ownership(db, payload.conversation_id, team_id)

    manager = DelegationManager(db)
    result = await manager.delegate_task(
        conversation_id=payload.conversation_id,
        created_by_agent_id=payload.created_by_agent_id,
        assigned_to_agent_id=payload.assigned_to_agent_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        parent_task_id=payload.parent_task_id,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"delegate_task_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist delegated task",
        ) from exc

    return result


@router.get("/v1/tasks/{task_id}", response_model=AgentTask)
async def get_task(
    task_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentTask:
    """Get task status by task ID."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_task_delegation, "enable_task_delegation")

    stmt = (
        select(AgentTaskORM)
        .join(ConversationORM, AgentTaskORM.conversation_id == ConversationORM.id)
        .where(AgentTaskORM.id == task_id, ConversationORM.team_id == team_id)
    )
    result = await db.execute(stmt)
    task_orm = result.scalar_one_or_none()

    if not task_orm:
        logger.warning(f"task_not_found: user_id={user.id}, task_id={task_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    from src.collaboration.models import AgentTaskType, TaskPriority

    priority_enum = TaskPriority.NORMAL
    if task_orm.priority <= 2:
        priority_enum = TaskPriority.URGENT
    elif task_orm.priority <= 4:
        priority_enum = TaskPriority.HIGH
    elif task_orm.priority >= 8:
        priority_enum = TaskPriority.LOW

    return AgentTask(
        id=task_orm.id,
        task_type=AgentTaskType.EXECUTE,
        description=task_orm.description,
        status=AgentTaskStatus(task_orm.status),
        priority=priority_enum,
        assigned_to=task_orm.assigned_to_agent_id,
        created_by=task_orm.created_by_agent_id,
        created_at=task_orm.created_at,
        started_at=None,
        completed_at=task_orm.completed_at,
        result=task_orm.result,
        error=None,
        parent_task_id=task_orm.parent_task_id,
        depth=task_orm.delegation_depth,
        timeout_seconds=300,
        metadata={"title": task_orm.title, "conversation_id": str(task_orm.conversation_id)},
    )


@router.post("/v1/tasks/{task_id}/cancel", response_model=AgentTask)
async def cancel_task(
    task_id: UUID,
    payload: TaskCancelRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentTask:
    """Cancel a delegated task."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_task_delegation, "enable_task_delegation")

    stmt = (
        select(AgentTaskORM)
        .join(ConversationORM, AgentTaskORM.conversation_id == ConversationORM.id)
        .where(AgentTaskORM.id == task_id, ConversationORM.team_id == team_id)
    )
    result = await db.execute(stmt)
    task_orm = result.scalar_one_or_none()

    if not task_orm:
        logger.warning(f"task_cancel_not_found: user_id={user.id}, task_id={task_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    manager = DelegationManager(db)
    cancel_result = await manager.complete_task(
        task_id=task_id,
        result=payload.reason or "Task cancelled by user",
        status=AgentTaskStatus.CANCELLED,
    )

    if isinstance(cancel_result, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=cancel_result)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"cancel_task_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel task",
        ) from exc

    return cancel_result


@router.get("/v1/agents/{slug}/inbox", response_model=list[AgentMessage])
async def get_agent_inbox(
    slug: str,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[AgentMessage]:
    """Get pending messages for an agent by slug."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == slug)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if not agent:
        logger.warning(f"agent_inbox_not_found: user_id={user.id}, slug={slug}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    bus = AgentMessageBus(db)
    return await bus.get_pending_messages(agent_id=agent.id)


@router.post("/v1/agents/{slug}/messages", response_model=AgentMessage)
async def send_agent_message(
    slug: str,
    payload: AgentMessageSendRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentMessage:
    """Send a message from the specified agent to another agent."""
    user, team_id = current_user
    _require_feature_flag(settings.feature_flags.enable_collaboration, "enable_collaboration")

    stmt = select(AgentORM).where(AgentORM.team_id == team_id, AgentORM.slug == slug)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if not agent:
        logger.warning(f"agent_send_message_not_found: user_id={user.id}, slug={slug}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    bus = AgentMessageBus(db)
    message = await bus.send_message(
        conversation_id=payload.conversation_id,
        from_agent_id=agent.id,
        to_agent_id=payload.to_agent_id,
        message_type=payload.message_type,
        subject=payload.subject,
        body=payload.body,
        metadata=payload.metadata,
    )

    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to send message",
        )

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"send_message_commit_failed: user_id={user.id}, error={str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist message",
        ) from exc

    return message
