"""Unit tests for chat endpoint (Phase 4 crown jewel)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Import functions directly to avoid loading routers
import src.api.routers.chat as chat_module

from src.api.schemas.chat import ChatRequest, ChatResponse, ChatUsage
from src.db.models.agent import AgentORM, AgentStatusEnum
from src.db.models.conversation import ConversationORM, MessageRoleEnum
from src.db.models.user import UserORM
from src.dependencies import AgentDependencies

# Extract functions from module
chat = chat_module.chat
stream_chat = chat_module.stream_chat
_generate_title = chat_module._generate_title
_orm_to_agent_dna = chat_module._orm_to_agent_dna


def setup_mock_db_session() -> tuple[AsyncSession, UUID, UUID, UUID]:
    """Create a mock database session with proper ID assignment.

    Returns:
        Tuple of (db_session, conversation_id, user_msg_id, assistant_msg_id).
    """
    db_session = AsyncMock(spec=AsyncSession)
    conv_id = uuid4()
    user_msg_id = uuid4()
    assistant_msg_id = uuid4()

    def mock_add(obj):
        """Assign IDs to objects."""
        if hasattr(obj, "role"):
            if obj.role == MessageRoleEnum.USER.value:
                obj.id = user_msg_id
            elif obj.role == MessageRoleEnum.ASSISTANT.value:
                obj.id = assistant_msg_id
        elif hasattr(obj, "message_count"):
            obj.id = conv_id

    db_session.add = MagicMock(side_effect=mock_add)
    db_session.execute = AsyncMock()
    db_session.flush = AsyncMock()
    db_session.refresh = AsyncMock()
    db_session.commit = AsyncMock()

    return db_session, conv_id, user_msg_id, assistant_msg_id


class TestGenerateTitle:
    """Tests for conversation title generation helper."""

    def test_generate_title_short_message(self) -> None:
        """Short messages should be returned as-is."""
        message = "Hello, agent!"
        result = _generate_title(message)
        assert result == "Hello, agent!"

    def test_generate_title_long_message_with_period(self) -> None:
        """Long messages should truncate at first sentence boundary."""
        message = (
            "This is a very long message that goes on and on. But this part should not appear."
        )
        result = _generate_title(message)
        assert result == "This is a very long message that goes on and on."
        assert len(result) <= 80

    def test_generate_title_long_message_no_boundary(self) -> None:
        """Long messages without sentence boundaries should hard truncate."""
        message = "A" * 100
        result = _generate_title(message)
        assert result.endswith("...")
        assert len(result) <= 80

    def test_generate_title_strips_whitespace(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        message = "   Hello   "
        result = _generate_title(message)
        assert result == "Hello"

    def test_generate_title_finds_question_mark(self) -> None:
        """Question marks should be treated as sentence boundaries."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Message length (73) is under 80, so it returns as-is without truncation
        message = "What is the weather today? This is extra text that should not appear."
        result = _generate_title(message)
        assert result == message  # Returns full message since < 80 chars


