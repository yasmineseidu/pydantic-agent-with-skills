"""Chat endpoint for agent conversations (Phase 4 crown jewel)."""

import asyncio
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPartDelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.agent import Agent, create_skill_agent, skill_agent
from src.api.dependencies import get_agent_deps, get_db, get_settings
from src.api.schemas.chat import ChatRequest, ChatResponse, ChatUsage, StreamChunk
from src.auth.dependencies import get_current_user
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.conversation import (
    ConversationORM,
    ConversationStatusEnum,
    MessageORM,
    MessageRoleEnum,
)
from src.db.models.user import UserORM
from src.dependencies import AgentDependencies
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

    Implements the same 8-step flow as the non-streaming chat endpoint,
    but streams the response incrementally as text deltas.

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
        HTTPException: 404 if agent or conversation not found.
        HTTPException: 400 if conversation does not belong to team.
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
        """Generate Server-Sent Events for streaming response."""
        try:
            # ---------------------------------------------------------------
            # Step 1: Resolve agent by slug + team_id
            # ---------------------------------------------------------------
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
                chunk = StreamChunk(type="error", content=f"Agent '{agent_slug}' not found")
                yield f"data: {chunk.model_dump_json()}\n\n"
                return

            if agent_orm.status != AgentStatusEnum.ACTIVE.value:
                logger.warning(
                    "stream_chat_agent_not_active: request_id=%s, agent_id=%s, status=%s",
                    request_id,
                    agent_orm.id,
                    agent_orm.status,
                )
                chunk = StreamChunk(type="error", content=f"Agent '{agent_slug}' is not active")
                yield f"data: {chunk.model_dump_json()}\n\n"
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
                    chunk = StreamChunk(type="error", content="Conversation not found")
                    yield f"data: {chunk.model_dump_json()}\n\n"
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
                    chunk = StreamChunk(type="error", content="Conversation not found")
                    yield f"data: {chunk.model_dump_json()}\n\n"
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
            if agent_deps.memory_retriever:
                try:
                    await agent_deps.memory_retriever.retrieve(
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
                                if (
                                    isinstance(event, PartStartEvent)
                                    and event.part.part_kind == "text"
                                ):
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
                                        yield f"data: {chunk.model_dump_json()}\n\n"

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
                                        yield f"data: {chunk.model_dump_json()}\n\n"

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
            usage_chunk = StreamChunk(
                type="usage",
                usage=ChatUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model_name,
                ),
            )
            yield f"data: {usage_chunk.model_dump_json()}\n\n"

            # Send done chunk
            done_chunk = StreamChunk(type="done")
            yield f"data: {done_chunk.model_dump_json()}\n\n"

            # ---------------------------------------------------------------
            # Step 8: Trigger async memory extraction (fire and forget)
            # ---------------------------------------------------------------
            if agent_deps.memory_extractor:
                try:
                    messages_for_extraction: list[dict[str, str]] = [
                        {"role": "user", "content": body.message},
                        {"role": "assistant", "content": response_text},
                    ]

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
            error_chunk = StreamChunk(type="error", content=f"Stream failed: {str(e)}")
            yield f"data: {error_chunk.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
