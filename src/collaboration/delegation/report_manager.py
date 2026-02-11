"""Structured report generation manager for multi-agent collaboration."""

import logging
from uuid import UUID

from src.collaboration.delegation.delegation_manager import DelegationManager
from src.collaboration.models import REPORT_TEMPLATES, AgentTask, Report, ReportRequest

logger = logging.getLogger(__name__)


class ReportManager:
    """Manages structured report generation and validation.

    Delegates report generation tasks to specialized agents using
    predefined templates with sections and instructions. Validates
    that generated reports contain all required sections.

    Args:
        task_delegator: DelegationManager instance for task delegation.
    """

    def __init__(self, task_delegator: DelegationManager) -> None:
        """Initialize ReportManager.

        Args:
            task_delegator: DelegationManager instance for task delegation.
        """
        self.task_delegator = task_delegator

    async def request_report(
        self,
        conversation_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        report_request: ReportRequest,
    ) -> AgentTask | str:
        """Request a structured report from an agent.

        Builds instructions from template sections and delegates as an
        AgentTask. Template is selected from REPORT_TEMPLATES based on
        report_type or template_id.

        Args:
            conversation_id: UUID of the conversation this report belongs to.
            from_agent_id: UUID of the agent requesting the report.
            to_agent_id: UUID of the agent that will generate the report.
            report_request: ReportRequest with type, title, scope, etc.

        Returns:
            AgentTask if delegation successful, error string otherwise.
        """
        # Get template
        template_id = report_request.template_id or report_request.report_type.value
        template = REPORT_TEMPLATES.get(template_id.upper())
        if not template:
            logger.warning(
                f"report_request_failed: template_not_found={template_id}, "
                f"report_type={report_request.report_type.value}"
            )
            return f"Error: Template not found for report type '{report_request.report_type.value}'"

        # Build instructions
        instructions = self._build_instructions(report_request, template)

        # Delegate task
        task_result = await self.task_delegator.delegate_task(
            conversation_id=conversation_id,
            created_by_agent_id=from_agent_id,
            assigned_to_agent_id=to_agent_id,
            title=report_request.title,
            description=instructions,
            priority=5,  # Default priority for reports
            parent_task_id=None,
        )

        if isinstance(task_result, str):
            logger.warning(
                f"report_delegation_failed: error={task_result}, "
                f"report_type={report_request.report_type.value}"
            )
            return task_result

        logger.info(
            f"report_requested: report_type={report_request.report_type.value}, "
            f"title={report_request.title}, task_id={task_result.id}, "
            f"assigned_to={to_agent_id}"
        )

        return task_result

    async def get_report(
        self,
        task_id: UUID,
    ) -> Report | str:
        """Get a generated report from a completed task.

        Retrieves task result, parses it into a Report model, and validates
        that all template sections are present.

        Args:
            task_id: UUID of the report generation task.

        Returns:
            Report model if task completed and valid, error string otherwise.
        """
        # Get task via delegation manager
        from src.collaboration.delegation.task_executor import TaskExecutor

        task_executor = TaskExecutor(self.task_delegator._session)
        task = await task_executor.get_task(task_id)

        if not task:
            logger.warning(f"get_report_failed: task_not_found={task_id}")
            return f"Error: Task not found (ID: {task_id})"

        # Check task status
        from src.collaboration.models import AgentTaskStatus

        if task.status != AgentTaskStatus.COMPLETED:
            logger.warning(
                f"get_report_failed: task_not_completed={task_id}, status={task.status.value}"
            )
            return f"Error: Report task not completed (status: {task.status.value})"

        if not task.result:
            logger.warning(f"get_report_failed: no_result={task_id}")
            return "Error: Report task completed but no result found"

        # Parse result into Report model
        # Extract report_type from task metadata if available
        from datetime import datetime

        from src.collaboration.models import ReportType

        # Try to infer report type from task description/title
        report_type = ReportType.CODE_REVIEW  # Default fallback
        for rt in ReportType:
            if rt.value.lower() in task.description.lower():
                report_type = rt
                break

        report = Report(
            id=task_id,
            report_type=report_type,
            title=task.metadata.get("title", "Untitled Report"),
            generated_by=task.assigned_to,
            generated_at=task.completed_at or datetime.utcnow(),
            format="markdown",  # Default format
            content=task.result,
            sections={},  # Will be populated by section parsing
            metadata=task.metadata,
        )

        # Validate sections (optional, log warning if incomplete)
        template_id = report_type.value
        template = REPORT_TEMPLATES.get(template_id.upper())
        if template:
            is_valid = self._validate_sections(report.content, template)
            if not is_valid:
                logger.warning(
                    f"report_incomplete_sections: task_id={task_id}, "
                    f"template={template_id}, missing sections detected"
                )
                # Still return report, but log warning
        else:
            logger.debug(f"report_validation_skipped: no_template={template_id}")

        logger.info(
            f"report_retrieved: task_id={task_id}, report_type={report_type.value}, "
            f"content_length={len(report.content)}"
        )

        return report

    def _build_instructions(
        self,
        report_request: ReportRequest,
        template: "REPORT_TEMPLATES.__class__",  # type: ignore
    ) -> str:
        """Build detailed instructions from report request and template.

        Combines template sections, instructions, and request scope into
        a comprehensive task description for the agent.

        Args:
            report_request: ReportRequest with scope and format.
            template: ReportTemplate with sections and instructions.

        Returns:
            Formatted instruction string for the report generation task.
        """
        lines = [
            f"# Generate {report_request.report_type.value.replace('_', ' ').title()} Report",
            "",
            f"**Title:** {report_request.title}",
            f"**Scope:** {report_request.scope}",
            f"**Format:** {report_request.format}",
            "",
            "## Required Sections",
            "",
        ]

        # Add section instructions
        for section in template.sections:
            instruction = template.instructions.get(section, "")
            lines.append(f"### {section}")
            lines.append(instruction)
            lines.append("")

        # Add example if available
        if template.example:
            lines.append("## Example Format")
            lines.append("")
            lines.append(template.example)
            lines.append("")

        return "\n".join(lines)

    def _validate_sections(
        self,
        report_text: str,
        template: "REPORT_TEMPLATES.__class__",  # type: ignore
    ) -> bool:
        """Validate that report contains all required sections.

        Checks if all template sections appear as markdown headers
        (## Section Name) in the report text.

        Args:
            report_text: Generated report content.
            template: ReportTemplate with required sections.

        Returns:
            True if all sections present, False otherwise.
        """
        # Simple validation: check if each section appears as a header
        report_lower = report_text.lower()
        for section in template.sections:
            section_lower = section.lower()
            # Check for markdown header patterns: ## Section or # Section
            if (
                f"## {section_lower}" not in report_lower
                and f"# {section_lower}" not in report_lower
            ):
                logger.debug(f"section_missing: section={section}, template={template.template_id}")
                return False

        return True