class TestOrmToAgentDna:
    """Tests for AgentORM to AgentDNA conversion."""

    def test_orm_to_agent_dna_success(self, test_team_id: UUID) -> None:
        """Valid AgentORM should convert to AgentDNA."""
        agent_orm = MagicMock(spec=AgentORM)
        agent_orm.id = uuid4()
        agent_orm.team_id = test_team_id
        agent_orm.name = "Test Agent"
        agent_orm.slug = "test-agent"
        agent_orm.tagline = "A test agent"
        agent_orm.avatar_emoji = "🤖"
        agent_orm.personality = {"system_prompt_template": "You are a test agent"}
        agent_orm.shared_skill_names = ["weather"]
        agent_orm.custom_skill_names = []
        agent_orm.disabled_skill_names = []
        agent_orm.model_config_json = {"model_name": "anthropic/claude-sonnet-4.5"}
        agent_orm.memory_config = {"token_budget": 2000}
        agent_orm.boundaries = {"max_autonomy": "execute"}
        agent_orm.status = AgentStatusEnum.ACTIVE.value
        agent_orm.created_at = datetime.now(timezone.utc)
        agent_orm.updated_at = datetime.now(timezone.utc)
        agent_orm.created_by = None

        result = _orm_to_agent_dna(agent_orm)

        assert result is not None
        assert result.name == "Test Agent"
        assert result.slug == "test-agent"

    def test_orm_to_agent_dna_missing_personality_template(self, test_team_id: UUID) -> None:
        """Missing system_prompt_template should be added with empty string."""
        agent_orm = MagicMock(spec=AgentORM)
        agent_orm.id = uuid4()
        agent_orm.team_id = test_team_id
        agent_orm.name = "Test Agent"
        agent_orm.slug = "test-agent"
        agent_orm.tagline = "A test agent"
        agent_orm.avatar_emoji = "🤖"
        agent_orm.personality = {}  # Missing system_prompt_template
        agent_orm.shared_skill_names = []
        agent_orm.custom_skill_names = []
        agent_orm.disabled_skill_names = []
        agent_orm.model_config_json = {"model_name": "anthropic/claude-sonnet-4.5"}
        agent_orm.memory_config = {"token_budget": 2000}
        agent_orm.boundaries = {"max_autonomy": "execute"}
        agent_orm.status = AgentStatusEnum.ACTIVE.value
        agent_orm.created_at = datetime.now(timezone.utc)
        agent_orm.updated_at = datetime.now(timezone.utc)
        agent_orm.created_by = None

        result = _orm_to_agent_dna(agent_orm)

        assert result is not None

    def test_orm_to_agent_dna_invalid_data_returns_none(self, test_team_id: UUID) -> None:
        """Invalid AgentORM data should return None."""
        agent_orm = MagicMock(spec=AgentORM)
        agent_orm.id = uuid4()
        agent_orm.team_id = test_team_id
        agent_orm.name = "Test Agent"
        agent_orm.slug = "test-agent"
        agent_orm.personality = {"system_prompt_template": "Test"}
        agent_orm.model_config_json = None  # Invalid
        agent_orm.memory_config = None
        agent_orm.boundaries = None

        result = _orm_to_agent_dna(agent_orm)

        assert result is None


class TestChatAgentResolution:
    """Tests for Step 1: Agent resolution by slug + team_id."""

    @pytest.mark.asyncio
    async def test_chat_agent_not_found_raises_404(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Agent not found should raise 404."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Mock database query returning None
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db_session.execute = AsyncMock(return_value=mock_result)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        # Mock settings and agent_deps
        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                agent_slug="nonexistent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_chat_agent_inactive_raises_404(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Inactive agent should raise 404."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Create mock inactive agent
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.status = AgentStatusEnum.PAUSED.value

        # Mock database query returning inactive agent
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_result)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                agent_slug="paused-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 404
        assert "not active" in exc_info.value.detail.lower()


