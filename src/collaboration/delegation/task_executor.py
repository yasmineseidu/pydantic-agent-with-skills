"""Task executor for executing delegated agent tasks."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.collaboration.models import AgentTask, AgentTaskStatus
from src.db.models.collaboration import AgentTaskORM

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes delegated tasks and updates their status.

    Handles task lifecycle from pending → in_progress → completed/failed,
    tracking execution timestamps and results.

    Args:
        session: AsyncSession for database operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize task executor.

        Args:
            session: AsyncSession for database operations.
        """
        self._session = session

    async def execute_task(
        self,
        task_id: UUID,
        executor_agent_id: UUID,
    ) -> AgentTask:
        """Execute a delegated task.

        Marks task as in_progress and sets started_at timestamp.
        Does not actually run the task logic - this is the start marker.

        Args:
            task_id: UUID of the task to execute.
            executor_agent_id: UUID of the agent executing the task.

        Returns:
            Updated AgentTask with IN_PROGRESS status.
        """
        # Load task ORM
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            logger.warning(f"execute_task_failed: task_not_found={task_id}")
            return AgentTask(
                id=task_id,
                task_type="execute",  # type: ignore
                description="Task not found",
                status=AgentTaskStatus.FAILED,
                priority="normal",  # type: ignore
                assigned_to=executor_agent_id,
                created_by=executor_agent_id,
                created_at=datetime.utcnow(),
                error="Task not found",
            )

        # Verify assignment
        if task_orm.assigned_to_agent_id != executor_agent_id:
            logger.warning(
                f"execute_task_failed: wrong_agent task_id={task_id}, "
                f"assigned_to={task_orm.assigned_to_agent_id}, executor={executor_agent_id}"
            )
            return self._orm_to_model(task_orm)

        # Update to in_progress
        old_status = task_orm.status
        task_orm.status = AgentTaskStatus.IN_PROGRESS.value
        if not task_orm.started_at:
            task_orm.started_at = datetime.utcnow()

        await self._session.flush()

        logger.info(
            f"task_execution_started: task_id={task_id}, "
            f"old_status={old_status}, new_status=in_progress"
        )

        return self._orm_to_model(task_orm)

    async def update_task_status(
        self,
        task_id: UUID,
        status: AgentTaskStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AgentTask:
        """Update task status and result.

        Args:
            task_id: UUID of the task to update.
            status: New status (IN_PROGRESS, COMPLETED, FAILED, etc.).
            result: Optional result data for completed tasks.
            error: Optional error message for failed tasks.

        Returns:
            Updated AgentTask model.
        """
        # Load task ORM
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            logger.warning(f"update_status_failed: task_not_found={task_id}")
            return AgentTask(
                id=task_id,
                task_type="execute",  # type: ignore
                description="Task not found",
                status=AgentTaskStatus.FAILED,
                priority="normal",  # type: ignore
                assigned_to=UUID(int=0),
                created_by=UUID(int=0),
                created_at=datetime.utcnow(),
                error="Task not found",
            )

        # Update status
        old_status = task_orm.status
        task_orm.status = status.value

        # Set result/error
        if result is not None:
            task_orm.result = result
        if error is not None:
            task_orm.result = error  # Store error in result field

        # Set completed_at if terminal status
        if status in (
            AgentTaskStatus.COMPLETED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.CANCELLED,
            AgentTaskStatus.TIMED_OUT,
        ):
            if not task_orm.completed_at:
                task_orm.completed_at = datetime.utcnow()

        await self._session.flush()

        logger.info(
            f"task_status_updated: task_id={task_id}, "
            f"old_status={old_status}, new_status={status.value}"
        )

        return self._orm_to_model(task_orm)

    async def get_task_result(
        self,
        task_id: UUID,
    ) -> Optional[str]:
        """Get task result or error message.

        Args:
            task_id: UUID of the task.

        Returns:
            Task result string if available, None otherwise.
        """
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            logger.warning(f"get_result_failed: task_not_found={task_id}")
            return None

        return task_orm.result

    async def get_task(
        self,
        task_id: UUID,
    ) -> Optional[AgentTask]:
        """Get full task details.

        Args:
            task_id: UUID of the task.

        Returns:
            AgentTask model or None if not found.
        """
        task_orm = await self._session.get(AgentTaskORM, task_id)
        if not task_orm:
            logger.warning(f"get_task_failed: task_not_found={task_id}")
            return None

        return self._orm_to_model(task_orm)

    async def get_tasks_by_status(
        self,
        status: AgentTaskStatus,
        assigned_to: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
    ) -> list[AgentTask]:
        """Query tasks by status with optional filters.

        Args:
            status: Task status to filter by.
            assigned_to: Optional agent ID filter.
            conversation_id: Optional conversation ID filter.

        Returns:
            List of matching AgentTask models.
        """
        filters = [AgentTaskORM.status == status.value]
        if assigned_to is not None:
            filters.append(AgentTaskORM.assigned_to_agent_id == assigned_to)
        if conversation_id is not None:
            filters.append(AgentTaskORM.conversation_id == conversation_id)

        stmt = select(AgentTaskORM).where(*filters).order_by(AgentTaskORM.priority.desc())

        result = await self._session.execute(stmt)
        task_orms = result.scalars().all()

        return [self._orm_to_model(task_orm) for task_orm in task_orms]

    def _orm_to_model(self, task_orm: AgentTaskORM) -> AgentTask:
        """Convert AgentTaskORM to AgentTask Pydantic model.

        Args:
            task_orm: ORM instance to convert.

        Returns:
            AgentTask Pydantic model.
        """
        # Map title to description (ORM has title, model expects description)
        return AgentTask(
            id=task_orm.id,
            task_type="execute",  # type: ignore - Not stored in ORM, default
            description=task_orm.description,
            status=AgentTaskStatus(task_orm.status),
            priority="normal",  # type: ignore - Priority is int in ORM
            assigned_to=task_orm.assigned_to_agent_id,
            created_by=task_orm.created_by_agent_id,
            created_at=task_orm.created_at,
            started_at=getattr(task_orm, "started_at", None),
            completed_at=task_orm.completed_at,
            result=task_orm.result,
            error=None,  # Error is stored in result field
            parent_task_id=task_orm.parent_task_id,
            depth=task_orm.delegation_depth,
            timeout_seconds=300,  # Not stored in ORM, default
            metadata={},  # Not stored in ORM
        )
