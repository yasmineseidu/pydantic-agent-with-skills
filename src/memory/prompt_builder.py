"""Seven-layer memory-aware prompt builder."""

import logging
import math

from src.memory.types import Contradiction, RetrievalResult, ScoredMemory
from src.models.agent_models import AgentDNA, VoiceExample
from src.models.memory_models import MemoryType
from src.prompts import PERSONALITY_TEMPLATE

logger = logging.getLogger(__name__)


class MemoryPromptBuilder:
    """Builds a 7-layer system prompt respecting a token budget.

    Layers are assembled in priority order with protected layers that
    are never trimmed and trimmable layers that shed content starting
    from the lowest-priority layer when the budget is exceeded.

    Layer priority (highest to lowest):
        L1 - Agent Identity + Personality (protected)
        L2 - Identity Memories (protected)
        L3 - Skill Metadata (protected)
        L4 - User Profile memories (trim reluctantly)
        L5 - Retrieved Memories by type (trimmed by score)
        L6 - Team/Shared Knowledge (trim before L5)
        L7 - Conversation Summary (trimmed FIRST)

    Args:
        token_budget: Maximum tokens for the assembled prompt.
    """

    def __init__(self, token_budget: int = 4000) -> None:
        self._token_budget = token_budget

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using len/3.5 heuristic.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count (>= 1 for non-empty text, 0 for empty).
        """
        if not text:
            return 0
        return math.ceil(len(text) / 3.5)

    def build(
        self,
        agent_dna: AgentDNA,
        skill_metadata: str,
        retrieval_result: RetrievalResult,
        conversation_summary: str = "",
    ) -> str:
        """Construct a 7-layer prompt within the token budget.

        Assembles identity, memories, skills, and context into a single
        prompt string. Protected layers (L1-L3) are never trimmed.
        Trimmable layers are shed in order L7 -> L6 -> L5 -> L4.

        Args:
            agent_dna: Agent identity and personality configuration.
            skill_metadata: Level-1 skill metadata string.
            retrieval_result: Retrieved memories with scores and contradictions.
            conversation_summary: Optional conversation summary text.

        Returns:
            Assembled prompt string trimmed to fit the token budget.
        """
        # Partition memories by type
        identity_memories: list[ScoredMemory] = []
        user_profile_memories: list[ScoredMemory] = []
        shared_memories: list[ScoredMemory] = []
        other_memories: list[ScoredMemory] = []

        for sm in retrieval_result.memories:
            if sm.memory.memory_type == MemoryType.IDENTITY:
                identity_memories.append(sm)
            elif sm.memory.memory_type == MemoryType.USER_PROFILE:
                user_profile_memories.append(sm)
            elif sm.memory.memory_type == MemoryType.SHARED:
                shared_memories.append(sm)
            else:
                other_memories.append(sm)

        # Build contradiction markers
        contradiction_text = self._format_contradictions(retrieval_result.contradictions)

        # L1 - Identity + Personality (PROTECTED)
        layer1 = self._build_identity_layer(agent_dna)

        # L2 - Identity Memories (PROTECTED)
        layer2 = self._format_memories_section(identity_memories, "Identity Memories")

        # L3 - Skill Metadata (PROTECTED)
        layer3 = skill_metadata

        # L4 - User Profile (trim reluctantly)
        layer4 = self._format_memories_section(user_profile_memories, "About This User")

        # L5 - Retrieved Memories by type (trimmed by score)
        layer5 = self._build_retrieved_layer(other_memories, contradiction_text)

        # L6 - Team/Shared Knowledge (trim before L5)
        layer6 = self._format_memories_section(shared_memories, "Team Knowledge")

        # L7 - Conversation Summary (trimmed FIRST)
        layer7 = conversation_summary

        # Assemble with trimming
        layers: list[tuple[str, str, bool]] = [
            ("L1_identity", layer1, True),
            ("L2_identity_memories", layer2, True),
            ("L3_skill_metadata", layer3, True),
            ("L4_user_profile", layer4, False),
            ("L5_retrieved", layer5, False),
            ("L6_team_knowledge", layer6, False),
            ("L7_conversation", layer7, False),
        ]

        trimmed_prompt = self._trim_to_budget(layers, self._token_budget)

        logger.info(
            "build: layers=7 budget=%d result_tokens=%d memories=%d contradictions=%d",
            self._token_budget,
            self.estimate_tokens(trimmed_prompt),
            len(retrieval_result.memories),
            len(retrieval_result.contradictions),
        )

        return trimmed_prompt

    def _build_identity_layer(self, agent_dna: AgentDNA) -> str:
        """Build L1 identity layer from AgentDNA personality.

        Args:
            agent_dna: Agent identity and personality configuration.

        Returns:
            Formatted identity section string.
        """
        voice_examples_section = _format_voice_examples(agent_dna.personality.voice_examples)

        personality_traits = ", ".join(f"{k}: {v}" for k, v in agent_dna.personality.traits.items())

        layer1 = PERSONALITY_TEMPLATE.format(
            agent_name=agent_dna.name,
            agent_tagline=agent_dna.tagline,
            personality_traits=personality_traits,
            tone=agent_dna.personality.tone,
            verbosity=agent_dna.personality.verbosity,
            formality=agent_dna.personality.formality,
            voice_examples_section=voice_examples_section,
            always_rules="\n".join(f"- {r}" for r in agent_dna.personality.always_rules),
            never_rules="\n".join(f"- {r}" for r in agent_dna.personality.never_rules),
            custom_instructions=agent_dna.personality.custom_instructions,
            memory_context="",
            skill_metadata="",
            user_preferences="",
            conversation_summary="",
        )
        return layer1

    def _build_retrieved_layer(
        self,
        memories: list[ScoredMemory],
        contradiction_text: str,
    ) -> str:
        """Build L5 retrieved memories layer grouped by type.

        Groups non-identity, non-profile, non-shared memories by their
        MemoryType and formats each group with a section header.

        Args:
            memories: Scored memories to include (already filtered).
            contradiction_text: Pre-formatted contradiction markers.

        Returns:
            Formatted retrieved memories section.
        """
        if not memories and not contradiction_text:
            return ""

        # Group by memory type
        grouped: dict[MemoryType, list[ScoredMemory]] = {}
        for sm in memories:
            grouped.setdefault(sm.memory.memory_type, []).append(sm)

        sections: list[str] = []

        # Sort groups by type name for deterministic output
        for mem_type in sorted(grouped.keys(), key=lambda t: t.value):
            type_memories = grouped[mem_type]
            # Sort by score descending within each group
            type_memories.sort(key=lambda m: m.final_score, reverse=True)
            header = f"Recalled ({mem_type.value})"
            section = self._format_memories_section(type_memories, header)
            if section:
                sections.append(section)

        if contradiction_text:
            sections.append(contradiction_text)

        return "\n\n".join(sections)

    def _format_memories_section(self, memories: list[ScoredMemory], header: str) -> str:
        """Format a list of scored memories as a markdown section.

        Args:
            memories: Scored memories to format.
            header: Section header text.

        Returns:
            Formatted section string, or empty string if no memories.
        """
        if not memories:
            return ""
        lines: list[str] = [f"### {header}"]
        for sm in memories:
            lines.append(f"- {sm.memory.content}")
        return "\n".join(lines)

    def _format_contradictions(self, contradictions: list[Contradiction]) -> str:
        """Format contradiction markers for prompt injection.

        Args:
            contradictions: Detected contradictions from retrieval.

        Returns:
            Formatted contradiction markers, or empty string if none.
        """
        if not contradictions:
            return ""
        lines: list[str] = []
        for c in contradictions:
            lines.append(f"[FACT DISPUTED]: {c.reason}")
        return "\n".join(lines)

    def _trim_to_budget(self, layers: list[tuple[str, str, bool]], budget: int) -> str:
        """Trim layers to fit within token budget.

        Protected layers (L1, L2, L3) are never trimmed.
        Trim order: L7 first, then L6, then L5, then L4.

        Args:
            layers: List of (name, content, is_protected) tuples.
            budget: Token budget.

        Returns:
            Combined prompt string trimmed to fit the budget.
        """
        # Separate protected and trimmable layers
        protected_parts: list[tuple[str, str]] = []
        trimmable_parts: list[tuple[str, str]] = []

        for name, content, is_protected in layers:
            if is_protected:
                protected_parts.append((name, content))
            else:
                trimmable_parts.append((name, content))

        protected_tokens = sum(self.estimate_tokens(content) for _, content in protected_parts)

        if protected_tokens > budget:
            logger.warning(
                "trim_to_budget: protected_tokens=%d exceeds budget=%d, "
                "including protected layers anyway",
                protected_tokens,
                budget,
            )

        remaining_budget = max(0, budget - protected_tokens)

        # Trim order maps trimmable indices to trim priority:
        # L7 (index 3) trimmed first -> L6 (index 2) -> L5 (index 1) -> L4 (index 0)
        trim_order = [3, 2, 1, 0]

        # Initially include all non-empty trimmable layers
        included_trimmable: dict[int, str] = {}
        tokens_used = 0

        for idx in range(len(trimmable_parts)):
            _name, content = trimmable_parts[idx]
            if not content:
                continue
            layer_tokens = self.estimate_tokens(content)
            included_trimmable[idx] = content
            tokens_used += layer_tokens

        # Shed layers in trim order until within budget
        for trim_idx in trim_order:
            if tokens_used <= remaining_budget:
                break
            if trim_idx in included_trimmable:
                removed_content = included_trimmable.pop(trim_idx)
                removed_tokens = self.estimate_tokens(removed_content)
                tokens_used -= removed_tokens
                layer_name = trimmable_parts[trim_idx][0]
                logger.info(
                    "trim_to_budget: trimmed %s, freed %d tokens",
                    layer_name,
                    removed_tokens,
                )

        # Assemble final prompt: protected layers + surviving trimmable layers
        parts: list[str] = []

        for _, content in protected_parts:
            if content:
                parts.append(content)

        # Add trimmable layers in original order (L4, L5, L6, L7)
        for idx in sorted(included_trimmable.keys()):
            content = included_trimmable[idx]
            if content:
                parts.append(content)

        result = "\n\n".join(parts)

        total_tokens = self.estimate_tokens(result)
        logger.info(
            "trim_to_budget: final_tokens=%d budget=%d protected=%d",
            total_tokens,
            budget,
            protected_tokens,
        )

        return result


def _format_voice_examples(examples: list[VoiceExample]) -> str:
    """Format voice examples for the personality template.

    Args:
        examples: List of voice example exchanges.

    Returns:
        Formatted voice examples section, or empty string if none.
    """
    if not examples:
        return ""
    lines: list[str] = ["\n### Voice Examples"]
    for ex in examples:
        context_note = f" ({ex.context})" if ex.context else ""
        lines.append(f"User{context_note}: {ex.user_message}")
        lines.append(f"You: {ex.agent_response}")
        lines.append("")
    return "\n".join(lines)
