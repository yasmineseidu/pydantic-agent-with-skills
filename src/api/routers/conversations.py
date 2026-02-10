"""Conversation management endpoints."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.schemas.common import PaginatedResponse
from src.api.schemas.conversations import ConversationResponse, MessageResponse
from src.auth.dependencies import get_current_user
from src.db.models.conversation import ConversationORM, MessageORM
from src.db.models.user import UserORM

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/conversations", response_model=PaginatedResponse[ConversationResponse])
async def list_conversations(
    agent_id: Optional[UUID] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by status (active/idle/closed)"),
    limit: int = Query(20, ge=1, le=100, description="Max items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ConversationResponse]:
    """
    List conversations for the current team with pagination and filtering.

    Multi-tenant scoped: only returns conversations belonging to the current user's team.
    Supports filtering by agent ID and conversation status.

    Args:
        agent_id: Optional filter by agent ID
        status: Optional filter by status (active/idle/closed)
        limit: Maximum number of conversations to return (1-100, default 20)
        offset: Number of conversations to skip for pagination (default 0)
        current_user: Authenticated user and team ID from dependency
        db: Async database session from dependency

    Returns:
        PaginatedResponse with:
        - items: List of ConversationResponse objects
        - total: Total count of conversations matching filters
        - limit: Current limit value
        - offset: Current offset value
        - has_more: Whether more conversations exist beyond this page

    Raises:
        HTTPException: 401 if team_id not available in auth context
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(f"list_conversations_error: user_id={user.id}, reason=no_team_context")
        raise HTTPException(
            status_code=401,
            detail="Team context required",
        )

    # Build base query with team scoping (ALWAYS filter by team_id)
    base_filters = [ConversationORM.team_id == team_id]

    # Add optional filters
    if agent_id is not None:
        base_filters.append(ConversationORM.agent_id == agent_id)
    if status is not None:
        base_filters.append(ConversationORM.status == status)

    # Count total matching conversations
    count_stmt = select(func.count()).select_from(ConversationORM).where(*base_filters)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Fetch paginated conversations
    stmt = (
        select(ConversationORM)
        .where(*base_filters)
        .order_by(ConversationORM.last_message_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    # Convert to response models
    items = [
        ConversationResponse(
            id=conv.id,
            team_id=conv.team_id,
            agent_id=conv.agent_id,
            user_id=conv.user_id,
            title=conv.title,
            status=conv.status,
            message_count=conv.message_count,
            total_input_tokens=conv.total_input_tokens,
            total_output_tokens=conv.total_output_tokens,
            summary=conv.summary,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            last_message_at=conv.last_message_at,
        )
        for conv in conversations
    ]

    has_more = (offset + limit) < total

    logger.info(
        f"list_conversations_success: user_id={user.id}, team_id={team_id}, "
        f"agent_id={agent_id}, status={status}, total={total}, "
        f"returned={len(items)}, offset={offset}, limit={limit}"
    )

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/v1/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """
    Get conversation details by ID.

    Multi-tenant scoped: returns 404 if conversation does not belong to current team.

    Args:
        conversation_id: UUID of the conversation to retrieve
        current_user: Authenticated user and team ID from dependency
        db: Async database session from dependency

    Returns:
        ConversationResponse with full conversation details

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if conversation not found or does not belong to current team
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(
            f"get_conversation_error: user_id={user.id}, conversation_id={conversation_id}, "
            f"reason=no_team_context"
        )
        raise HTTPException(
            status_code=401,
            detail="Team context required",
        )

    # Query with team scoping (CRITICAL: prevents cross-team access)
    stmt = select(ConversationORM).where(
        ConversationORM.id == conversation_id,
        ConversationORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        logger.warning(
            f"get_conversation_not_found: user_id={user.id}, team_id={team_id}, "
            f"conversation_id={conversation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    logger.info(
        f"get_conversation_success: user_id={user.id}, team_id={team_id}, "
        f"conversation_id={conversation_id}, status={conversation.status}"
    )

    return ConversationResponse(
        id=conversation.id,
        team_id=conversation.team_id,
        agent_id=conversation.agent_id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        message_count=conversation.message_count,
        total_input_tokens=conversation.total_input_tokens,
        total_output_tokens=conversation.total_output_tokens,
        summary=conversation.summary,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_at=conversation.last_message_at,
    )


@router.get(
    "/v1/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[MessageResponse],
)
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=100, description="Max messages per page"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[MessageResponse]:
    """
    Get messages for a conversation with pagination.

    Multi-tenant scoped: returns 404 if conversation does not belong to current team.
    Messages returned in chronological order (oldest first).

    Args:
        conversation_id: UUID of the conversation
        limit: Maximum number of messages to return (1-100, default 50)
        offset: Number of messages to skip for pagination (default 0)
        current_user: Authenticated user and team ID from dependency
        db: Async database session from dependency

    Returns:
        PaginatedResponse with:
        - items: List of MessageResponse objects in chronological order (ASC)
        - total: Total count of messages in conversation
        - limit: Current limit value
        - offset: Current offset value
        - has_more: Whether more messages exist beyond this page

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if conversation not found or does not belong to current team
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(
            f"get_messages_error: user_id={user.id}, conversation_id={conversation_id}, "
            f"reason=no_team_context"
        )
        raise HTTPException(
            status_code=401,
            detail="Team context required",
        )

    # First verify conversation exists and belongs to team
    conv_stmt = select(ConversationORM).where(
        ConversationORM.id == conversation_id,
        ConversationORM.team_id == team_id,
    )
    conv_result = await db.execute(conv_stmt)
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        logger.warning(
            f"get_messages_conversation_not_found: user_id={user.id}, team_id={team_id}, "
            f"conversation_id={conversation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Count total messages in conversation
    count_stmt = (
        select(func.count())
        .select_from(MessageORM)
        .where(MessageORM.conversation_id == conversation_id)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Fetch paginated messages in chronological order (ASC)
    stmt = (
        select(MessageORM)
        .where(MessageORM.conversation_id == conversation_id)
        .order_by(MessageORM.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    # Convert to response models
    items = [
        MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            agent_id=msg.agent_id,
            role=msg.role,
            content=msg.content,
            token_count=msg.token_count,
            model=msg.model,
            created_at=msg.created_at,
        )
        for msg in messages
    ]

    has_more = (offset + limit) < total

    logger.info(
        f"get_messages_success: user_id={user.id}, team_id={team_id}, "
        f"conversation_id={conversation_id}, total={total}, "
        f"returned={len(items)}, offset={offset}, limit={limit}"
    )

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.delete("/v1/conversations/{conversation_id}", response_model=dict)
async def close_conversation(
    conversation_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Close a conversation (soft delete by setting status to 'closed').

    Multi-tenant scoped: returns 404 if conversation does not belong to current team.
    Note: Memory extraction trigger is handled by the chat router when messages are added.

    Args:
        conversation_id: UUID of the conversation to close
        current_user: Authenticated user and team ID from dependency
        db: Async database session from dependency

    Returns:
        Dictionary with success message and conversation ID

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if conversation not found or does not belong to current team
    """
    user, team_id = current_user

    if not team_id:
        logger.warning(
            f"close_conversation_error: user_id={user.id}, conversation_id={conversation_id}, "
            f"reason=no_team_context"
        )
        raise HTTPException(
            status_code=401,
            detail="Team context required",
        )

    # Query with team scoping (CRITICAL: prevents cross-team access)
    stmt = select(ConversationORM).where(
        ConversationORM.id == conversation_id,
        ConversationORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        logger.warning(
            f"close_conversation_not_found: user_id={user.id}, team_id={team_id}, "
            f"conversation_id={conversation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Update status to closed
    conversation.status = "closed"
    db.add(conversation)
    await db.commit()

    logger.info(
        f"close_conversation_success: user_id={user.id}, team_id={team_id}, "
        f"conversation_id={conversation_id}, previous_status={conversation.status}"
    )

    return {
        "message": "Conversation closed successfully",
        "conversation_id": str(conversation_id),
    }
