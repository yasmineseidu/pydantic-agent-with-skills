"""Tests for collaboration ORM model exports."""

from __future__ import annotations

from src.db.models import (
    AgentHandoffORM,
    AgentMessageORM,
    AgentTaskORM,
    CollaborationParticipantV2ORM,
    CollaborationSessionORM,
    ConversationParticipantORM,
    RoutingDecisionLogORM,
)


def test_collaboration_models_exported() -> None:
    """Collaboration ORM models should be importable from db.models."""
    assert ConversationParticipantORM.__name__ == "ConversationParticipantORM"
    assert AgentHandoffORM.__name__ == "AgentHandoffORM"
    assert RoutingDecisionLogORM.__name__ == "RoutingDecisionLogORM"
    assert AgentTaskORM.__name__ == "AgentTaskORM"
    assert AgentMessageORM.__name__ == "AgentMessageORM"
    assert CollaborationSessionORM.__name__ == "CollaborationSessionORM"
    assert CollaborationParticipantV2ORM.__name__ == "CollaborationParticipantV2ORM"
