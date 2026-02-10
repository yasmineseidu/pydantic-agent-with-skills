"""Tests for collaboration Pydantic models and enums."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.collaboration import models as collab_models


def test_enum_values_match_expected() -> None:
    """Enums expose expected string values."""
    assert collab_models.ParticipantRole.PRIMARY.value == "primary"
    assert collab_models.AgentTaskStatus.IN_PROGRESS.value == "in_progress"
    assert collab_models.TaskPriority.URGENT.value == "urgent"
    assert collab_models.AgentMessageType.TASK_REQUEST.value == "task_request"
    assert collab_models.CollaborationPattern.SUPERVISOR_WORKER.value == "supervisor_worker"
    assert collab_models.CollaborationStatus.SYNTHESIZING.value == "synthesizing"
    assert collab_models.ReportType.CODE_REVIEW.value == "code_review"


def test_constants_present() -> None:
    """Constants use expected defaults."""
    assert collab_models.MAX_DELEGATION_DEPTH == 3
    assert collab_models.MAX_CONCURRENT_TASKS == 5


def test_routing_decision_model() -> None:
    """RoutingDecision model stores expected fields."""
    decision = collab_models.RoutingDecision(
        selected_agent_id=uuid4(),
        confidence=0.75,
        reasoning="Best skill match",
        alternatives=[uuid4()],
    )
    assert 0.0 <= decision.confidence <= 1.0
    assert decision.reasoning


def test_agent_task_model_validation() -> None:
    """AgentTask enforces delegation depth bounds."""
    task = collab_models.AgentTask(
        id=uuid4(),
        task_type=collab_models.AgentTaskType.EXECUTE,
        description="Test",
        status=collab_models.AgentTaskStatus.PENDING,
        priority=collab_models.TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        depth=2,
        timeout_seconds=120,
    )
    assert task.depth == 2

    with pytest.raises(ValueError):
        collab_models.AgentTask(
            id=uuid4(),
            task_type=collab_models.AgentTaskType.EXECUTE,
            description="Too deep",
            status=collab_models.AgentTaskStatus.PENDING,
            priority=collab_models.TaskPriority.NORMAL,
            assigned_to=uuid4(),
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            depth=collab_models.MAX_DELEGATION_DEPTH + 1,
            timeout_seconds=120,
        )


def test_report_templates_present() -> None:
    """Report templates include required keys and types."""
    templates = collab_models.REPORT_TEMPLATES
    assert "CODE_REVIEW" in templates
    assert "RESEARCH_SUMMARY" in templates
    assert "RISK_ASSESSMENT" in templates

    template = templates["CODE_REVIEW"]
    assert template.report_type == collab_models.ReportType.CODE_REVIEW
    assert template.sections
