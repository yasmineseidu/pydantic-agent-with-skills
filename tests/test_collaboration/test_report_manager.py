"""Tests for ReportManager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.collaboration.delegation.report_manager import ReportManager
from src.collaboration.models import (
    REPORT_TEMPLATES,
    AgentTask,
    AgentTaskStatus,
    AgentTaskType,
    Report,
    ReportRequest,
    ReportType,
    TaskPriority,
)


@pytest.mark.asyncio
async def test_request_report_with_template() -> None:
    """Test report request uses correct template."""
    # Mock DelegationManager
    mock_delegator = AsyncMock()
    task_id = uuid4()
    mock_task = AgentTask(
        id=task_id,
        task_type=AgentTaskType.GENERATE,
        description="Generate report",
        status=AgentTaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        metadata={},
    )
    mock_delegator.delegate_task = AsyncMock(return_value=mock_task)

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request (template_id uppercase to match REPORT_TEMPLATES keys)
    report_request = ReportRequest(
        report_type=ReportType.CODE_REVIEW,
        title="Test Code Review",
        scope="src/collaboration/",
        template_id="CODE_REVIEW",  # Explicitly uppercase to match dict keys
    )

    # Request report
    result = await manager.request_report(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        report_request=report_request,
    )

    # Verify delegation called
    assert mock_delegator.delegate_task.called
    assert not isinstance(result, str)
    assert result.id == task_id


@pytest.mark.asyncio
async def test_request_report_builds_instructions() -> None:
    """Test report request builds instructions with template sections."""
    # Mock DelegationManager
    mock_delegator = AsyncMock()
    mock_task = AgentTask(
        id=uuid4(),
        task_type=AgentTaskType.GENERATE,
        description="Generate report",
        status=AgentTaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        metadata={},
    )
    mock_delegator.delegate_task = AsyncMock(return_value=mock_task)

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request (template_id uppercase to match REPORT_TEMPLATES keys)
    report_request = ReportRequest(
        report_type=ReportType.RESEARCH_SUMMARY,
        title="Test Research",
        scope="AI collaboration patterns",
        template_id="RESEARCH_SUMMARY",  # Explicitly uppercase
    )

    # Request report
    await manager.request_report(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        report_request=report_request,
    )

    # Verify instructions include template sections
    call_args = mock_delegator.delegate_task.call_args
    description = call_args.kwargs["description"]

    # Check for template sections in instructions
    template = REPORT_TEMPLATES["RESEARCH_SUMMARY"]
    for section in template.sections:
        assert section in description
    assert "AI collaboration patterns" in description


@pytest.mark.asyncio
async def test_request_report_delegates_task() -> None:
    """Test report request delegates task with correct parameters."""
    # Mock DelegationManager
    mock_delegator = AsyncMock()
    task_id = uuid4()
    mock_task = AgentTask(
        id=task_id,
        task_type=AgentTaskType.GENERATE,
        description="Generate report",
        status=AgentTaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        metadata={},
    )
    mock_delegator.delegate_task = AsyncMock(return_value=mock_task)

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request
    conversation_id = uuid4()
    from_agent_id = uuid4()
    to_agent_id = uuid4()
    report_request = ReportRequest(
        report_type=ReportType.RISK_ASSESSMENT,
        title="Security Risk Assessment",
        scope="Phase 7 authentication system",
        template_id="RISK_ASSESSMENT",  # Explicitly uppercase
    )

    # Request report
    result = await manager.request_report(
        conversation_id=conversation_id,
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        report_request=report_request,
    )

    # Verify delegation called with correct args
    assert mock_delegator.delegate_task.called
    call_args = mock_delegator.delegate_task.call_args
    assert call_args.kwargs["conversation_id"] == conversation_id
    assert call_args.kwargs["created_by_agent_id"] == from_agent_id
    assert call_args.kwargs["assigned_to_agent_id"] == to_agent_id
    assert call_args.kwargs["title"] == "Security Risk Assessment"
    assert call_args.kwargs["priority"] == 5
    assert not isinstance(result, str)


@pytest.mark.asyncio
async def test_request_report_metadata_preserved() -> None:
    """Test report request preserves report_type in metadata."""
    # Mock DelegationManager
    mock_delegator = AsyncMock()
    mock_task = AgentTask(
        id=uuid4(),
        task_type=AgentTaskType.GENERATE,
        description="Generate report",
        status=AgentTaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        assigned_to=uuid4(),
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        metadata={"custom_key": "custom_value"},
    )
    mock_delegator.delegate_task = AsyncMock(return_value=mock_task)

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request with metadata
    report_request = ReportRequest(
        report_type=ReportType.CODE_REVIEW,
        title="Test Report",
        scope="src/",
        template_id="CODE_REVIEW",  # Explicitly uppercase
        metadata={"custom_key": "custom_value"},
    )

    # Request report
    result = await manager.request_report(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        report_request=report_request,
    )

    # Verify result contains metadata
    assert not isinstance(result, str)
    assert result.metadata.get("custom_key") == "custom_value"


@pytest.mark.asyncio
async def test_get_report_parses_result() -> None:
    """Test get_report parses task result into Report model."""
    # Mock DelegationManager with _session
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Create completed task
    task_id = uuid4()
    agent_id = uuid4()
    completed_at = datetime.now(timezone.utc)
    task_result = "# Code Review Report\n\n## Summary\nAll good.\n\n## Issues Found\nNone.\n\n## Recommendations\nContinue.\n\n## Security Concerns\nNone."

    # Mock task retrieval via TaskExecutor pattern
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_task = AgentTask(
            id=task_id,
            task_type=AgentTaskType.GENERATE,
            description="Generate code_review report for src/",
            status=AgentTaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            assigned_to=agent_id,
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            completed_at=completed_at,
            result=task_result,
            metadata={"title": "Code Review Report"},
        )
        mock_get_task.return_value = mock_task

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report
        report = await manager.get_report(task_id=task_id)

        # Verify Report model
        assert not isinstance(report, str)
        assert isinstance(report, Report)
        assert report.id == task_id
        assert report.report_type == ReportType.CODE_REVIEW
        assert report.generated_by == agent_id
        assert report.content == task_result
        assert report.format == "markdown"


@pytest.mark.asyncio
async def test_get_report_validates_sections() -> None:
    """Test get_report validates sections against template."""
    # Mock DelegationManager with _session
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Create completed task with all sections
    task_id = uuid4()
    agent_id = uuid4()
    task_result = """# Research Summary

