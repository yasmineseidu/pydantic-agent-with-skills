"""Memory CRUD and semantic search endpoints."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db, get_settings
from src.api.schemas.common import PaginatedResponse, SuccessResponse
from src.api.schemas.memories import (
    MemoryCreateRequest,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)
from src.auth.dependencies import get_current_user
from src.db.models.memory import (
    MemoryORM,
    MemorySourceEnum,
    MemoryStatusEnum,
    MemoryTierEnum,
    MemoryTypeEnum,
)
from src.db.models.user import UserORM
from src.db.repositories.memory_repo import MemoryRepository
from src.memory.embedding import EmbeddingService
from src.memory.memory_log import MemoryAuditLog
from src.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter()


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------


def _orm_to_response(memory: MemoryORM) -> MemoryResponse:
    """
    Convert MemoryORM to MemoryResponse schema.

    Args:
        memory: Memory ORM instance from database

    Returns:
        MemoryResponse schema for API response
    """
    return MemoryResponse(
        id=memory.id,
        team_id=memory.team_id,
        agent_id=memory.agent_id,
        user_id=memory.user_id,
        memory_type=memory.memory_type,
        content=memory.content,
        subject=memory.subject,
        importance=memory.importance,
        confidence=memory.confidence,
        is_pinned=memory.is_pinned,
        status=memory.status,
        tier=memory.tier,
        access_count=memory.access_count,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


def _get_embedding_service(settings: Settings) -> Optional[EmbeddingService]:
    """
    Get EmbeddingService if configured, or None for graceful degradation.

    Args:
        settings: Application settings

    Returns:
        EmbeddingService if API key configured, None otherwise
    """
    if not settings.llm_api_key:
        logger.warning("get_embedding_service: api_key=not_configured")
        return None

    return EmbeddingService(
        api_key=settings.llm_api_key,
        model="text-embedding-3-small",
        dimensions=1536,
        base_url="https://api.openai.com/v1",
    )


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------


@router.get("/v1/memories", response_model=PaginatedResponse[MemoryResponse])
async def list_memories(
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    agent_id: Optional[UUID] = Query(None, description="Filter by agent ID"),
    status: str = Query(
        "active", description="Filter by status (active/superseded/archived/disputed)"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[MemoryResponse]:
    """
    List memories for the current team with pagination and filtering.

    All queries are scoped to the current team. Returns memories ordered by
    last accessed timestamp (most recent first).

    Args:
        memory_type: Optional filter by memory type (semantic, episodic, etc.)
        agent_id: Optional filter by agent ID
        status: Filter by status (default: active)
        limit: Max results per page (1-100, default: 20)
        offset: Number of records to skip (default: 0)
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency

    Returns:
        PaginatedResponse with memories and pagination metadata

    Raises:
        HTTPException: 400 if invalid memory_type or status value
        HTTPException: 401 if team_id not available in auth context
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"list_memories_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Validate memory_type if provided
    memory_type_filter: Optional[MemoryTypeEnum] = None
    if memory_type:
        try:
            memory_type_filter = MemoryTypeEnum(memory_type)
        except ValueError:
            logger.warning(
                f"list_memories_error: team_id={team_id}, invalid_memory_type={memory_type}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid memory_type: {memory_type}",
            )

    # Validate status
    try:
        status_filter = MemoryStatusEnum(status)
    except ValueError:
        logger.warning(f"list_memories_error: team_id={team_id}, invalid_status={status}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {status}",
        )

    repo = MemoryRepository(db)

    # Get total count
    count_stmt = select(func.count()).select_from(MemoryORM).where(MemoryORM.team_id == team_id)
    if memory_type_filter:
        count_stmt = count_stmt.where(MemoryORM.memory_type == memory_type_filter)
    if agent_id:
        count_stmt = count_stmt.where(MemoryORM.agent_id == agent_id)
    count_stmt = count_stmt.where(MemoryORM.status == status_filter)

    result = await db.execute(count_stmt)
    total = result.scalar() or 0

    # Get paginated memories
    memories = await repo.get_by_team(
        team_id=team_id,
        memory_types=[memory_type_filter] if memory_type_filter else None,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    has_more = (offset + len(memories)) < total

    logger.info(
        f"list_memories_success: team_id={team_id}, agent_id={agent_id}, "
        f"memory_type={memory_type}, status={status}, total={total}, "
        f"limit={limit}, offset={offset}, returned={len(memories)}"
    )

    return PaginatedResponse(
        items=[_orm_to_response(m) for m in memories],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post(
    "/v1/memories", response_model=MemoryResponse, status_code=http_status.HTTP_201_CREATED
)
async def create_memory(
    request: MemoryCreateRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """
    Create a new explicit memory (user-created, importance=8).

    Explicit memories are user-created memories with high importance (8).
    They are immediately active and stored in the warm tier. Embeddings
    are generated asynchronously if the embedding service is available.

    Args:
        request: Memory creation request with content, type, importance
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency
        settings: Application settings from dependency

    Returns:
        MemoryResponse for the created memory

    Raises:
        HTTPException: 400 if invalid memory type
        HTTPException: 401 if team_id not available in auth context
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"create_memory_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Validate memory type
    try:
        memory_type_value = MemoryTypeEnum(request.memory_type)
    except ValueError:
        logger.warning(
            f"create_memory_error: team_id={team_id}, invalid_memory_type={request.memory_type}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_type: {request.memory_type}",
        )

    # Generate embedding if service available
    embedding: Optional[list[float]] = None
    embedding_service = _get_embedding_service(settings)
    if embedding_service:
        try:
            embedding = await embedding_service.embed_text(request.content)
            logger.debug(f"create_memory: team_id={team_id}, embedding_generated=true")
        except Exception as e:
            # Non-fatal: continue without embedding
            logger.warning(f"create_memory_embedding_error: team_id={team_id}, error={str(e)}")

    # Create memory record
    memory = MemoryORM(
        team_id=team_id,
        agent_id=request.agent_id,
        user_id=user.id,
        memory_type=memory_type_value,
        content=request.content,
        subject=request.subject,
        embedding=embedding,
        importance=8,  # Explicit memories are high importance
        confidence=1.0,
        source_type=MemorySourceEnum.EXPLICIT,
        status=MemoryStatusEnum.ACTIVE,
        tier=MemoryTierEnum.WARM,
    )

    db.add(memory)
    await db.flush()
    await db.refresh(memory)

    # Audit log
    audit_log = MemoryAuditLog(db)
    await audit_log.log_created(
        memory_id=memory.id,
        content=memory.content,
        source="explicit",
        changed_by=f"user:{user.id}",
    )

    await db.commit()

    logger.info(
        f"create_memory_success: team_id={team_id}, memory_id={memory.id}, "
        f"user_id={user.id}, memory_type={memory.memory_type}, importance=8"
    )

    return _orm_to_response(memory)


@router.post("/v1/memories/search", response_model=MemorySearchResponse)
async def search_memories(
    request: MemorySearchRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemorySearchResponse:
    """
    Semantic search memories by embedding similarity.

    Generates an embedding for the query text, then searches memories using
    pgvector cosine similarity. Returns memories ranked by relevance.

    NOTE: Rate limit to 30 requests/min per user when rate limiter is enabled.

    Args:
        request: Search request with query, filters, and limit
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency
        settings: Application settings from dependency

    Returns:
        MemorySearchResponse with ranked memories

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 503 if embedding service unavailable
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"search_memories_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Get embedding service
    embedding_service = _get_embedding_service(settings)
    if embedding_service is None:
        logger.error(
            f"search_memories_error: team_id={team_id}, reason=embedding_service_unavailable"
        )
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service not configured",
        )

    # Generate query embedding
    try:
        query_embedding = await embedding_service.embed_text(request.query)
    except Exception as e:
        logger.error(f"search_memories_embedding_error: team_id={team_id}, error={str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to generate query embedding",
        )

    # Search by embedding
    repo = MemoryRepository(db)
    memory_type_filter = [MemoryTypeEnum(request.memory_type)] if request.memory_type else None

    results = await repo.search_by_embedding(
        embedding=query_embedding,
        team_id=team_id,
        agent_id=request.agent_id,
        memory_types=memory_type_filter,
        limit=request.limit,
    )

    logger.info(
        f"search_memories_success: team_id={team_id}, agent_id={request.agent_id}, "
        f"memory_type={request.memory_type}, query_length={len(request.query)}, "
        f"results_count={len(results)}"
    )

    return MemorySearchResponse(
        memories=[_orm_to_response(memory) for memory, _ in results],
        query=request.query,
        total=len(results),
    )


@router.delete("/v1/memories/{memory_id}", response_model=SuccessResponse)
async def delete_memory(
    memory_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    """
    Soft delete a memory (status=archived, tier=cold).

    Memories are never hard-deleted. Soft delete moves the memory to archived
    status and cold tier, removing it from active retrieval.

    Args:
        memory_id: UUID of the memory to delete
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency

    Returns:
        SuccessResponse confirming deletion

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if memory not found or not owned by team
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"delete_memory_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Get memory (team-scoped)
    stmt = select(MemoryORM).where(
        MemoryORM.id == memory_id,
        MemoryORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    memory = result.scalar_one_or_none()

    if memory is None:
        logger.warning(
            f"delete_memory_error: team_id={team_id}, memory_id={memory_id}, reason=not_found"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # Soft delete
    old_tier = memory.tier

    memory.status = MemoryStatusEnum.ARCHIVED
    memory.tier = MemoryTierEnum.COLD

    # Audit log (tier change for soft delete)
    audit_log = MemoryAuditLog(db)
    await audit_log.log_promoted(
        memory_id=memory.id,
        old_tier=old_tier,
        new_tier=memory.tier,
        changed_by=f"user:{user.id}",
    )

    await db.commit()

    logger.info(
        f"delete_memory_success: team_id={team_id}, memory_id={memory_id}, "
        f"user_id={user.id}, status={MemoryStatusEnum.ARCHIVED}, tier={MemoryTierEnum.COLD}"
    )

    return SuccessResponse(
        message="Memory deleted successfully",
        data={"memory_id": str(memory_id)},
    )


@router.post("/v1/memories/{memory_id}/pin", response_model=MemoryResponse)
async def toggle_pin_memory(
    memory_id: UUID,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """
    Toggle the pin status of a memory.

    Pinned memories are always included in retrieval regardless of relevance
    scores. Useful for critical information that should always be available.

    Args:
        memory_id: UUID of the memory to pin/unpin
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency

    Returns:
        MemoryResponse with updated pin status

    Raises:
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if memory not found or not owned by team
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"toggle_pin_memory_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Get memory (team-scoped)
    stmt = select(MemoryORM).where(
        MemoryORM.id == memory_id,
        MemoryORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    memory = result.scalar_one_or_none()

    if memory is None:
        logger.warning(
            f"toggle_pin_memory_error: team_id={team_id}, memory_id={memory_id}, reason=not_found"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # Toggle pin
    old_pinned = memory.is_pinned
    memory.is_pinned = not memory.is_pinned

    # Audit log (pin toggle)
    audit_log = MemoryAuditLog(db)
    await audit_log.log_updated(
        memory_id=memory.id,
        old_content=memory.content,
        new_content=memory.content,
        reason=f"pin_toggle: {'pinned' if memory.is_pinned else 'unpinned'}",
        changed_by=f"user:{user.id}",
    )

    await db.commit()
    await db.refresh(memory)

    logger.info(
        f"toggle_pin_memory_success: team_id={team_id}, memory_id={memory_id}, "
        f"user_id={user.id}, old_pinned={old_pinned}, new_pinned={memory.is_pinned}"
    )

    return _orm_to_response(memory)


@router.post(
    "/v1/memories/{memory_id}/correct",
    response_model=MemoryResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def correct_memory(
    memory_id: UUID,
    request: MemoryCreateRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MemoryResponse:
    """
    Create a corrected version of a memory.

    Creates a new memory with the corrected content and links it to the
    original memory via the superseded_by relationship. The original memory
    is moved to superseded status and cold tier.

    Args:
        memory_id: UUID of the memory to correct
        request: Corrected memory content and attributes
        current_user: Authenticated user and team_id from dependency
        db: Database session from dependency
        settings: Application settings from dependency

    Returns:
        MemoryResponse for the new corrected memory

    Raises:
        HTTPException: 400 if invalid memory type
        HTTPException: 401 if team_id not available in auth context
        HTTPException: 404 if original memory not found or not owned by team
    """
    user, team_id = current_user

    if team_id is None:
        logger.warning(f"correct_memory_error: user_id={user.id}, reason=team_id_not_available")
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Team context required",
        )

    # Get original memory (team-scoped)
    stmt = select(MemoryORM).where(
        MemoryORM.id == memory_id,
        MemoryORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    original_memory = result.scalar_one_or_none()

    if original_memory is None:
        logger.warning(
            f"correct_memory_error: team_id={team_id}, memory_id={memory_id}, reason=not_found"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # Validate memory type
    try:
        memory_type_value = MemoryTypeEnum(request.memory_type)
    except ValueError:
        logger.warning(
            f"correct_memory_error: team_id={team_id}, invalid_memory_type={request.memory_type}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_type: {request.memory_type}",
        )

    # Generate embedding if service available
    embedding: Optional[list[float]] = None
    embedding_service = _get_embedding_service(settings)
    if embedding_service:
        try:
            embedding = await embedding_service.embed_text(request.content)
            logger.debug(f"correct_memory: team_id={team_id}, embedding_generated=true")
        except Exception as e:
            # Non-fatal: continue without embedding
            logger.warning(f"correct_memory_embedding_error: team_id={team_id}, error={str(e)}")

    # Create corrected memory
    corrected_memory = MemoryORM(
        team_id=team_id,
        agent_id=request.agent_id or original_memory.agent_id,
        user_id=user.id,
        memory_type=memory_type_value,
        content=request.content,
        subject=request.subject or original_memory.subject,
        embedding=embedding,
        importance=request.importance,
        confidence=1.0,
        source_type=MemorySourceEnum.EXPLICIT,
        version=original_memory.version + 1,
        status=MemoryStatusEnum.ACTIVE,
        tier=MemoryTierEnum.WARM,
    )

    db.add(corrected_memory)
    await db.flush()
    await db.refresh(corrected_memory)

    # Update original memory
    original_memory.superseded_by = corrected_memory.id
    original_memory.status = MemoryStatusEnum.SUPERSEDED
    original_memory.tier = MemoryTierEnum.COLD

    # Audit logs
    audit_log = MemoryAuditLog(db)

    await audit_log.log_created(
        memory_id=corrected_memory.id,
        content=corrected_memory.content,
        source=f"correction_of_{memory_id}",
        changed_by=f"user:{user.id}",
    )

    await audit_log.log_superseded(
        old_id=original_memory.id,
        new_id=corrected_memory.id,
        reason=f"corrected by user:{user.id}",
        changed_by=f"user:{user.id}",
    )

    await db.commit()

    logger.info(
        f"correct_memory_success: team_id={team_id}, original_memory_id={memory_id}, "
        f"corrected_memory_id={corrected_memory.id}, user_id={user.id}, version={corrected_memory.version}"
    )

    return _orm_to_response(corrected_memory)
