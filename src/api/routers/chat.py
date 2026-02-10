"""Chat endpoint for agent conversations (Phase 4 crown jewel)."""

import asyncio
import hashlib
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPartDelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.agent import Agent, create_skill_agent, skill_agent
from src.api.dependencies import get_agent_deps, get_db, get_settings
from src.api.schemas.chat import ChatRequest, ChatResponse, ChatUsage, StreamChunk
from src.auth.dependencies import authenticate_websocket, get_current_user
from src.collaboration.routing.agent_directory import AgentDirectory
from src.collaboration.routing.agent_router import AgentRouter
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.conversation import (
    ConversationORM,
    ConversationStatusEnum,
    MessageORM,
    MessageRoleEnum,
)
from src.db.models.user import UserORM
from src.dependencies import AgentDependencies
from src.moe.expert_gate import ExpertGate
from src.settings import Settings

if TYPE_CHECKING:
    from src.memory.storage import MemoryExtractor
    from src.models.agent_models import AgentDNA

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum first-message characters used to auto-generate a conversation title
_TITLE_MAX_LENGTH: int = 80

# Rate limit note: 60/min per user (enforcement added in Wave 7)
_RATE_LIMIT_PER_MINUTE: int = 60


def _generate_title(message: str) -> str:
    """Generate a conversation title from the first user message.

    Truncates at the first sentence boundary within _TITLE_MAX_LENGTH characters,
    or hard-truncates with an ellipsis if no boundary is found.

    Args:
        message: The first user message text.

    Returns:
        A title string of at most _TITLE_MAX_LENGTH characters.
    """
    # Strip whitespace and limit length
    clean: str = message.strip()
    if len(clean) <= _TITLE_MAX_LENGTH:
        return clean

    # Try to find a sentence boundary
    for sep in (".", "?", "!", "\n"):
        idx: int = clean.find(sep, 0, _TITLE_MAX_LENGTH)
        if idx > 0:
            return clean[: idx + 1]

    # Hard truncate
    return clean[: _TITLE_MAX_LENGTH - 3] + "..."


def _orm_to_agent_dna(agent_orm: AgentORM) -> Optional["AgentDNA"]:
    """Attempt to construct an AgentDNA from an AgentORM row.

    Returns None if construction fails (missing fields, invalid config).
    The caller should fall back to the basic agent in that case.

    Args:
        agent_orm: The SQLAlchemy agent model instance.

    Returns:
        AgentDNA instance, or None on failure.
    """
    try:
        from src.models.agent_models import (
            AgentBoundaries,
            AgentDNA,
            AgentMemoryConfig,
            AgentModelConfig,
            AgentPersonality,
            AgentStatus,
        )

        personality_data: dict = agent_orm.personality or {}
        if "system_prompt_template" not in personality_data:
            personality_data["system_prompt_template"] = ""

        return AgentDNA(
            id=agent_orm.id,
            team_id=agent_orm.team_id,
            name=agent_orm.name,
            slug=agent_orm.slug,
            tagline=agent_orm.tagline,
            avatar_emoji=agent_orm.avatar_emoji,
            personality=AgentPersonality(**personality_data),
            shared_skill_names=agent_orm.shared_skill_names or [],
            custom_skill_names=agent_orm.custom_skill_names or [],
            disabled_skill_names=agent_orm.disabled_skill_names or [],
            model=AgentModelConfig(**(agent_orm.model_config_json or {})),
            memory=AgentMemoryConfig(**(agent_orm.memory_config or {})),
            boundaries=AgentBoundaries(**(agent_orm.boundaries or {})),
            status=AgentStatus(agent_orm.status),
            created_at=agent_orm.created_at,
            updated_at=agent_orm.updated_at,
            created_by=agent_orm.created_by or agent_orm.team_id,
        )
    except Exception as e:
        logger.warning(
            "orm_to_agent_dna_failed: agent_id=%s, slug=%s, error=%s",
            agent_orm.id,
            agent_orm.slug,
            str(e),
        )
        return None


