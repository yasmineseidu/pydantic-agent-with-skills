"""Task delegation manager with depth enforcement and status tracking."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import and_, select

from src.collaboration.models import AgentTask, AgentTaskStatus, MAX_DELEGATION_DEPTH, TaskPriority
from src.db.models.collaboration import AgentTaskORM

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DelegationManager:
    """Manages task delegation between agents with depth tracking.

    Creates and tracks AgentTaskORM records for delegated tasks,
    enforcing MAX_DELEGATION_DEPTH (3) to prevent infinite delegation
    chains. Provides methods to delegate tasks, check depth limits,
    query pending tasks, and mark tasks complete.

    Feature flag: settings.feature_flags.enable_task_delegation

    Args:
        session: Async SQLAlchemy session for database operations.
    """

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize DelegationManager.

        Args:
            session: Async SQLAlchemy session for database operations.
        """
        self._session: "AsyncSession" = session

    async def delegate_task(
        self,
        conversation_id: UUID,
        created_by_agent_id: UUID,
        assigned_to_agent_id: UUID,
        title: str,
        description: str,
        priority: int = 5,
        parent_task_id: Optional[UUID] = None,
    ) -> AgentTask | str:
        """Delegate a task from one agent to another.

        Validates delegation depth (max 3 levels deep), creates an
        AgentTaskORM record with status PENDING, and returns the task
        as a Pydantic model.

        Args:
            conversation_id: UUID of the conversation this task belongs to.
            created_by_agent_id: UUID of the agent creating the task.
            assigned_to_agent_id: UUID of the agent receiving the task.
            title: Short task title.
            description: Detailed task description.
            priority: Task priority (1=highest, 10=lowest, default=5).
            parent_task_id: Optional parent task UUID if this is a subtask.

        Returns:
            AgentTask model if successful, error string if depth exceeded.
        """
        # Check delegation depth
        depth = 0
        if parent_task_id:
            parent_depth, error = await self.check_delegation_depth(parent_task_id)
            if error:
                logger.warning(
                    f"delegate_task_failed: parent_not_found={parent_task_id}, "
                    f"created_by={created_by_agent_id}"
                )
                return f"Error: Parent task not found (ID: {parent_task_id})"

            depth = parent_depth + 1
            if depth > MAX_DELEGATION_DEPTH:
                logger.warning(
                    f"delegate_task_rejected: depth_exceeded={depth}, "
                    f"max={MAX_DELEGATION_DEPTH}, parent={parent_task_id}"
                )
                return (
                    f"Error: Maximum delegation depth ({MAX_DELEGATION_DEPTH}) exceeded. "
                    f"Current depth: {depth}"
                )

        # Create task ORM
        task_orm = AgentTaskORM(
            conversation_id=conversation_id,
            created_by_agent_id=created_by_agent_id,
            assigned_to_agent_id=assigned_to_agent_id,
            parent_task_id=parent_task_id,
            title=title,
            description=description,
            status=AgentTaskStatus.PENDING.value,
            priority=priority,
            delegation_depth=depth,
            result=None,
            completed_at=None,
        )

        self._session.add(task_orm)
        await self._session.flush()

        logger.info(
            f"task_delegated: task_id={task_orm.id}, title={title[:50]}, "
            f"created_by={created_by_agent_id}, assigned_to={assigned_to_agent_id}, "
            f"depth={depth}, priority={priority}"
        )

        # Convert to Pydantic model (using RESEARCH as default task_type for compatibility)
        from src.collaboration.models import AgentTaskType

        return AgentTask(
            id=task_orm.id,
            task_type=AgentTaskType.EXECUTE,  # Default type (not stored in Phase 7 ORM)
            description=description,
            status=AgentTaskStatus.PENDING,
            priority=self._priority_int_to_enum(priority),
            assigned_to=assigned_to_agent_id,
            created_by=created_by_agent_id,
            created_at=task_orm.created_at,
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            parent_task_id=parent_task_id,
            depth=depth,
            timeout_seconds=300,
            metadata={"title": title, "conversation_id": str(conversation_id)},
        )

    async def check_delegation_depth(
        self,
        task_id: UUID,
    ) -> tuple[int, Optional[str]]:
        """Check the delegation depth of a task.

        Traverses parent task chain to calculate total delegation depth.

        Args:
            task_id: UUID of the task to check.

        Returns:
            Tuple of (depth, error_message).
                depth is 0 for root tasks, 1+ for delegated tasks.
                error_message is None if task found, error string otherwise.
        """
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            return (0, f"Task not found (ID: {task_id})")

        depth = task_orm.delegation_depth
        logger.debug(f"delegation_depth_checked: task_id={task_id}, depth={depth}")
        return (depth, None)

    async def get_pending_tasks(
        self,
        assigned_to_agent_id: UUID,
        conversation_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> list[AgentTask]:
        """Get pending tasks assigned to an agent.

        Returns tasks with status PENDING, ordered by priority (ascending)
        then created_at (oldest first).

        Args:
            assigned_to_agent_id: UUID of the agent to get tasks for.
            conversation_id: Optional filter by conversation.
            limit: Maximum number of tasks to return.

        Returns:
            List of AgentTask models with PENDING status.
        """
        filters = [
            AgentTaskORM.assigned_to_agent_id == assigned_to_agent_id,
            AgentTaskORM.status == AgentTaskStatus.PENDING.value,
        ]
        if conversation_id:
            filters.append(AgentTaskORM.conversation_id == conversation_id)

        stmt = (
            select(AgentTaskORM)
            .where(and_(*filters))
            .order_by(AgentTaskORM.priority.asc(), AgentTaskORM.created_at.asc())
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        task_orms = list(result.scalars().all())

        logger.info(
            f"pending_tasks_retrieved: agent_id={assigned_to_agent_id}, "
            f"count={len(task_orms)}, conversation_id={conversation_id}"
        )

        # Convert to Pydantic models
        from src.collaboration.models import AgentTaskType

        tasks: list[AgentTask] = []
        for orm in task_orms:
            tasks.append(
                AgentTask(
                    id=orm.id,
                    task_type=AgentTaskType.EXECUTE,
                    description=orm.description,
                    status=AgentTaskStatus(orm.status),
                    priority=self._priority_int_to_enum(orm.priority),
                    assigned_to=orm.assigned_to_agent_id,
                    created_by=orm.created_by_agent_id,
                    created_at=orm.created_at,
                    started_at=None,
                    completed_at=orm.completed_at,
                    result=orm.result,
                    error=None,
                    parent_task_id=orm.parent_task_id,
                    depth=orm.delegation_depth,
                    timeout_seconds=300,
                    metadata={"title": orm.title},
                )
            )

        return tasks

    async def complete_task(
        self,
        task_id: UUID,
        result: str,
        status: AgentTaskStatus = AgentTaskStatus.COMPLETED,
    ) -> AgentTask | str:
        """Mark a task as complete with result.

        Updates task status to COMPLETED (or FAILED) and sets completed_at
        timestamp. Returns the updated task model.

        Args:
            task_id: UUID of the task to complete.
            result: Task result or error message.
            status: Final status (COMPLETED or FAILED).

        Returns:
            Updated AgentTask model if successful, error string if not found.
        """
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            logger.warning(f"complete_task_failed: task_not_found={task_id}")
            return f"Error: Task not found (ID: {task_id})"

        # Update task
        old_status = task_orm.status
        task_orm.status = status.value
        task_orm.result = result
        task_orm.completed_at = datetime.utcnow()

        await self._session.flush()

        logger.info(
            f"task_completed: task_id={task_id}, old_status={old_status}, "
            f"new_status={status.value}, result_length={len(result)}"
        )

        # Convert to Pydantic model
        from src.collaboration.models import AgentTaskType

        return AgentTask(
            id=task_orm.id,
            task_type=AgentTaskType.EXECUTE,
            description=task_orm.description,
            status=status,
            priority=self._priority_int_to_enum(task_orm.priority),
            assigned_to=task_orm.assigned_to_agent_id,
            created_by=task_orm.created_by_agent_id,
            created_at=task_orm.created_at,
            started_at=None,
            completed_at=task_orm.completed_at,
            result=task_orm.result,
            error=result if status == AgentTaskStatus.FAILED else None,
            parent_task_id=task_orm.parent_task_id,
            depth=task_orm.delegation_depth,
            timeout_seconds=300,
            metadata={"title": task_orm.title},
        )

    def _priority_int_to_enum(self, priority: int) -> TaskPriority:
        """Convert integer priority to TaskPriority enum.

        Args:
            priority: Integer priority (1-10, default 5).

        Returns:
            TaskPriority enum value.
        """
        if priority <= 2:
            return TaskPriority.URGENT
        elif priority <= 4:
            return TaskPriority.HIGH
        elif priority <= 7:
            return TaskPriority.NORMAL
        else:
            return TaskPriority.LOW
