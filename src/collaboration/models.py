"""Pydantic models for agent collaboration, routing, and multi-agent orchestration."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Enums (P7-01A)
# ============================================================================


class ParticipantRole(str, Enum):
    """Role of an agent in a collaboration session."""

    PRIMARY = "primary"
    INVITED = "invited"
    HANDOFF_SOURCE = "handoff_source"


class AgentTaskType(str, Enum):
    """Type of task an agent can perform in delegation."""

    RESEARCH = "research"
    REVIEW = "review"
    ANALYZE = "analyze"
    GENERATE = "generate"
    SUMMARIZE = "summarize"
    VALIDATE = "validate"
    PLAN = "plan"
    EXECUTE = "execute"


class AgentTaskStatus(str, Enum):
    """Lifecycle status of a delegated agent task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskPriority(str, Enum):
    """Priority level for delegated tasks."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AgentMessageType(str, Enum):
    """Type of message exchanged between agents."""

    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    TASK_STATUS = "task_status"
    INFO_REQUEST = "info_request"
    INFO_RESPONSE = "info_response"
    NOTIFICATION = "notification"
    COLLAB_INVITE = "collab_invite"
    COLLAB_UPDATE = "collab_update"
    HANDOFF_REQUEST = "handoff_request"
    FEEDBACK = "feedback"


class CollaborationPattern(str, Enum):
    """Multi-agent collaboration pattern being executed."""

    SUPERVISOR_WORKER = "supervisor_worker"
    PIPELINE = "pipeline"
    PEER_REVIEW = "peer_review"
    BRAINSTORM = "brainstorm"
    CONSENSUS = "consensus"
    DELEGATION = "delegation"


class CollaborationStatus(str, Enum):
    """Lifecycle status of a collaboration session."""

    PLANNING = "planning"
    ACTIVE = "active"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ReportType(str, Enum):
    """Type of structured report an agent can generate."""

    CODE_REVIEW = "code_review"
    SECURITY_AUDIT = "security_audit"
    RESEARCH_SUMMARY = "research_summary"
    DATA_ANALYSIS = "data_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    PERFORMANCE_REPORT = "performance_report"
    COMPARISON = "comparison"
    ACTION_PLAN = "action_plan"


# ============================================================================
# Constants
# ============================================================================

MAX_DELEGATION_DEPTH = 3
MAX_CONCURRENT_TASKS = 5


# ============================================================================
# Core Models (P7-01B)
# ============================================================================


class RoutingDecision(BaseModel):
    """Router's decision about which agent should handle a request.

    Args:
        selected_agent_id: UUID of the agent chosen to handle the request.
        confidence: Router confidence in this decision (0.0-1.0).
        reasoning: Explanation of why this agent was selected.
        alternatives: List of alternative agent IDs considered.
    """

    selected_agent_id: UUID
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    alternatives: list[UUID] = Field(default_factory=list)


class HandoffResult(BaseModel):
    """Result of handing off a conversation to another agent.

    Args:
        target_agent_id: UUID of the agent receiving the handoff.
        success: Whether the handoff was accepted.
        context_transferred: Summary of what context was transferred.
        reason: Reason for the handoff or failure message.
    """

    target_agent_id: UUID
    success: bool
    context_transferred: str
    reason: str


class AgentRecommendation(BaseModel):
    """A recommended agent for a specific task or query.

    Args:
        agent_id: UUID of the recommended agent.
        agent_name: Human-readable name of the agent.
        match_score: How well this agent matches the request (0.0-1.0).
        reasoning: Why this agent is recommended.
    """

    agent_id: UUID
    agent_name: str
    match_score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class AgentProfile(BaseModel):
    """Profile information about an agent's capabilities.

    Args:
        agent_id: UUID of the agent.
        name: Human-readable name.
        capabilities: List of capabilities (skills, task types).
        specializations: Domain or task type specializations.
        personality_summary: Brief personality summary for matching.
        average_response_time: Average response time in seconds.
    """

    agent_id: UUID
    name: str
    capabilities: list[str]
    specializations: list[str]
    personality_summary: str
    average_response_time: float = Field(ge=0.0)


class AgentAvailability(BaseModel):
    """Real-time availability status of an agent.

    Args:
        agent_id: UUID of the agent.
        is_available: Whether the agent can accept new tasks.
        current_load: Number of active tasks currently assigned.
        max_concurrent_tasks: Maximum number of concurrent tasks.
        estimated_wait_time: Estimated seconds until available.
    """

    agent_id: UUID
    is_available: bool
    current_load: int = Field(ge=0)
    max_concurrent_tasks: int = Field(default=MAX_CONCURRENT_TASKS, ge=1)
    estimated_wait_time: float = Field(default=0.0, ge=0.0)


class AgentTaskCreate(BaseModel):
    """Request to create a new delegated agent task.

    Args:
        task_type: Type of task being delegated.
        description: Task description and requirements.
        assigned_to: UUID of the agent assigned to this task.
        priority: Task priority level.
        parent_task_id: Parent task UUID if this is a subtask.
        timeout_seconds: Maximum execution time in seconds.
        metadata: Additional task metadata.
    """

    task_type: AgentTaskType
    description: str
    assigned_to: UUID
    priority: TaskPriority = TaskPriority.NORMAL
    parent_task_id: Optional[UUID] = None
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """A delegated task assigned to an agent.

    Args:
        id: Task UUID.
        task_type: Type of task being performed.
        description: Task description and requirements.
        status: Current task status.
        priority: Task priority level.
        assigned_to: UUID of the assigned agent.
        created_by: UUID of the agent that created this task.
        created_at: Task creation timestamp.
        started_at: Task start timestamp.
        completed_at: Task completion timestamp.
        result: Task result or output.
        error: Error message if task failed.
        parent_task_id: Parent task UUID if this is a subtask.
        depth: Delegation depth (0=root, 1=child, etc).
        timeout_seconds: Maximum execution time in seconds.
        metadata: Additional task metadata.
    """

    id: UUID
    task_type: AgentTaskType
    description: str
    status: AgentTaskStatus
    priority: TaskPriority
    assigned_to: UUID
    created_by: UUID
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    parent_task_id: Optional[UUID] = None
    depth: int = Field(default=0, ge=0, le=MAX_DELEGATION_DEPTH)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    """Message exchanged between agents in a collaboration.

    Args:
        id: Message UUID.
        message_type: Type of message being sent.
        sender_id: UUID of the sending agent.
        recipient_id: UUID of the receiving agent.
        content: Message content or payload.
        timestamp: Message timestamp.
        metadata: Additional message metadata.
    """

    id: UUID
    message_type: AgentMessageType
    sender_id: UUID
    recipient_id: UUID
    content: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Report Models (P7-01C)
# ============================================================================


class ReportRequest(BaseModel):
    """Request to generate a structured report.

    Args:
        report_type: Type of report to generate.
        title: Report title.
        scope: Description of what to include in the report.
        template_id: Optional template ID to use.
        format: Output format (markdown, json, html).
        metadata: Additional request metadata.
    """

    report_type: ReportType
    title: str
    scope: str
    template_id: Optional[str] = None
    format: Literal["markdown", "json", "html"] = "markdown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportTemplate(BaseModel):
    """Template for generating structured reports.

    Args:
        template_id: Unique template identifier.
        report_type: Type of report this template generates.
        sections: List of section names in order.
        instructions: Instructions for generating each section.
        example: Example report output.
    """

    template_id: str
    report_type: ReportType
    sections: list[str]
    instructions: dict[str, str]
    example: str = ""


class Report(BaseModel):
    """A generated structured report.

    Args:
        id: Report UUID.
        report_type: Type of report.
        title: Report title.
        generated_by: UUID of the agent that generated this report.
        generated_at: Report generation timestamp.
        format: Report format (markdown, json, html).
        content: Full report content.
        sections: Report content split by section.
        metadata: Additional report metadata.
    """

    id: UUID
    report_type: ReportType
    title: str
    generated_by: UUID
    generated_at: datetime
    format: Literal["markdown", "json", "html"]
    content: str
    sections: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Collaboration Session Models (P7-01C)
# ============================================================================


class CollaborationParticipantInfo(BaseModel):
    """Information about an agent participating in a collaboration.

    Args:
        agent_id: UUID of the participating agent.
        role: Participant's role in the collaboration.
        joined_at: Timestamp when this participant joined.
        contribution: Description of this participant's contribution.
    """

    agent_id: UUID
    role: ParticipantRole
    joined_at: datetime
    contribution: str = ""


class StageOutput(BaseModel):
    """Output from a single stage in a multi-stage collaboration.

    Args:
        stage_name: Name of the collaboration stage.
        agent_id: UUID of the agent that completed this stage.
        output: Stage output or result.
        completed_at: Stage completion timestamp.
    """

    stage_name: str
    agent_id: UUID
    output: str
    completed_at: datetime


class CollaborationSession(BaseModel):
    """A multi-agent collaboration session.

    Args:
        id: Session UUID.
        pattern: Collaboration pattern being used.
        status: Current session status.
        initiator_id: UUID of the agent that initiated the session.
        participants: List of participating agents with roles.
        started_at: Session start timestamp.
        completed_at: Session completion timestamp.
        stage_outputs: Outputs from each collaboration stage.
        final_result: Final synthesized result.
        metadata: Additional session metadata.
    """

    id: UUID
    pattern: CollaborationPattern
    status: CollaborationStatus
    initiator_id: UUID
    participants: list[CollaborationParticipantInfo]
    started_at: datetime
    completed_at: Optional[datetime] = None
    stage_outputs: list[StageOutput] = Field(default_factory=list)
    final_result: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParticipantConfig(BaseModel):
    """Configuration for an agent's participation in a collaboration.

    Args:
        agent_id: UUID of the participant agent.
        role: Participant's role in the collaboration.
        instructions: Specific instructions for this participant.
        dependencies: List of participant agent IDs this one depends on.
    """

    agent_id: UUID
    role: ParticipantRole
    instructions: str
    dependencies: list[UUID] = Field(default_factory=list)


# ============================================================================
# Report Templates (P7-01C)
# ============================================================================

REPORT_TEMPLATES: dict[str, ReportTemplate] = {
    "CODE_REVIEW": ReportTemplate(
        template_id="CODE_REVIEW",
        report_type=ReportType.CODE_REVIEW,
        sections=["Summary", "Issues Found", "Recommendations", "Security Concerns"],
        instructions={
            "Summary": "Provide overview of code reviewed and overall quality assessment.",
            "Issues Found": "List specific issues found with severity and location.",
            "Recommendations": "Suggest improvements and best practices.",
            "Security Concerns": "Highlight any security vulnerabilities or risks.",
        },
        example="# Code Review Report\n\n## Summary\n...",
    ),
    "RESEARCH_SUMMARY": ReportTemplate(
        template_id="RESEARCH_SUMMARY",
        report_type=ReportType.RESEARCH_SUMMARY,
        sections=["Objective", "Methodology", "Key Findings", "Conclusions"],
        instructions={
            "Objective": "State the research question or goal.",
            "Methodology": "Describe how research was conducted.",
            "Key Findings": "Summarize the most important discoveries.",
            "Conclusions": "Draw conclusions and suggest next steps.",
        },
        example="# Research Summary\n\n## Objective\n...",
    ),
    "RISK_ASSESSMENT": ReportTemplate(
        template_id="RISK_ASSESSMENT",
        report_type=ReportType.RISK_ASSESSMENT,
        sections=["Risks Identified", "Impact Analysis", "Mitigation Strategies", "Action Plan"],
        instructions={
            "Risks Identified": "List all identified risks with severity ratings.",
            "Impact Analysis": "Analyze potential impact of each risk.",
            "Mitigation Strategies": "Propose strategies to mitigate or eliminate risks.",
            "Action Plan": "Recommend concrete actions to take.",
        },
        example="# Risk Assessment Report\n\n## Risks Identified\n...",
    ),
}
