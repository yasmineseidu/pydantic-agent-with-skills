"""API schemas for collaboration routing, handoffs, and sessions."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.collaboration.models import (
    AgentMessageType,
    CollaborationPattern,
    CollaborationStatus,
    ParticipantRole,
)


class CollaborationRouteRequest(BaseModel):
    """Request to route a query to the best agent."""

    query: str = Field(min_length=1, max_length=4000)
    current_agent_id: Optional[UUID] = None
    conversation_history: Optional[list[str]] = None


class CollaborationRecommendRequest(BaseModel):
    """Request to recommend multiple agents for collaboration."""

    query: str = Field(min_length=1, max_length=4000)
    min_agents: int = Field(default=2, ge=1, le=5)
    max_agents: int = Field(default=4, ge=1, le=8)


class HandoffRequest(BaseModel):
    """Request to initiate an agent handoff."""

    conversation_id: UUID
    from_agent_id: UUID
    to_agent_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    context_transferred: dict[str, Any] = Field(default_factory=dict)


class HandoffRecordResponse(BaseModel):
    """Handoff record response payload."""

    id: UUID
    conversation_id: UUID
    from_agent_id: UUID
    to_agent_id: UUID
    reason: str
    context_transferred: dict[str, Any]
    handoff_at: datetime


class CollaborationSessionCreateRequest(BaseModel):
    """Request to create a collaboration session."""

    conversation_id: UUID
    pattern: CollaborationPattern
    goal: str = Field(min_length=1, max_length=2000)
    initiator_id: UUID


class ParticipantInput(BaseModel):
    """Input payload for adding a participant to a collaboration session."""

    agent_id: UUID
    role: ParticipantRole


class CollaborationParticipantsRequest(BaseModel):
    """Request to add participants to a collaboration session."""

    participants: list[ParticipantInput] = Field(min_length=1)


class CollaborationStatusUpdateRequest(BaseModel):
    """Request to update a collaboration session status."""

    status: CollaborationStatus
    final_result: Optional[str] = Field(default=None, max_length=5000)


class TaskDelegateRequest(BaseModel):
    """Request to delegate a task to another agent."""

    conversation_id: UUID
    created_by_agent_id: UUID
    assigned_to_agent_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    priority: int = Field(default=5, ge=1, le=10)
    parent_task_id: Optional[UUID] = None


class TaskCancelRequest(BaseModel):
    """Request to cancel a delegated task."""

    reason: Optional[str] = Field(default=None, max_length=2000)


class AgentMessageSendRequest(BaseModel):
    """Request to send an agent-to-agent message."""

    conversation_id: UUID
    to_agent_id: UUID
    message_type: AgentMessageType
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)
