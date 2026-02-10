"""Dependencies for Skill-Based Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional
import logging
from pathlib import Path

from src.skill_loader import SkillLoader
from src.settings import load_settings

if TYPE_CHECKING:
    # Phase 2: Memory system imports
    from src.memory.embedding import EmbeddingService
    from src.db.repositories.memory_repo import MemoryRepository
    from src.memory.memory_log import MemoryAuditLog
    from src.memory.contradiction import ContradictionDetector
    from src.memory.tier_manager import TierManager
    from src.memory.token_budget import TokenBudgetManager
    from src.memory.retrieval import MemoryRetriever
    from src.memory.storage import MemoryExtractor
    from src.memory.compaction_shield import CompactionShield
    from src.memory.prompt_builder import MemoryPromptBuilder

    # Phase 2: MoE routing imports
    from src.moe.complexity_scorer import QueryComplexityScorer
    from src.moe.model_router import ModelRouter
    from src.moe.cost_guard import CostGuard

    # Phase 3: Cache imports
    from src.cache.client import RedisManager
    from src.cache.hot_cache import HotMemoryCache
    from src.cache.working_memory import WorkingMemoryCache
    from src.cache.embedding_cache import EmbeddingCache
    from src.cache.rate_limiter import RateLimiter

    # Phase 7: Collaboration system imports
    from src.collaboration.routing.agent_router import AgentRouter
    from src.moe.expert_gate import ExpertGate
    from src.collaboration.aggregation.response_aggregator import ResponseAggregator
    from src.collaboration.routing.agent_directory import AgentDirectory
    from src.collaboration.coordination.handoff_manager import HandoffManager
    from src.collaboration.coordination.multi_agent_manager import MultiAgentManager
    from src.collaboration.delegation.delegation_manager import DelegationManager

logger = logging.getLogger(__name__)


@dataclass
class AgentDependencies:
    """Dependencies injected into the agent context."""

    # Skill system
    skill_loader: Optional[SkillLoader] = None

    # Session context
    session_id: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # Configuration
    settings: Optional[Any] = None

    # Memory system (Phase 2 - initialized externally)
    embedding_service: Optional["EmbeddingService"] = None
    memory_repo: Optional["MemoryRepository"] = None
    audit_log: Optional["MemoryAuditLog"] = None
    contradiction_detector: Optional["ContradictionDetector"] = None
    tier_manager: Optional["TierManager"] = None
    token_budget: Optional["TokenBudgetManager"] = None
    memory_retriever: Optional["MemoryRetriever"] = None
    memory_extractor: Optional["MemoryExtractor"] = None
    compaction_shield: Optional["CompactionShield"] = None
    prompt_builder: Optional["MemoryPromptBuilder"] = None

    # MoE routing (Phase 2 - initialized externally)
    complexity_scorer: Optional["QueryComplexityScorer"] = None
    model_router: Optional["ModelRouter"] = None
    cost_guard: Optional["CostGuard"] = None

    # Cache layer (Phase 3 - initialized externally)
    redis_manager: Optional["RedisManager"] = None
    hot_cache: Optional["HotMemoryCache"] = None
    working_memory: Optional["WorkingMemoryCache"] = None
    embedding_cache: Optional["EmbeddingCache"] = None
    rate_limiter: Optional["RateLimiter"] = None

    # Collaboration system (Phase 7 - initialized externally)
    router: Optional["AgentRouter"] = None
    expert_gate: Optional["ExpertGate"] = None
    aggregator: Optional["ResponseAggregator"] = None
    directory: Optional["AgentDirectory"] = None
    handoff: Optional["HandoffManager"] = None
    multi_agent: Optional["MultiAgentManager"] = None
    delegator: Optional["DelegationManager"] = None

    async def initialize(self) -> None:
        """
        Initialize skill loader and settings.

        Raises:
            ValueError: If settings cannot be loaded
        """
        if not self.settings:
            self.settings = load_settings()
            logger.info(f"settings_loaded: skills_dir={self.settings.skills_dir}")

        if not self.skill_loader:
            skills_dir = Path(self.settings.skills_dir)
            self.skill_loader = SkillLoader(skills_dir)
            skills = self.skill_loader.discover_skills()

            logger.info(f"skill_loader_initialized: skills_count={len(skills)}")

            # Log discovered skills
            for skill in skills:
                logger.debug(f"skill_available: name={skill.name}, description={skill.description}")

    def set_user_preference(self, key: str, value: Any) -> None:
        """
        Set a user preference for the session.

        Args:
            key: Preference key
            value: Preference value
        """
        self.user_preferences[key] = value

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """
        Get a user preference.

        Args:
            key: Preference key
            default: Default value if key not found

        Returns:
            Preference value or default
        """
        return self.user_preferences.get(key, default)