async def _route_to_agent(
    *,
    message: str,
    team_id: UUID,
    user_id: UUID,
    current_agent_slug: str,
    db: AsyncSession,
    settings: Settings,
    request_id: str,
) -> str:
    """Resolve the agent slug using routing feature flags.

    If expert gate is enabled, prefer ExpertGate selection. Otherwise, if
    agent collaboration is enabled, use the baseline AgentRouter. Falls
    back to the requested agent_slug on any error or no selection.
    """
    try:

        def _flag(name: str) -> bool:
            try:
                feature_flags = getattr(settings, "feature_flags", None)
                if feature_flags is None:
                    return False
                value = getattr(feature_flags, name, False)
                return value is True
            except Exception:
                return False

        if _flag("enable_expert_gate"):
            expert_gate = ExpertGate(settings)
            selection = await expert_gate.select_best_agent(
                session=db,
                team_id=team_id,
                task_description=message,
            )
            if not selection:
                return current_agent_slug

            stmt = select(AgentORM).where(
                AgentORM.id == selection.expert_id,
                AgentORM.team_id == team_id,
            )
            result = await db.execute(stmt)
            agent_orm = result.scalar_one_or_none()
            if not agent_orm or agent_orm.status != AgentStatusEnum.ACTIVE.value:
                return current_agent_slug

            if agent_orm.slug != current_agent_slug:
                logger.info(
                    "chat_routed_expert_gate: request_id=%s, from_slug=%s, to_slug=%s, "
                    "agent_id=%s, score=%.2f",
                    request_id,
                    current_agent_slug,
                    agent_orm.slug,
                    agent_orm.id,
                    selection.score.overall,
                )

            return agent_orm.slug

        if _flag("enable_agent_collaboration"):
            current_id_stmt = select(AgentORM.id).where(
                AgentORM.slug == current_agent_slug,
                AgentORM.team_id == team_id,
            )
            current_id_result = await db.execute(current_id_stmt)
            current_agent_id = current_id_result.scalar_one_or_none()

            directory = AgentDirectory(db)
            agent_router = AgentRouter(directory, settings)
            decision = await agent_router.route_to_agent(
                query=message,
                user_id=user_id,
                current_agent_id=current_agent_id,
            )

            selected_id = decision.selected_agent_id
            if not selected_id or selected_id.int == 0:
                return current_agent_slug

            stmt = select(AgentORM).where(
                AgentORM.id == selected_id,
                AgentORM.team_id == team_id,
            )
            result = await db.execute(stmt)
            agent_orm = result.scalar_one_or_none()
            if not agent_orm or agent_orm.status != AgentStatusEnum.ACTIVE.value:
                return current_agent_slug

            if agent_orm.slug != current_agent_slug:
                logger.info(
                    "chat_routed_agent_router: request_id=%s, from_slug=%s, to_slug=%s, "
                    "agent_id=%s, confidence=%.2f, reason=%s",
                    request_id,
                    current_agent_slug,
                    agent_orm.slug,
                    agent_orm.id,
                    decision.confidence,
                    decision.reasoning,
                )

            return agent_orm.slug

        return current_agent_slug
    except Exception as exc:
        logger.warning(
            "chat_routing_failed: request_id=%s, agent_slug=%s, error=%s",
            request_id,
            current_agent_slug,
            str(exc),
        )
        return current_agent_slug


