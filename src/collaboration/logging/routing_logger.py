"""Routing decision logger for MoE router analysis and debugging."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import and_, select

from src.db.models.collaboration import RoutingDecisionLogORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RoutingLogger:
    """Logs routing decisions made by the MoE router for analysis.

    Provides methods to record routing decisions, query history, and analyze
    routing patterns. Supports debugging and optimization of agent selection.

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session

    async def log_routing_decision(
        self,
        conversation_id: UUID,
        user_message: str,
        selected_agent_id: UUID,
        scores: dict[str, float],
        routing_confidence: float,
        routing_strategy: str = "moe_gate",
        decision_time_ms: int = 0,
    ) -> None:
        """Log a routing decision made by the MoE router.

        Creates a new routing decision log entry with all relevant metadata
        for later analysis and debugging.

        Args:
            conversation_id: UUID of the conversation.
            user_message: The user's message that was routed.
            selected_agent_id: UUID of the agent selected by the router.
            scores: Dict mapping agent IDs to their routing scores.
            routing_confidence: Confidence score (0.0 - 1.0) for the routing decision.
            routing_strategy: Strategy used for routing (default: "moe_gate").
            decision_time_ms: Time taken to make routing decision in milliseconds.
        """
        # Create hash of user message for pattern analysis (first 16 chars)
        query_hash = hashlib.sha256(user_message.encode()).hexdigest()[:16]

        log_entry = RoutingDecisionLogORM(
            conversation_id=conversation_id,
            user_message=user_message,
            selected_agent_id=selected_agent_id,
            scores=scores,
            routing_confidence=routing_confidence,
            routing_strategy=routing_strategy,
            decision_time_ms=decision_time_ms,
        )
        self._session.add(log_entry)
        await self._session.flush()

        logger.info(
            f"routing_logged: query_hash={query_hash}, selected={selected_agent_id}, "
            f"confidence={routing_confidence:.2f}, strategy={routing_strategy}"
        )

    async def get_decision_history(
        self,
        conversation_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> list[RoutingDecisionLogORM]:
        """Query past routing decisions with optional filters.

        Args:
            conversation_id: Filter by conversation (optional).
            agent_id: Filter by selected agent (optional).
            limit: Maximum number of results to return.
            since: Only return decisions made after this timestamp (optional).

        Returns:
            List of RoutingDecisionLogORM entries matching the filters.
        """
        filters = []

        if conversation_id is not None:
            filters.append(RoutingDecisionLogORM.conversation_id == conversation_id)

        if agent_id is not None:
            filters.append(RoutingDecisionLogORM.selected_agent_id == agent_id)

        if since is not None:
            filters.append(RoutingDecisionLogORM.created_at >= since)

        stmt = select(RoutingDecisionLogORM)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(RoutingDecisionLogORM.created_at.desc()).limit(limit)

        result = await self._session.execute(stmt)
        decisions = list(result.scalars().all())

        logger.info(
            f"decision_history_retrieved: count={len(decisions)}, "
            f"conversation_id={conversation_id}, agent_id={agent_id}"
        )

        return decisions

    async def analyze_routing_patterns(
        self, lookback_days: int = 7
    ) -> dict[str, Any]:
        """Aggregate statistics on routing patterns.

        Calculates success rates, average confidence, and decision times
        per agent over the specified lookback period.

        Args:
            lookback_days: Number of days to analyze (default: 7).

        Returns:
            Dict with routing statistics:
            {
                "total_decisions": int,
                "avg_confidence": float,
                "avg_decision_time_ms": float,
                "by_agent": {
                    "agent_id": {
                        "count": int,
                        "success_rate": float,
                        "avg_confidence": float
                    }
                }
            }
        """
        since = datetime.utcnow() - timedelta(days=lookback_days)

        # Get all decisions in the lookback period
        stmt = (
            select(RoutingDecisionLogORM)
            .where(RoutingDecisionLogORM.created_at >= since)
            .order_by(RoutingDecisionLogORM.created_at.desc())
        )

        result = await self._session.execute(stmt)
        decisions = list(result.scalars().all())

        if not decisions:
            logger.info("analyze_routing_patterns: no decisions found")
            return {
                "total_decisions": 0,
                "avg_confidence": 0.0,
                "avg_decision_time_ms": 0.0,
                "by_agent": {},
            }

        # Calculate overall stats
        total_decisions = len(decisions)
        avg_confidence = sum(d.routing_confidence for d in decisions) / total_decisions
        avg_decision_time = sum(d.decision_time_ms for d in decisions) / total_decisions

        # Calculate per-agent stats
        by_agent: dict[str, dict[str, Any]] = {}

        for decision in decisions:
            agent_str = str(decision.selected_agent_id)
            if agent_str not in by_agent:
                by_agent[agent_str] = {
                    "count": 0,
                    "total_confidence": 0.0,
                    "success_rate": 0.0,
                }

            by_agent[agent_str]["count"] += 1
            by_agent[agent_str]["total_confidence"] += decision.routing_confidence

        # Calculate success rate and avg confidence per agent
        for agent_id, stats in by_agent.items():
            stats["success_rate"] = self._calculate_success_rate(
                stats["count"], total_decisions
            )
            stats["avg_confidence"] = stats["total_confidence"] / stats["count"]
            # Remove temporary field
            del stats["total_confidence"]

        logger.info(
            f"analyze_routing_patterns: total={total_decisions}, "
            f"avg_confidence={avg_confidence:.2f}, agents={len(by_agent)}"
        )

        return {
            "total_decisions": total_decisions,
            "avg_confidence": round(avg_confidence, 3),
            "avg_decision_time_ms": round(avg_decision_time, 2),
            "by_agent": by_agent,
        }

    def _calculate_success_rate(self, success_count: int, total_count: int) -> float:
        """Calculate success rate as a percentage.

        Args:
            success_count: Number of successful operations.
            total_count: Total number of operations.

        Returns:
            Success rate as a float (0.0 - 1.0).
        """
        if total_count == 0:
            return 0.0
        return round(success_count / total_count, 3)