## Objective
Study AI collaboration patterns.

## Methodology
Literature review and code analysis.

## Key Findings
Progressive disclosure is effective.

## Conclusions
Adopt progressive disclosure pattern.
"""

    # Mock task retrieval
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_task = AgentTask(
            id=task_id,
            task_type=AgentTaskType.GENERATE,
            description="Generate research_summary report",
            status=AgentTaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            assigned_to=agent_id,
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result=task_result,
            metadata={"title": "Research Summary"},
        )
        mock_get_task.return_value = mock_task

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report
        report = await manager.get_report(task_id=task_id)

        # Verify report retrieved successfully
        assert not isinstance(report, str)
        assert isinstance(report, Report)
        # Validation happens internally, no error raised


@pytest.mark.asyncio
async def test_get_report_task_not_found() -> None:
    """Test get_report returns error when task not found."""
    # Mock DelegationManager
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Mock TaskExecutor to return None
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_get_task.return_value = None

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report
        task_id = uuid4()
        result = await manager.get_report(task_id=task_id)

        # Verify error returned
        assert isinstance(result, str)
        assert "Error: Task not found" in result
        assert str(task_id) in result


@pytest.mark.asyncio
async def test_get_report_incomplete_task() -> None:
    """Test get_report returns error when task not completed."""
    # Mock DelegationManager
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Create incomplete task
    task_id = uuid4()

    # Mock TaskExecutor to return pending task
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_task = AgentTask(
            id=task_id,
            task_type=AgentTaskType.GENERATE,
            description="Generate report",
            status=AgentTaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_to=uuid4(),
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            metadata={},
        )
        mock_get_task.return_value = mock_task

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report
        result = await manager.get_report(task_id=task_id)

        # Verify error returned
        assert isinstance(result, str)
        assert "Error: Report task not completed" in result
        assert "in_progress" in result


@pytest.mark.asyncio
async def test_invalid_report_type() -> None:
    """Test error when report_type not in REPORT_TEMPLATES."""
    # Mock DelegationManager
    mock_delegator = AsyncMock()

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request with invalid template (use valid ReportType but override template_id)
    report_request = ReportRequest(
        report_type=ReportType.CODE_REVIEW,
        title="Test Report",
        scope="src/",
        template_id="INVALID_TEMPLATE",  # Force invalid template lookup
    )

    # Request report
    result = await manager.request_report(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        report_request=report_request,
    )

    # Verify error returned
    assert isinstance(result, str)
    assert "Error: Template not found" in result


@pytest.mark.asyncio
async def test_section_validation_missing_sections() -> None:
    """Test validation detects missing sections."""
    # Mock DelegationManager
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Create completed task with MISSING sections
    task_id = uuid4()
    agent_id = uuid4()
    task_result = """# Risk Assessment Report