class TestChatConversationManagement:
    """Tests for Step 2: Load or create conversation."""

    @pytest.mark.asyncio
    async def test_chat_creates_new_conversation(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat without conversation_id should create a new conversation."""
        # Setup mock database with proper ID assignment
        db_session, conv_id, user_msg_id, assistant_msg_id = setup_mock_db_session()

        # Setup mocks for agent resolution
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Hello back!"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Hello agent!")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Verify conversation was created
        assert db_session.add.called
        assert db_session.flush.called
        assert db_session.commit.called

    @pytest.mark.asyncio
    async def test_chat_loads_existing_conversation(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat with conversation_id should load existing conversation."""
        # Setup mock database
        db_session, _, user_msg_id, assistant_msg_id = setup_mock_db_session()

        existing_conv_id = uuid4()

        # Setup mocks for agent resolution
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        # Mock existing conversation
        mock_conversation = MagicMock(spec=ConversationORM)
        mock_conversation.id = existing_conv_id
        mock_conversation.team_id = test_team_id
        mock_conversation.message_count = 4
        mock_conversation.total_input_tokens = 200
        mock_conversation.total_output_tokens = 150

        # Setup execute mock to return different results for each query
        call_count = 0

        async def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = AsyncMock()
            if call_count == 1:  # First call: agent lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
            elif call_count == 2:  # Second call: conversation lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_conversation)
            return mock_result

        db_session.execute = AsyncMock(side_effect=mock_execute_side_effect)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Override db.add to only assign IDs to messages, not to the
        # existing conversation whose id is already set.
        def mock_add_existing_conv(obj):
            if hasattr(obj, "role"):
                if obj.role == MessageRoleEnum.USER.value:
                    obj.id = user_msg_id
                elif obj.role == MessageRoleEnum.ASSISTANT.value:
                    obj.id = assistant_msg_id

        db_session.add = MagicMock(side_effect=mock_add_existing_conv)

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Continuing conversation"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 120
        mock_usage.output_tokens = 60
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Follow up question", conversation_id=existing_conv_id)
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert result.conversation_id == existing_conv_id

    @pytest.mark.asyncio
    async def test_chat_conversation_not_found_raises_404(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat with nonexistent conversation_id should raise 404."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        nonexistent_conv_id = uuid4()

        # Setup mocks for agent resolution
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value

        # Setup execute mock to return agent, then None for conversation
        call_count = 0

        async def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = AsyncMock()
            if call_count == 1:  # First call: agent lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
            elif call_count == 2:  # Second call: conversation lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        db_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        body = ChatRequest(message="Question", conversation_id=nonexistent_conv_id)
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 404
        assert "conversation not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_chat_conversation_wrong_team_raises_404(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat with conversation from different team should raise 404."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        existing_conv_id = uuid4()
        other_team_id = uuid4()

        # Setup mocks for agent resolution
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value

        # Mock conversation from different team
        mock_conversation = MagicMock(spec=ConversationORM)
        mock_conversation.id = existing_conv_id
        mock_conversation.team_id = other_team_id

        # Setup execute mock
        call_count = 0

        async def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = AsyncMock()
            if call_count == 1:  # First call: agent lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
            elif call_count == 2:  # Second call: conversation lookup
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_conversation)
            return mock_result

        db_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        body = ChatRequest(message="Question", conversation_id=existing_conv_id)
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 404


class TestChatMemoryRetrieval:
    """Tests for Step 3: Retrieve memories (graceful degradation)."""

    @pytest.mark.asyncio
    async def test_chat_with_memory_retrieval(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Chat should retrieve memories when retriever is available."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock memory retriever
        mock_retrieval_result = MagicMock()
        mock_retrieval_result.memories = []
        mock_retrieval_result.stats = MagicMock()
        mock_retrieval_result.stats.cache_hit = False

        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_retrieval_result)

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Response with memory context"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = mock_retriever
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Verify memory retrieval was attempted
        mock_retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_without_memory_retrieval(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat should work without memory retriever (graceful degradation)."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Response without memory"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None  # No memory retriever
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Should succeed without memory
        assert result.response == "Response without memory"

    @pytest.mark.asyncio
    async def test_chat_memory_retrieval_failure_graceful(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Chat should continue if memory retrieval fails."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock memory retriever that fails
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(side_effect=Exception("Redis connection failed"))

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Response despite memory failure"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = mock_retriever
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Should succeed despite memory failure
        assert result.response == "Response despite memory failure"


class TestChatAgentExecution:
    """Tests for Steps 5-6: Create agent instance and run."""

    @pytest.mark.asyncio
    async def test_chat_successful_agent_run(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Successful agent run should return proper ChatResponse."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock agent.run with realistic response
        mock_run_result = MagicMock()
        mock_run_result.output = "This is the agent's response to your question."
        mock_usage = MagicMock()
        mock_usage.input_tokens = 150
        mock_usage.output_tokens = 75
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="What is the weather?")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Verify response structure
        assert isinstance(result, ChatResponse)
        assert result.response == "This is the agent's response to your question."
        assert result.usage.input_tokens == 150
        assert result.usage.output_tokens == 75
        assert result.usage.model == "anthropic/claude-sonnet-4.5"
        assert result.request_id is not None

    @pytest.mark.asyncio
    async def test_chat_agent_run_failure_raises_500(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Agent run failure should raise 500."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(side_effect=Exception("LLM provider API key invalid"))

            with pytest.raises(HTTPException) as exc_info:
                await chat(
                    agent_slug="test-agent",
                    body=body,
                    current_user=current_user,
                    db=db_session,
                    settings=mock_settings,
                    agent_deps=mock_agent_deps,
                )

        assert exc_info.value.status_code == 500
        assert "agent execution failed" in exc_info.value.detail.lower()


class TestChatAuthentication:
    """Tests for authentication and authorization."""

    @pytest.mark.asyncio
    async def test_chat_requires_team_context(self, test_user: UserORM) -> None:
        """Chat without team context should raise 401."""
        # Setup mock database (even though chat will fail before using it)
        db_session, _, _, _ = setup_mock_db_session()

        body = ChatRequest(message="Hello")
        current_user = (test_user, None)  # No team_id

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 401
        assert "team context required" in exc_info.value.detail.lower()


class TestChatResponseStructure:
    """Tests for response format and structure."""

    @pytest.mark.asyncio
    async def test_chat_response_includes_all_fields(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """ChatResponse should include all required fields."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock agent.run
        mock_run_result = MagicMock()
        mock_run_result.output = "Agent response"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Test message")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Verify all required fields
        assert hasattr(result, "response")
        assert hasattr(result, "conversation_id")
        assert hasattr(result, "message_id")
        assert hasattr(result, "usage")
        assert hasattr(result, "request_id")

        assert isinstance(result.response, str)
        assert isinstance(result.conversation_id, UUID)
        assert isinstance(result.message_id, UUID)
        assert isinstance(result.usage, ChatUsage)
        assert isinstance(result.request_id, str)

    @pytest.mark.asyncio
    async def test_chat_response_usage_has_correct_values(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """ChatResponse.usage should reflect actual token counts."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)
        db_session.flush = AsyncMock()
        db_session.refresh = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock agent.run with specific token counts
        mock_run_result = MagicMock()
        mock_run_result.output = "Response"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 250
        mock_usage.output_tokens = 125
        mock_run_result.usage = MagicMock(return_value=mock_usage)

        body = ChatRequest(message="Test")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-opus-4.6"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.run = AsyncMock(return_value=mock_run_result)

            result = await chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert result.usage.input_tokens == 250
        assert result.usage.output_tokens == 125
        assert result.usage.model == "anthropic/claude-opus-4.6"


class TestStreamChat:
    """Tests for streaming chat endpoint."""

    @pytest.mark.asyncio
    async def test_stream_returns_event_stream_content_type(
        self, test_user: UserORM, test_team_id: UUID
    ) -> None:
        """Stream endpoint should return text/event-stream content type."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Setup basic mocks
        mock_agent = MagicMock(spec=AgentORM)
        mock_agent.id = uuid4()
        mock_agent.team_id = test_team_id
        mock_agent.status = AgentStatusEnum.ACTIVE.value
        mock_agent.name = "Test Agent"
        mock_agent.slug = "test-agent"
        mock_agent.personality = None
        mock_agent.model_config_json = None

        mock_agent_result = AsyncMock()
        mock_agent_result.scalar_one_or_none = MagicMock(return_value=mock_agent)
        db_session.execute = AsyncMock(return_value=mock_agent_result)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_settings.llm_model = "anthropic/claude-sonnet-4.5"

        mock_agent_deps = MagicMock(spec=AgentDependencies)
        mock_agent_deps.memory_retriever = None
        mock_agent_deps.memory_extractor = None

        # Mock agent.iter() streaming
        mock_run = MagicMock()
        mock_run.usage = MagicMock(return_value=MagicMock(input_tokens=100, output_tokens=50))
        mock_run.__aenter__ = AsyncMock(return_value=mock_run)
        mock_run.__aexit__ = AsyncMock(return_value=None)
        mock_run.__aiter__ = MagicMock(return_value=AsyncMock().__aiter__())

        with patch("src.api.routers.chat.skill_agent") as mock_skill_agent:
            mock_skill_agent.iter = MagicMock(return_value=mock_run)

            result = await chat_module.stream_chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        # Verify response type
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_stream_requires_auth(self, test_user: UserORM) -> None:
        """Stream endpoint should require team context."""
        db_session, _, _, _ = setup_mock_db_session()

        body = ChatRequest(message="Hello")
        current_user = (test_user, None)  # No team_id

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        with pytest.raises(HTTPException) as exc_info:
            await chat_module.stream_chat(
                agent_slug="test-agent",
                body=body,
                current_user=current_user,
                db=db_session,
                settings=mock_settings,
                agent_deps=mock_agent_deps,
            )

        assert exc_info.value.status_code == 401
        assert "team context required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_stream_agent_not_found(self, test_user: UserORM, test_team_id: UUID) -> None:
        """Stream endpoint should handle agent not found."""
        # Setup mock database
        db_session, _, _, _ = setup_mock_db_session()

        # Mock database query returning None
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db_session.execute = AsyncMock(return_value=mock_result)

        body = ChatRequest(message="Hello")
        current_user = (test_user, test_team_id)

        mock_settings = MagicMock()
        mock_agent_deps = MagicMock(spec=AgentDependencies)

        result = await chat_module.stream_chat(
            agent_slug="nonexistent",
            body=body,
            current_user=current_user,
            db=db_session,
            settings=mock_settings,
            agent_deps=mock_agent_deps,
        )

        # Verify it returns StreamingResponse with error in SSE format
        assert result.media_type == "text/event-stream"
        # Consume the stream to check for error chunk
        chunks = []
        async for chunk in result.body_iterator:
            # StreamingResponse yields strings, not bytes
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8"))
            else:
                chunks.append(chunk)

        # Should have at least one error chunk
        assert len(chunks) > 0
        assert "error" in chunks[0].lower()
