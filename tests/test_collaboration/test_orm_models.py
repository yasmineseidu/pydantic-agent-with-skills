"""Tests for collaboration ORM models and constraints."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import CheckConstraint, UniqueConstraint

from src.db.models import (
    AgentHandoffORM,
    AgentMessageORM,
    AgentTaskORM,
    CollaborationParticipantV2ORM,
    CollaborationSessionORM,
    ConversationParticipantORM,
    RoutingDecisionLogORM,
)


def _constraint_names(table) -> set[str]:
    return {c.name for c in table.constraints if c.name}


def test_conversation_participant_constraints() -> None:
    """ConversationParticipant has unique constraint."""
    names = _constraint_names(ConversationParticipantORM.__table__)
    assert "uq_participant_conversation_agent" in names


def test_agent_task_constraints_present() -> None:
    """AgentTask has delegation depth and no self-assign constraints."""
    names = _constraint_names(AgentTaskORM.__table__)
    assert "ck_task_delegation_depth" in names
    assert "ck_task_no_self_assign" in names


def test_collaboration_participant_unique() -> None:
    """CollaborationParticipantV2 has unique constraint on session+agent."""
    names = _constraint_names(CollaborationParticipantV2ORM.__table__)
    assert "uq_collab_session_agent" in names


def test_models_instantiation() -> None:
    """Instantiate ORM models without hitting the DB."""
    conv_id = uuid4()
    agent_a = uuid4()
    agent_b = uuid4()

    ConversationParticipantORM(conversation_id=conv_id, agent_id=agent_a)
    AgentHandoffORM(
        conversation_id=conv_id,
        from_agent_id=agent_a,
        to_agent_id=agent_b,
        reason="handoff",
        context_transferred={},
    )
    RoutingDecisionLogORM(
        conversation_id=conv_id,
        user_message="route",
        selected_agent_id=agent_b,
        scores={},
        routing_confidence=0.5,
    )
    AgentTaskORM(
        conversation_id=conv_id,
        created_by_agent_id=agent_a,
        assigned_to_agent_id=agent_b,
        title="task",
        description="desc",
        status="pending",
        priority=5,
        delegation_depth=0,
    )
    AgentMessageORM(
        conversation_id=conv_id,
        from_agent_id=agent_a,
        to_agent_id=agent_b,
        message_type="info",
        subject="subject",
        body="body",
        metadata_json={},
    )
    CollaborationSessionORM(
        conversation_id=conv_id,
        session_type="pipeline",
        goal="goal",
        status="active",
        stage_outputs={},
        total_cost=0.0,
        total_duration_ms=0,
    )
    CollaborationParticipantV2ORM(
        session_id=uuid4(),
        agent_id=agent_a,
        role="participant",
        contribution_summary="",
        turn_count=0,
        cost_incurred=0.0,
    )


def test_constraints_are_expected_types() -> None:
    """Ensure constraint objects are present on tables."""
    assert any(
        isinstance(c, UniqueConstraint) for c in ConversationParticipantORM.__table__.constraints
    )
    assert any(isinstance(c, CheckConstraint) for c in AgentTaskORM.__table__.constraints)