## Risks Identified
- Risk 1: High severity
- Risk 2: Medium severity

## Impact Analysis
Moderate impact expected.

# Missing: Mitigation Strategies and Action Plan sections
"""

    # Mock TaskExecutor to return completed task
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_task = AgentTask(
            id=task_id,
            task_type=AgentTaskType.GENERATE,
            description="Generate risk_assessment report",
            status=AgentTaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            assigned_to=agent_id,
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result=task_result,
            metadata={"title": "Risk Assessment"},
        )
        mock_get_task.return_value = mock_task

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report (should still succeed but log warning)
        report = await manager.get_report(task_id=task_id)

        # Verify report still returned (validation warning logged, not error)
        assert not isinstance(report, str)
        assert isinstance(report, Report)
        # Internal validation logs warning but doesn't fail


@pytest.mark.asyncio
async def test_get_report_no_result() -> None:
    """Test get_report handles task completed without result."""
    # Mock DelegationManager
    mock_session = AsyncMock()
    mock_delegator = AsyncMock()
    mock_delegator._session = mock_session

    # Create completed task with NO result
    task_id = uuid4()

    # Mock TaskExecutor
    from src.collaboration.delegation.task_executor import TaskExecutor

    with patch.object(TaskExecutor, "get_task") as mock_get_task:
        mock_task = AgentTask(
            id=task_id,
            task_type=AgentTaskType.GENERATE,
            description="Generate report",
            status=AgentTaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            assigned_to=uuid4(),
            created_by=uuid4(),
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result=None,  # No result!
            metadata={},
        )
        mock_get_task.return_value = mock_task

        # Create ReportManager
        manager = ReportManager(task_delegator=mock_delegator)

        # Get report
        result = await manager.get_report(task_id=task_id)

        # Verify error returned
        assert isinstance(result, str)
        assert "Error: Report task completed but no result found" in result


@pytest.mark.asyncio
async def test_delegation_error_propagates() -> None:
    """Test that delegation errors are propagated from delegate_task."""
    # Mock DelegationManager that returns error string
    mock_delegator = AsyncMock()
    error_msg = "Error: Agent not available"
    mock_delegator.delegate_task = AsyncMock(return_value=error_msg)

    # Create ReportManager
    manager = ReportManager(task_delegator=mock_delegator)

    # Create request
    report_request = ReportRequest(
        report_type=ReportType.CODE_REVIEW,
        title="Test Report",
        scope="src/",
        template_id="CODE_REVIEW",  # Explicitly uppercase
    )

    # Request report
    result = await manager.request_report(
        conversation_id=uuid4(),
        from_agent_id=uuid4(),
        to_agent_id=uuid4(),
        report_request=report_request,
    )

    # Verify error propagated
    assert isinstance(result, str)
    assert result == error_msg