@router.post(
    "/{agent_slug}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to an agent",
    responses={
        404: {"description": "Agent not found"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"},
    },
)
async def chat(
    agent_slug: str,
    body: ChatRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    agent_deps: AgentDependencies = Depends(get_agent_deps),
) -> ChatResponse:
    """Send a message to an agent and receive a response.

    Implements the 8-step chat flow:
    1. Resolve agent by slug + team_id
    2. Load or create conversation
    3. Retrieve memories (graceful degradation)
    4. Build memory-aware prompt (graceful degradation)
    5. Create agent instance (DNA-based or basic)
    6. Run agent and get response
    7. Persist user message and assistant response
    8. Trigger async memory extraction (fire and forget)

    Args:
        agent_slug: URL slug of the target agent.
        body: Chat request containing message and optional conversation_id.
        current_user: Authenticated user tuple (UserORM, team_id).
        db: Async database session.
        settings: Application settings.
        agent_deps: Initialized agent dependencies.

    Returns:
        ChatResponse with agent's response, conversation_id, usage, and request_id.

    Raises:
        HTTPException: 401 if not authenticated or no team context.
        HTTPException: 404 if agent or conversation not found.
        HTTPException: 400 if conversation does not belong to team.
    """
    request_id: str = str(uuid_mod.uuid4())
    user, team_id = current_user

    if not team_id:
        logger.warning(
            "chat_error: request_id=%s, reason=no_team_context, user_id=%s",
            request_id,
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required for chat",
        )

    logger.info(
        "chat_start: request_id=%s, agent_slug=%s, team_id=%s, user_id=%s, "
        "conversation_id=%s, message_length=%d",
        request_id,
        agent_slug,
        team_id,
        user.id,
        body.conversation_id,
        len(body.message),
    )

    # ---------------------------------------------------------------
    # Step 1: Resolve agent by slug + team_id
    # ---------------------------------------------------------------
    agent_slug = await _route_to_agent(
        message=body.message,
        team_id=team_id,
        user_id=user.id,
        current_agent_slug=agent_slug,
        db=db,
        settings=settings,
        request_id=request_id,
    )

    stmt = select(AgentORM).where(
        AgentORM.slug == agent_slug,
        AgentORM.team_id == team_id,
    )
    result = await db.execute(stmt)
    agent_orm: Optional[AgentORM] = result.scalar_one_or_none()

    if agent_orm is None:
        logger.warning(
            "chat_agent_not_found: request_id=%s, slug=%s, team_id=%s",
            request_id,
            agent_slug,
            team_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_slug}' not found",
        )

    if agent_orm.status != AgentStatusEnum.ACTIVE.value:
        logger.warning(
            "chat_agent_not_active: request_id=%s, agent_id=%s, status=%s",
            request_id,
            agent_orm.id,
            agent_orm.status,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_slug}' is not active",
        )

    logger.info(
        "chat_agent_resolved: request_id=%s, agent_id=%s, agent_name=%s",
        request_id,
        agent_orm.id,
        agent_orm.name,
    )

    # ---------------------------------------------------------------
    # Step 2: Load or create conversation
    # ---------------------------------------------------------------
    conversation: ConversationORM
    is_new_conversation: bool = False

    if body.conversation_id:
        # Load existing conversation
        conv_stmt = select(ConversationORM).where(
            ConversationORM.id == body.conversation_id,
        )
        conv_result = await db.execute(conv_stmt)
        existing_conv: Optional[ConversationORM] = conv_result.scalar_one_or_none()

        if existing_conv is None:
            logger.warning(
                "chat_conversation_not_found: request_id=%s, conversation_id=%s",
                request_id,
                body.conversation_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Verify conversation belongs to the same team
        if existing_conv.team_id != team_id:
            logger.warning(
                "chat_conversation_wrong_team: request_id=%s, "
                "conversation_id=%s, conv_team=%s, user_team=%s",
                request_id,
                body.conversation_id,
                existing_conv.team_id,
                team_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        conversation = existing_conv
        logger.info(
            "chat_conversation_loaded: request_id=%s, conversation_id=%s, message_count=%d",
            request_id,
            conversation.id,
            conversation.message_count,
        )
    else:
        # Create new conversation
        title: str = _generate_title(body.message)
        conversation = ConversationORM(
            team_id=team_id,
            agent_id=agent_orm.id,
            user_id=user.id,
            title=title,
            status=ConversationStatusEnum.ACTIVE.value,
            message_count=0,
            total_input_tokens=0,
            total_output_tokens=0,
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        is_new_conversation = True

        logger.info(
            "chat_conversation_created: request_id=%s, conversation_id=%s, title=%s",
            request_id,
            conversation.id,
            title[:50],
        )

    # ---------------------------------------------------------------
    # Step 3: Retrieve memories (graceful degradation)
    # ---------------------------------------------------------------
    retrieval_result = None
    if agent_deps.memory_retriever:
        try:
            retrieval_result = await agent_deps.memory_retriever.retrieve(
                query=body.message,
                team_id=team_id,
                agent_id=agent_orm.id,
                conversation_id=conversation.id,
            )
            logger.info(
                "chat_memory_retrieved: request_id=%s, memories=%d, cache_hit=%s",
                request_id,
                len(retrieval_result.memories),
                retrieval_result.stats.cache_hit,
            )
        except Exception as e:
            logger.warning(
                "chat_memory_retrieval_failed: request_id=%s, error=%s",
                request_id,
                str(e),
            )
            retrieval_result = None
    else:
        logger.debug(
            "chat_memory_retrieval_skipped: request_id=%s, reason=retriever_not_available",
            request_id,
        )

    # ---------------------------------------------------------------
    # Step 4: Build memory-aware prompt (graceful degradation)
    # ---------------------------------------------------------------
    # Prompt building is handled by the agent's system_prompt decorator
    # when using create_skill_agent(agent_dna). The MemoryPromptBuilder
    # is invoked inside get_memory_aware_prompt in agent.py.
    # We just need to wire up the deps correctly.

    # ---------------------------------------------------------------
    # Step 5: Create agent instance
    # ---------------------------------------------------------------
    agent_dna = _orm_to_agent_dna(agent_orm)
    active_agent = skill_agent  # default fallback

    if agent_dna is not None:
        try:
            active_agent = create_skill_agent(agent_dna=agent_dna)
            logger.info(
                "chat_agent_created: request_id=%s, agent_name=%s, model=%s, skills=%d",
                request_id,
                agent_dna.name,
                agent_dna.model.model_name,
                len(agent_dna.effective_skills),
            )
        except Exception as e:
            logger.warning(
                "chat_agent_creation_failed: request_id=%s, error=%s, falling_back_to_default",
                request_id,
                str(e),
            )
            active_agent = skill_agent
    else:
        logger.info(
            "chat_using_default_agent: request_id=%s, reason=dna_construction_failed",
            request_id,
        )

    # ---------------------------------------------------------------
    # Step 6: Run agent
    # ---------------------------------------------------------------
    try:
        run_result = await active_agent.run(body.message, deps=agent_deps)
        response_text: str = run_result.output
        usage = run_result.usage()
        input_tokens: int = usage.input_tokens
        output_tokens: int = usage.output_tokens

        logger.info(
            "chat_agent_run_success: request_id=%s, response_length=%d, "
            "input_tokens=%d, output_tokens=%d",
            request_id,
            len(response_text),
            input_tokens,
            output_tokens,
        )
    except Exception as e:
        logger.exception(
            "chat_agent_run_failed: request_id=%s, error=%s",
            request_id,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent execution failed",
        ) from e

    # ---------------------------------------------------------------
    # Step 7: Persist messages and update conversation counters
    # ---------------------------------------------------------------
    now: datetime = datetime.now(timezone.utc)
    model_name: str = settings.llm_model
    if agent_dna is not None:
        model_name = agent_dna.model.model_name

    # User message
    user_message = MessageORM(
        conversation_id=conversation.id,
        agent_id=None,
        role=MessageRoleEnum.USER.value,
        content=body.message,
        token_count=input_tokens,
        model=None,
    )
    db.add(user_message)

    # Assistant message
    assistant_message = MessageORM(
        conversation_id=conversation.id,
        agent_id=agent_orm.id,
        role=MessageRoleEnum.ASSISTANT.value,
        content=response_text,
        token_count=output_tokens,
        model=model_name,
    )
    db.add(assistant_message)

    # Update conversation counters
    conversation.message_count += 2
    conversation.total_input_tokens += input_tokens
    conversation.total_output_tokens += output_tokens
    conversation.last_message_at = now
    db.add(conversation)

    await db.flush()
    await db.refresh(user_message)
    await db.refresh(assistant_message)

    logger.info(
        "chat_messages_persisted: request_id=%s, conversation_id=%s, "
        "user_msg_id=%s, assistant_msg_id=%s, total_messages=%d",
        request_id,
        conversation.id,
        user_message.id,
        assistant_message.id,
        conversation.message_count,
    )

    # Commit the transaction
    await db.commit()

    # ---------------------------------------------------------------
    # Step 8: Trigger async memory extraction (fire and forget)
    # ---------------------------------------------------------------
    if agent_deps.memory_extractor:
        try:
            messages_for_extraction: list[dict[str, str]] = [
                {"role": "user", "content": body.message},
                {"role": "assistant", "content": response_text},
            ]

            # Try Celery dispatch if background processing enabled
            _dispatched = False
            if settings.feature_flags.enable_background_processing:
                try:
                    from workers.tasks.memory_tasks import extract_memories

                    extract_memories.delay(
                        messages=messages_for_extraction,
                        team_id=str(team_id),
                        agent_id=str(agent_orm.id),
                        user_id=str(user.id),
                        conversation_id=str(conversation.id),
                    )
                    _dispatched = True
                    logger.info(
                        "chat_extraction_celery_dispatched: request_id=%s",
                        request_id,
                    )
                except Exception as celery_exc:
                    logger.warning(
                        "chat_extraction_celery_failed: request_id=%s, error=%s, falling_back=asyncio",
                        request_id,
                        str(celery_exc),
                    )

            if not _dispatched:
                asyncio.create_task(
                    _extract_memories(
                        extractor=agent_deps.memory_extractor,
                        messages=messages_for_extraction,
                        team_id=team_id,
                        agent_id=agent_orm.id,
                        user_id=user.id,
                        conversation_id=conversation.id,
                        request_id=request_id,
                    )
                )
            logger.info(
                "chat_extraction_triggered: request_id=%s, conversation_id=%s",
                request_id,
                conversation.id,
            )
        except Exception as e:
            # Fire-and-forget: do not fail the response
            logger.warning(
                "chat_extraction_trigger_failed: request_id=%s, error=%s",
                request_id,
                str(e),
            )
    else:
        logger.debug(
            "chat_extraction_skipped: request_id=%s, reason=extractor_not_available",
            request_id,
        )

    # ---------------------------------------------------------------
    # Build and return response
    # ---------------------------------------------------------------
    chat_response = ChatResponse(
        response=response_text,
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        usage=ChatUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model_name,
        ),
        request_id=request_id,
    )

    logger.info(
        "chat_complete: request_id=%s, conversation_id=%s, is_new=%s, total_tokens=%d",
        request_id,
        conversation.id,
        is_new_conversation,
        input_tokens + output_tokens,
    )

    return chat_response


async def _stream_agent_response(
    agent_slug: str,
    body: ChatRequest,
    user: UserORM,
    team_id: UUID,
    db: AsyncSession,
    settings: Settings,
    agent_deps: AgentDependencies,
    request_id: str,
    *,
    include_tool_events: bool = False,
    include_memory_context: bool = False,
) -> AsyncIterator[StreamChunk]:
    """Generate StreamChunk objects for an agent conversation.

    Implements the core streaming logic (Steps 1-8) shared by SSE and
    WebSocket transports.  Yields raw StreamChunk objects; callers are
    responsible for serialising them into the wire format (SSE lines,
    WebSocket frames, etc.).

    Args:
        agent_slug: URL slug of the target agent.
        body: Chat request containing message and optional conversation_id.
        user: Authenticated user ORM instance.
        team_id: Team UUID for multi-tenant scoping.
        db: Async database session.
        settings: Application settings.
        agent_deps: Initialized agent dependencies.
        request_id: Unique request ID for log correlation.
        include_tool_events: When True, yield tool_call StreamChunks for tool invocations.
        include_memory_context: When True, yield a memory_context StreamChunk with memory count.

    Yields:
        StreamChunk objects of type "typing", "memory_context", "content",
        "tool_call", "usage", "done", or "error".
    """
    try:
        # ---------------------------------------------------------------
        # Step 1: Resolve agent by slug + team_id
        # ---------------------------------------------------------------
        agent_slug = await _route_to_agent(
            message=body.message,
            team_id=team_id,
            user_id=user.id,
            current_agent_slug=agent_slug,
            db=db,
            settings=settings,
            request_id=request_id,
        )

        stmt = select(AgentORM).where(
            AgentORM.slug == agent_slug,
            AgentORM.team_id == team_id,
        )
        result = await db.execute(stmt)
        agent_orm: Optional[AgentORM] = result.scalar_one_or_none()

        if agent_orm is None:
            logger.warning(
                "stream_chat_agent_not_found: request_id=%s, slug=%s, team_id=%s",
                request_id,
                agent_slug,
                team_id,
            )
            yield StreamChunk(type="error", content=f"Agent '{agent_slug}' not found")
            return

        if agent_orm.status != AgentStatusEnum.ACTIVE.value:
            logger.warning(
                "stream_chat_agent_not_active: request_id=%s, agent_id=%s, status=%s",
                request_id,
                agent_orm.id,
                agent_orm.status,
            )
            yield StreamChunk(type="error", content=f"Agent '{agent_slug}' is not active")
            return

        # ---------------------------------------------------------------
        # Step 2: Load or create conversation
        # ---------------------------------------------------------------
        conversation: ConversationORM
        is_new_conversation: bool = False

        if body.conversation_id:
            # Load existing conversation
            conv_stmt = select(ConversationORM).where(
                ConversationORM.id == body.conversation_id,
            )
            conv_result = await db.execute(conv_stmt)
            existing_conv: Optional[ConversationORM] = conv_result.scalar_one_or_none()

            if existing_conv is None:
                logger.warning(
                    "stream_chat_conversation_not_found: request_id=%s, conversation_id=%s",
                    request_id,
                    body.conversation_id,
                )
                yield StreamChunk(type="error", content="Conversation not found")
                return

            # Verify conversation belongs to the same team
            if existing_conv.team_id != team_id:
                logger.warning(
                    "stream_chat_conversation_wrong_team: request_id=%s, "
                    "conversation_id=%s, conv_team=%s, user_team=%s",
                    request_id,
                    body.conversation_id,
                    existing_conv.team_id,
                    team_id,
                )
                yield StreamChunk(type="error", content="Conversation not found")
                return

            conversation = existing_conv
        else:
            # Create new conversation
            title: str = _generate_title(body.message)
            conversation = ConversationORM(
                team_id=team_id,
                agent_id=agent_orm.id,
                user_id=user.id,
                title=title,
                status=ConversationStatusEnum.ACTIVE.value,
                message_count=0,
                total_input_tokens=0,
                total_output_tokens=0,
            )
            db.add(conversation)
            await db.flush()
            await db.refresh(conversation)
            is_new_conversation = True

        # ---------------------------------------------------------------
        # Step 3: Retrieve memories (graceful degradation)
        # ---------------------------------------------------------------
        retrieval_result = None
        if agent_deps.memory_retriever:
            try:
                retrieval_result = await agent_deps.memory_retriever.retrieve(
                    query=body.message,
                    team_id=team_id,
                    agent_id=agent_orm.id,
                    conversation_id=conversation.id,
                )
            except Exception as e:
                logger.warning(
                    "stream_chat_memory_retrieval_failed: request_id=%s, error=%s",
                    request_id,
                    str(e),
                )

        # ---------------------------------------------------------------
        # Step 5: Create agent instance
        # ---------------------------------------------------------------
        agent_dna = _orm_to_agent_dna(agent_orm)
        active_agent = skill_agent  # default fallback

        if agent_dna is not None:
            try:
                active_agent = create_skill_agent(agent_dna=agent_dna)
            except Exception as e:
                logger.warning(
                    "stream_chat_agent_creation_failed: request_id=%s, error=%s",
                    request_id,
                    str(e),
                )
                active_agent = skill_agent

        # ---------------------------------------------------------------
        # Step 6: Stream agent response using agent.iter()
        # ---------------------------------------------------------------
        # Emit memory context if requested
        if include_memory_context and agent_deps.memory_retriever:
            memory_count: int = 0
            if retrieval_result is not None:
                memory_count = len(retrieval_result.memories)
            yield StreamChunk(type="memory_context", memory_count=memory_count)

        # Emit typing indicator
        yield StreamChunk(type="typing")

        response_text: str = ""
        input_tokens: int = 0
        output_tokens: int = 0
        first_chunk: bool = True

        async with active_agent.iter(body.message, deps=agent_deps) as run:
            async for node in run:
                # Handle model request node - stream text deltas
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            # Handle text part start events
                            if isinstance(event, PartStartEvent) and event.part.part_kind == "text":
                                initial_text = event.part.content
                                if initial_text:
                                    response_text += initial_text
                                    if first_chunk:
                                        chunk = StreamChunk(
                                            type="content",
                                            content=initial_text,
                                            conversation_id=conversation.id,
                                        )
                                        first_chunk = False
                                    else:
                                        chunk = StreamChunk(
                                            type="content",
                                            content=initial_text,
                                        )
                                    yield chunk

                            # Handle text delta events for streaming
                            elif isinstance(event, PartDeltaEvent) and isinstance(
                                event.delta, TextPartDelta
                            ):
                                delta_text = event.delta.content_delta
                                if delta_text:
                                    response_text += delta_text
                                    if first_chunk:
                                        chunk = StreamChunk(
                                            type="content",
                                            content=delta_text,
                                            conversation_id=conversation.id,
                                        )
                                        first_chunk = False
                                    else:
                                        chunk = StreamChunk(
                                            type="content",
                                            content=delta_text,
                                        )
                                    yield chunk

                            # Handle tool call events
                            elif (
                                isinstance(event, PartStartEvent)
                                and event.part.part_kind == "tool-call"
                            ):
                                if include_tool_events:
                                    yield StreamChunk(
                                        type="tool_call",
                                        tool_name=event.part.tool_name,
                                        tool_args=event.part.args_as_dict(),
                                        tool_call_id=event.part.tool_call_id,
                                    )

        # Get usage from run
        usage = run.usage()
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        # ---------------------------------------------------------------
        # Step 7: Persist messages and update conversation counters
        # ---------------------------------------------------------------
        now: datetime = datetime.now(timezone.utc)
        model_name: str = settings.llm_model
        if agent_dna is not None:
            model_name = agent_dna.model.model_name

        # User message
        user_message = MessageORM(
            conversation_id=conversation.id,
            agent_id=None,
            role=MessageRoleEnum.USER.value,
            content=body.message,
            token_count=input_tokens,
            model=None,
        )
        db.add(user_message)

        # Assistant message
        assistant_message = MessageORM(
            conversation_id=conversation.id,
            agent_id=agent_orm.id,
            role=MessageRoleEnum.ASSISTANT.value,
            content=response_text,
            token_count=output_tokens,
            model=model_name,
        )
        db.add(assistant_message)

        # Update conversation counters
        conversation.message_count += 2
        conversation.total_input_tokens += input_tokens
        conversation.total_output_tokens += output_tokens
        conversation.last_message_at = now
        db.add(conversation)

        await db.flush()
        await db.refresh(user_message)
        await db.refresh(assistant_message)
        await db.commit()

        # Send usage chunk
        yield StreamChunk(
            type="usage",
            usage=ChatUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
            ),
        )

        # Send done chunk
        yield StreamChunk(type="done")

        # ---------------------------------------------------------------
        # Step 8: Trigger async memory extraction (fire and forget)
        # ---------------------------------------------------------------
        if agent_deps.memory_extractor:
            try:
                messages_for_extraction: list[dict[str, str]] = [
                    {"role": "user", "content": body.message},
                    {"role": "assistant", "content": response_text},
                ]

                # Try Celery dispatch if background processing enabled
                _dispatched = False
                if settings.feature_flags.enable_background_processing:
                    try:
                        from workers.tasks.memory_tasks import extract_memories

                        extract_memories.delay(
                            messages=messages_for_extraction,
                            team_id=str(team_id),
                            agent_id=str(agent_orm.id),
                            user_id=str(user.id),
                            conversation_id=str(conversation.id),
                        )
                        _dispatched = True
                        logger.info(
                            "stream_chat_extraction_celery_dispatched: request_id=%s",
                            request_id,
                        )
                    except Exception as celery_exc:
                        logger.warning(
                            "stream_chat_extraction_celery_failed: request_id=%s, error=%s, falling_back=asyncio",
                            request_id,
                            str(celery_exc),
                        )

                if not _dispatched:
                    asyncio.create_task(
                        _extract_memories(
                            extractor=agent_deps.memory_extractor,
                            messages=messages_for_extraction,
                            team_id=team_id,
                            agent_id=agent_orm.id,
                            user_id=user.id,
                            conversation_id=conversation.id,
                            request_id=request_id,
                        )
                    )
            except Exception as e:
                logger.warning(
                    "stream_chat_extraction_trigger_failed: request_id=%s, error=%s",
                    request_id,
                    str(e),
                )

        logger.info(
            "stream_chat_complete: request_id=%s, conversation_id=%s, is_new=%s, total_tokens=%d",
            request_id,
            conversation.id,
            is_new_conversation,
            input_tokens + output_tokens,
        )

    except Exception as e:
        logger.exception(
            "stream_chat_error: request_id=%s, error=%s",
            request_id,
            str(e),
        )
        yield StreamChunk(type="error", content=f"Stream failed: {str(e)}")


@router.post(
    "/{agent_slug}/chat/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream a message to an agent via Server-Sent Events",
    responses={
        404: {"description": "Agent not found"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"},
    },
)
async def stream_chat(
    agent_slug: str,
    body: ChatRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    agent_deps: AgentDependencies = Depends(get_agent_deps),
) -> StreamingResponse:
    """Stream agent response via Server-Sent Events.

    Thin SSE wrapper around _stream_agent_response(). Formats each
    StreamChunk as an SSE ``data:`` line.

    SSE Event types:
    - {"type": "content", "content": "...", "conversation_id": "..."} - First chunk with text delta
    - {"type": "content", "content": "..."} - Subsequent text deltas
    - {"type": "usage", "usage": {...}} - Token usage after completion
    - {"type": "done"} - Marks end of stream
    - {"type": "error", "content": "..."} - Error message

    Args:
        agent_slug: URL slug of the target agent.
        body: Chat request containing message and optional conversation_id.
        current_user: Authenticated user tuple (UserORM, team_id).
        db: Async database session.
        settings: Application settings.
        agent_deps: Initialized agent dependencies.

    Returns:
        StreamingResponse with media_type="text/event-stream".

    Raises:
        HTTPException: 401 if not authenticated or no team context.
    """
    request_id: str = str(uuid_mod.uuid4())
    user, team_id = current_user

    if not team_id:
        logger.warning(
            "stream_chat_error: request_id=%s, reason=no_team_context, user_id=%s",
            request_id,
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required for chat",
        )

    logger.info(
        "stream_chat_start: request_id=%s, agent_slug=%s, team_id=%s, user_id=%s",
        request_id,
        agent_slug,
        team_id,
        user.id,
    )

    async def event_generator() -> AsyncIterator[str]:
        """Format StreamChunk objects as SSE data lines."""
        async for chunk in _stream_agent_response(
            agent_slug=agent_slug,
            body=body,
            user=user,
            team_id=team_id,
            db=db,
            settings=settings,
            agent_deps=agent_deps,
            request_id=request_id,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/{agent_slug}/chat/stream/advanced",
    status_code=status.HTTP_200_OK,
    summary="Stream a message with tool call and memory context events",
    responses={
        404: {"description": "Agent not found"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"},
    },
)
async def stream_chat_advanced(
    agent_slug: str,
    body: ChatRequest,
    current_user: tuple[UserORM, Optional[UUID]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    agent_deps: AgentDependencies = Depends(get_agent_deps),
) -> StreamingResponse:
    """Stream agent response with tool call and memory context events.

    Extended SSE endpoint that includes all event types: typing indicators,
    memory context counts, tool call notifications, text deltas, usage, and
    completion markers.

    SSE Event types:
    - {"type": "typing"} - Agent is preparing a response
    - {"type": "memory_context", "memory_count": N} - Loaded memory count
    - {"type": "content", "content": "...", "conversation_id": "..."} - First text delta
    - {"type": "content", "content": "..."} - Subsequent text deltas
    - {"type": "tool_call", "tool_name": "...", "tool_args": {...}, "tool_call_id": "..."} - Tool invocation
    - {"type": "usage", "usage": {...}} - Token usage after completion
    - {"type": "done"} - Marks end of stream
    - {"type": "error", "content": "..."} - Error message

    Args:
        agent_slug: URL slug of the target agent.
        body: Chat request containing message and optional conversation_id.
        current_user: Authenticated user tuple (UserORM, team_id).
        db: Async database session.
        settings: Application settings.
        agent_deps: Initialized agent dependencies.

    Returns:
        StreamingResponse with media_type="text/event-stream".

    Raises:
        HTTPException: 401 if not authenticated or no team context.
    """
    request_id: str = str(uuid_mod.uuid4())
    user, team_id = current_user

    if not team_id:
        logger.warning(
            "stream_chat_advanced_error: request_id=%s, reason=no_team_context, user_id=%s",
            request_id,
            user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Team context required for chat",
        )

    logger.info(
        "stream_chat_advanced_start: request_id=%s, agent_slug=%s, team_id=%s, user_id=%s",
        request_id,
        agent_slug,
        team_id,
        user.id,
    )

    async def event_generator() -> AsyncIterator[str]:
        """Format StreamChunk objects as SSE data lines."""
        async for chunk in _stream_agent_response(
            agent_slug=agent_slug,
            body=body,
            user=user,
            team_id=team_id,
            db=db,
            settings=settings,
            agent_deps=agent_deps,
            request_id=request_id,
            include_tool_events=True,
            include_memory_context=True,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _handle_ws_message(
    websocket: WebSocket,
    agent_slug: str,
    content: str,
    conversation_id: Optional[UUID],
    user: UserORM,
    team_id: UUID,
    db: AsyncSession,
    settings: Settings,
    agent_deps: AgentDependencies,
    request_id: str,
) -> None:
    """Handle a single WebSocket chat message by streaming agent response.

    Sends typing indicator, then streams each StreamChunk from
    _stream_agent_response() as a JSON frame over the WebSocket.

    Args:
        websocket: Active WebSocket connection.
        agent_slug: URL slug of the target agent.
        content: User's message text.
        conversation_id: Optional existing conversation UUID.
        user: Authenticated user.
        team_id: Team UUID for scoping.
        db: Async database session.
        settings: Application settings.
        agent_deps: Agent dependencies.
        request_id: Request ID for logging.
    """
    body = ChatRequest(message=content, conversation_id=conversation_id)

    try:
        async for chunk in _stream_agent_response(
            agent_slug=agent_slug,
            body=body,
            user=user,
            team_id=team_id,
            db=db,
            settings=settings,
            agent_deps=agent_deps,
            request_id=request_id,
            include_tool_events=True,
            include_memory_context=True,
        ):
            # Convert StreamChunk to WSServerMessage format
            msg = chunk.model_dump(exclude_none=True)
            await websocket.send_json(msg)
    except asyncio.CancelledError:
        logger.info(
            "ws_stream_cancelled: request_id=%s",
            request_id,
        )
        await websocket.send_json({"type": "done", "content": "Cancelled by client"})
    except Exception as e:
        logger.error(
            "ws_handle_message_error: request_id=%s, error=%s",
            request_id,
            str(e),
        )
        await websocket.send_json(
            {
                "type": "error",
                "content": f"Stream failed: {str(e)}",
            }
        )


@router.websocket("/{agent_slug}/ws")
async def agent_websocket(
    websocket: WebSocket,
    agent_slug: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    agent_deps: AgentDependencies = Depends(get_agent_deps),
) -> None:
    """WebSocket endpoint for real-time agent conversations.

    Supports bidirectional communication with:
    - Authentication via query param (?token=jwt) or first message
    - Ping/pong keepalive
    - Message streaming with tool events
    - Client disconnect handling

    Args:
        websocket: WebSocket connection.
        agent_slug: URL slug of the target agent.
        db: Async database session.
        settings: Application settings.
        agent_deps: Initialized agent dependencies.
    """
    request_id: str = str(uuid_mod.uuid4())

    # Rate limit check (pre-auth, by IP)
    rate_limiter = getattr(websocket.app.state, "rate_limiter", None)
    if rate_limiter:
        try:
            client_ip = websocket.client.host if websocket.client else "unknown"
            ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:32]
            ip_uuid = UUID(ip_hash)
            result = await rate_limiter.check_rate_limit(
                team_id=ip_uuid,
                resource="chat",
                limit=_RATE_LIMIT_PER_MINUTE,
                window_seconds=60,
            )
            if not result.allowed:
                logger.warning(
                    "ws_rate_limited_pre_auth: request_id=%s, client_ip=%s",
                    request_id,
                    client_ip,
                )
                await websocket.close(code=4029, reason="Rate limit exceeded")
                return
        except Exception as e:
            # Graceful degradation - allow if Redis unavailable
            logger.warning(
                "ws_rate_limit_check_failed: request_id=%s, error=%s",
                request_id,
                str(e),
            )

    # Authenticate
    try:
        user, team_id = await authenticate_websocket(websocket, db, settings)
    except Exception:
        logger.warning(
            "ws_auth_failed: request_id=%s, agent_slug=%s",
            request_id,
            agent_slug,
        )
        return

    logger.info(
        "ws_connected: request_id=%s, agent_slug=%s, user_id=%s, team_id=%s",
        request_id,
        agent_slug,
        user.id,
        team_id,
    )

    active_task: dict[str, Optional[asyncio.Task[None]]] = {"current": None}

    async def run_streaming(content: str, conversation_id: Optional[UUID]) -> None:
        """Run _handle_ws_message as a background task.

        Catches CancelledError and generic exceptions so that
        errors never propagate out of the task boundary.
        """
        try:
            await _handle_ws_message(
                websocket=websocket,
                agent_slug=agent_slug,
                content=content,
                conversation_id=conversation_id,
                user=user,
                team_id=team_id,
                db=db,
                settings=settings,
                agent_deps=agent_deps,
                request_id=request_id,
            )
        except asyncio.CancelledError:
            logger.info(
                "ws_task_cancelled: request_id=%s, agent_slug=%s",
                request_id,
                agent_slug,
            )
            await websocket.send_json({"type": "done", "content": "Cancelled by client"})
        except Exception as e:
            logger.error(
                "ws_task_error: request_id=%s, error=%s",
                request_id,
                str(e),
            )
        finally:
            active_task["current"] = None

    try:
        while True:
            data = await websocket.receive_json()

            # Per-message rate limit check (post-auth, by team)
            if rate_limiter:
                try:
                    msg_limit_result = await rate_limiter.check_rate_limit(
                        team_id=team_id,
                        resource="chat",
                        limit=_RATE_LIMIT_PER_MINUTE,
                        window_seconds=60,
                    )
                    if not msg_limit_result.allowed:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "content": "Rate limit exceeded",
                                "error_code": 4029,
                            }
                        )
                        continue
                except Exception:
                    pass  # Graceful degradation

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "cancel":
                if active_task["current"] is not None and not active_task["current"].done():
                    active_task["current"].cancel()
                    logger.info(
                        "ws_cancel_requested: request_id=%s, agent_slug=%s",
                        request_id,
                        agent_slug,
                    )

            elif msg_type == "message":
                content = data.get("content", "")
                conversation_id_str = data.get("conversation_id")
                conversation_id = UUID(conversation_id_str) if conversation_id_str else None

                active_task["current"] = asyncio.create_task(
                    run_streaming(content, conversation_id)
                )

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "content": f"Unknown message type: {msg_type}",
                    }
                )

    except WebSocketDisconnect:
        logger.info(
            "ws_disconnected: request_id=%s, agent_slug=%s, user_id=%s",
            request_id,
            agent_slug,
            user.id,
        )
    except Exception as e:
        logger.exception(
            "ws_error: request_id=%s, error=%s",
            request_id,
            str(e),
        )
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "content": f"WebSocket error: {str(e)}",
                }
            )
        except Exception:
            pass


async def _extract_memories(
    extractor: "MemoryExtractor",
    messages: list[dict[str, str]],
    team_id: UUID,
    agent_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    request_id: str,
) -> None:
    """Fire-and-forget memory extraction from conversation messages.

    Runs asynchronously after the chat response is returned. Errors are
    logged but never propagated to the caller.

    Args:
        extractor: MemoryExtractor instance for double-pass extraction.
        messages: Conversation messages as role/content dicts.
        team_id: Team scope for extracted memories.
        agent_id: Agent scope for extracted memories.
        user_id: User scope for extracted memories.
        conversation_id: Source conversation UUID.
        request_id: Request ID for log correlation.
    """
    try:
        result = await extractor.extract_from_conversation(
            messages=messages,
            team_id=team_id,
            agent_id=agent_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        logger.info(
            "chat_extraction_complete: request_id=%s, created=%d, "
            "versioned=%d, skipped=%d, contradictions=%d",
            request_id,
            result.memories_created,
            result.memories_versioned,
            result.duplicates_skipped,
            result.contradictions_found,
        )
    except Exception as e:
        logger.error(
            "chat_extraction_error: request_id=%s, error=%s",
            request_id,
            str(e),
        )
