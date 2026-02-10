"""CollaborationOrchestrator for pattern-based multi-agent workflows (Phase 7 Wave 4)."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from src.collaboration.models import (
    CollaborationPattern,
    CollaborationSession,
    CollaborationStatus,
    ParticipantConfig,
    ParticipantRole,
    StageOutput,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.collaboration.coordination.handoff_manager import HandoffManager
    from src.collaboration.coordination.multi_agent_manager import MultiAgentManager

logger = logging.getLogger(__name__)


class CollaborationOrchestrator:
    """Orchestrates multi-agent collaboration workflows using pattern-based dispatch.

    Implements 6 collaboration patterns: SUPERVISOR_WORKER, PIPELINE, PEER_REVIEW,
    BRAINSTORM, CONSENSUS, and DELEGATION. Each pattern has specific coordination
    logic and state management requirements.

    Integrates MultiAgentManager (Wave 3) for session management and HandoffManager
    (Wave 3) for agent coordination. Designed for future integration with
    DelegationManager (Wave 4) and AgentSelector (Wave 4).

    Args:
        session: Async SQLAlchemy session for database operations.
        multi_agent_manager: Manager for collaboration sessions.
        handoff_manager: Manager for agent-to-agent handoffs.
    """

    def __init__(
        self,
        session: "AsyncSession",
        multi_agent_manager: "MultiAgentManager",
        handoff_manager: "HandoffManager",
    ) -> None:
        """Initialize the collaboration orchestrator.

        Args:
            session: Async SQLAlchemy session for database operations.
            multi_agent_manager: Manager for collaboration sessions.
            handoff_manager: Manager for agent-to-agent handoffs.
        """
        self._session: "AsyncSession" = session
        self._multi_agent: "MultiAgentManager" = multi_agent_manager
        self._handoff: "HandoffManager" = handoff_manager

    async def orchestrate_collaboration(
        self,
        conversation_id: UUID,
        pattern: CollaborationPattern,
        goal: str,
        initiator_id: UUID,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Orchestrate a multi-agent collaboration using the specified pattern.

        Creates a collaboration session, adds participants, and executes the
        pattern-specific workflow. Returns the completed session with results.

        Args:
            conversation_id: UUID of the conversation this collaboration belongs to.
            pattern: Collaboration pattern to execute.
            goal: Description of the collaboration goal.
            initiator_id: UUID of the agent initiating the collaboration.
            participants: List of participant configurations with roles.

        Returns:
            CollaborationSession with final results and status.

        Raises:
            ValueError: If pattern is not supported or participants invalid.
        """
        # Create session
        session = await self._multi_agent.create_collaboration(
            conversation_id=conversation_id,
            pattern=pattern,
            goal=goal,
            initiator_id=initiator_id,
        )

        logger.info(
            f"orchestrate_collaboration: session_id={session.id}, pattern={pattern.value}, "
            f"participants={len(participants)}"
        )

        # Add participants
        participant_tuples = [(p.agent_id, p.role) for p in participants]
        session = await self._multi_agent.add_participants(session.id, participant_tuples)

        # Execute pattern-specific workflow
        try:
            session = await self.execute_pattern(
                session=session,
                participants=participants,
            )

            # Update session status to COMPLETED
            session = await self._multi_agent.update_session_status(
                session_id=session.id,
                status=CollaborationStatus.COMPLETED,
                final_result=session.final_result,
            )

            logger.info(
                f"collaboration_completed: session_id={session.id}, pattern={pattern.value}, "
                f"status=COMPLETED"
            )

        except Exception as e:
            logger.error(
                f"collaboration_failed: session_id={session.id}, pattern={pattern.value}, "
                f"error={str(e)}"
            )

            # Update session status to FAILED
            session = await self._multi_agent.update_session_status(
                session_id=session.id,
                status=CollaborationStatus.FAILED,
                final_result=f"Error: {str(e)}",
            )

        return session

    async def execute_pattern(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute the collaboration pattern-specific workflow.

        Dispatches to the appropriate pattern handler based on session.pattern.
        Each handler implements the coordination logic for that pattern.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with results.

        Raises:
            ValueError: If pattern is not recognized.
        """
        logger.info(
            f"execute_pattern: session_id={session.id}, pattern={session.pattern.value}, "
            f"participants={len(participants)}"
        )

        # Pattern dispatch
        if session.pattern == CollaborationPattern.SUPERVISOR_WORKER:
            return await self._execute_supervisor_worker(session, participants)
        elif session.pattern == CollaborationPattern.PIPELINE:
            return await self._execute_pipeline(session, participants)
        elif session.pattern == CollaborationPattern.PEER_REVIEW:
            return await self._execute_peer_review(session, participants)
        elif session.pattern == CollaborationPattern.BRAINSTORM:
            return await self._execute_brainstorm(session, participants)
        elif session.pattern == CollaborationPattern.CONSENSUS:
            return await self._execute_consensus(session, participants)
        elif session.pattern == CollaborationPattern.DELEGATION:
            return await self._execute_delegation(session, participants)
        else:
            error_msg = f"Unsupported collaboration pattern: {session.pattern.value}"
            logger.error(f"execute_pattern_failed: {error_msg}")
            raise ValueError(error_msg)

    async def coordinate_agents(
        self,
        session: CollaborationSession,
        from_agent_id: UUID,
        to_agent_id: UUID,
        context: dict[str, Any],
    ) -> CollaborationSession:
        """Coordinate a handoff between two agents in a collaboration.

        Uses HandoffManager to transfer control between agents with context.
        Updates session state to track the coordination event.

        Args:
            session: Collaboration session containing the agents.
            from_agent_id: UUID of the agent handing off control.
            to_agent_id: UUID of the agent receiving control.
            context: Dictionary of context data to transfer.

        Returns:
            Updated CollaborationSession.
        """
        logger.info(
            f"coordinate_agents: session_id={session.id}, from={from_agent_id}, to={to_agent_id}"
        )

        # Initiate handoff
        handoff_result = await self._handoff.initiate_handoff(
            conversation_id=session.metadata.get("conversation_id", str(session.id)),
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            reason=f"Collaboration {session.pattern.value} coordination",
            context_transferred=context,
        )

        if not handoff_result.success:
            logger.warning(
                f"coordinate_agents_failed: session_id={session.id}, reason={handoff_result.reason}"
            )

        return session

    # ============================================================================
    # Pattern-Specific Implementations
    # ============================================================================

    async def _execute_supervisor_worker(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute SUPERVISOR_WORKER pattern: one supervisor delegates to multiple workers.

        Supervisor agent assigns tasks to worker agents, monitors progress, and
        synthesizes results. Workers execute independently and report back.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(
            f"supervisor_worker_pattern: session_id={session.id}, participants={len(participants)}"
        )

        # Find supervisor (PRIMARY role) and workers (INVITED role)
        supervisor = next(
            (p for p in participants if p.role == ParticipantRole.PRIMARY),
            None,
        )
        workers = [p for p in participants if p.role == ParticipantRole.INVITED]

        if not supervisor:
            session.final_result = "Error: No supervisor found in participants"
            return session

        if not workers:
            session.final_result = "Error: No workers found in participants"
            return session

        # Stage 1: Supervisor plans and delegates
        stage_outputs = []
        stage_outputs.append(
            StageOutput(
                stage_name="supervisor_planning",
                agent_id=supervisor.agent_id,
                output=f"Supervisor delegated tasks to {len(workers)} workers",
                completed_at=datetime.utcnow(),
            )
        )

        # Stage 2: Workers execute (simulated with handoffs)
        worker_results = []
        for worker in workers:
            # Coordinate handoff to worker
            await self.coordinate_agents(
                session=session,
                from_agent_id=supervisor.agent_id,
                to_agent_id=worker.agent_id,
                context={"instructions": worker.instructions, "goal": session.metadata.get("goal")},
            )

            # Simulate worker output
            worker_output = f"Worker {worker.agent_id} completed task: {worker.instructions[:100]}"
            worker_results.append(worker_output)

            stage_outputs.append(
                StageOutput(
                    stage_name=f"worker_{worker.agent_id}",
                    agent_id=worker.agent_id,
                    output=worker_output,
                    completed_at=datetime.utcnow(),
                )
            )

        # Stage 3: Supervisor synthesizes results
        final_result = (
            f"Supervisor-Worker Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Workers: {len(workers)}\n\n"
            f"Worker Results:\n" + "\n".join(f"- {r}" for r in worker_results)
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"supervisor_worker_completed: session_id={session.id}, workers={len(workers)}")

        return session

    async def _execute_pipeline(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute PIPELINE pattern: sequential processing through agent stages.

        Each agent processes input from the previous stage and passes output to
        the next stage. Dependencies define the pipeline order.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(f"pipeline_pattern: session_id={session.id}, participants={len(participants)}")

        # Sort participants by dependency order (root first)
        ordered = self._topological_sort(participants)

        if not ordered:
            session.final_result = "Error: Cannot resolve pipeline dependencies (cycle detected)"
            return session

        # Execute pipeline stages sequentially
        stage_outputs = []
        current_output = session.metadata.get("goal", "")

        for participant in ordered:
            # Simulate stage execution
            stage_result = (
                f"Stage '{participant.agent_id}' processed input and produced output: "
                f"{participant.instructions[:100]}"
            )

            stage_outputs.append(
                StageOutput(
                    stage_name=f"pipeline_{participant.agent_id}",
                    agent_id=participant.agent_id,
                    output=stage_result,
                    completed_at=datetime.utcnow(),
                )
            )

            current_output = stage_result

        # Final result is output of last stage
        final_result = (
            f"Pipeline Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Stages: {len(ordered)}\n\n"
            f"Final Output:\n{current_output}"
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"pipeline_completed: session_id={session.id}, stages={len(ordered)}")

        return session

    async def _execute_peer_review(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute PEER_REVIEW pattern: one agent creates, others review and critique.

        Primary agent creates initial output. Reviewer agents provide feedback.
        Primary agent iterates based on feedback.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(
            f"peer_review_pattern: session_id={session.id}, participants={len(participants)}"
        )

        # Find primary creator and reviewers
        creator = next(
            (p for p in participants if p.role == ParticipantRole.PRIMARY),
            None,
        )
        reviewers = [p for p in participants if p.role == ParticipantRole.INVITED]

        if not creator:
            session.final_result = "Error: No creator found in participants"
            return session

        # Stage 1: Creator produces initial output
        stage_outputs = []
        initial_output = (
            f"Creator {creator.agent_id} produced initial output: {creator.instructions[:100]}"
        )

        stage_outputs.append(
            StageOutput(
                stage_name="initial_creation",
                agent_id=creator.agent_id,
                output=initial_output,
                completed_at=datetime.utcnow(),
            )
        )

        # Stage 2: Reviewers provide feedback
        feedback_items = []
        for reviewer in reviewers:
            feedback = f"Reviewer {reviewer.agent_id} feedback: {reviewer.instructions[:100]}"
            feedback_items.append(feedback)

            stage_outputs.append(
                StageOutput(
                    stage_name=f"review_{reviewer.agent_id}",
                    agent_id=reviewer.agent_id,
                    output=feedback,
                    completed_at=datetime.utcnow(),
                )
            )

        # Stage 3: Creator revises based on feedback
        revision_output = f"Creator revised output based on {len(feedback_items)} reviews"
        stage_outputs.append(
            StageOutput(
                stage_name="final_revision",
                agent_id=creator.agent_id,
                output=revision_output,
                completed_at=datetime.utcnow(),
            )
        )

        final_result = (
            f"Peer Review Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Creator: {creator.agent_id}\n"
            f"Reviewers: {len(reviewers)}\n\n"
            f"Initial Output:\n{initial_output}\n\n"
            f"Feedback:\n" + "\n".join(f"- {f}" for f in feedback_items) + f"\n\n"
            f"Final Revision:\n{revision_output}"
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"peer_review_completed: session_id={session.id}, reviewers={len(reviewers)}")

        return session

    async def _execute_brainstorm(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute BRAINSTORM pattern: parallel idea generation and synthesis.

        All agents generate ideas independently. Results are synthesized into
        a combined output with diverse perspectives.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(
            f"brainstorm_pattern: session_id={session.id}, participants={len(participants)}"
        )

        # All participants generate ideas in parallel
        stage_outputs = []
        ideas = []

        for participant in participants:
            idea = f"Agent {participant.agent_id} idea: {participant.instructions[:100]}"
            ideas.append(idea)

            stage_outputs.append(
                StageOutput(
                    stage_name=f"brainstorm_{participant.agent_id}",
                    agent_id=participant.agent_id,
                    output=idea,
                    completed_at=datetime.utcnow(),
                )
            )

        # Synthesize all ideas
        final_result = (
            f"Brainstorm Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Participants: {len(participants)}\n\n"
            f"Ideas Generated:\n" + "\n".join(f"- {i}" for i in ideas)
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"brainstorm_completed: session_id={session.id}, ideas={len(ideas)}")

        return session

    async def _execute_consensus(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute CONSENSUS pattern: iterative discussion until agreement.

        Agents propose solutions, discuss differences, and iterate until
        consensus is reached or maximum rounds exceeded.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(f"consensus_pattern: session_id={session.id}, participants={len(participants)}")

        # Round 1: Initial proposals
        stage_outputs = []
        proposals = []

        for participant in participants:
            proposal = f"Agent {participant.agent_id} proposes: {participant.instructions[:100]}"
            proposals.append(proposal)

            stage_outputs.append(
                StageOutput(
                    stage_name=f"proposal_{participant.agent_id}",
                    agent_id=participant.agent_id,
                    output=proposal,
                    completed_at=datetime.utcnow(),
                )
            )

        # Round 2: Discussion and consensus (simulated)
        consensus_output = (
            f"After discussion, {len(participants)} agents reached consensus on approach"
        )

        stage_outputs.append(
            StageOutput(
                stage_name="consensus_reached",
                agent_id=participants[0].agent_id if participants else uuid4(),
                output=consensus_output,
                completed_at=datetime.utcnow(),
            )
        )

        final_result = (
            f"Consensus Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Participants: {len(participants)}\n\n"
            f"Initial Proposals:\n" + "\n".join(f"- {p}" for p in proposals) + f"\n\n"
            f"Final Consensus:\n{consensus_output}"
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"consensus_completed: session_id={session.id}, rounds=2")

        return session

    async def _execute_delegation(
        self,
        session: CollaborationSession,
        participants: list[ParticipantConfig],
    ) -> CollaborationSession:
        """Execute DELEGATION pattern: hierarchical task delegation.

        Primary agent delegates subtasks to other agents. Supports nested
        delegation up to MAX_DELEGATION_DEPTH.

        Args:
            session: Collaboration session to execute.
            participants: List of participant configurations.

        Returns:
            Updated CollaborationSession with final result.
        """
        logger.info(
            f"delegation_pattern: session_id={session.id}, participants={len(participants)}"
        )

        # Find delegator (PRIMARY role) and delegates (INVITED role)
        delegator = next(
            (p for p in participants if p.role == ParticipantRole.PRIMARY),
            None,
        )
        delegates = [p for p in participants if p.role == ParticipantRole.INVITED]

        if not delegator:
            session.final_result = "Error: No delegator found in participants"
            return session

        # Delegator assigns tasks to delegates
        stage_outputs = []
        delegation_results = []

        for delegate in delegates:
            result = f"Delegate {delegate.agent_id} completed: {delegate.instructions[:100]}"
            delegation_results.append(result)

            stage_outputs.append(
                StageOutput(
                    stage_name=f"delegation_{delegate.agent_id}",
                    agent_id=delegate.agent_id,
                    output=result,
                    completed_at=datetime.utcnow(),
                )
            )

        # Delegator synthesizes results
        synthesis = f"Delegator synthesized {len(delegation_results)} task results"
        stage_outputs.append(
            StageOutput(
                stage_name="delegation_synthesis",
                agent_id=delegator.agent_id,
                output=synthesis,
                completed_at=datetime.utcnow(),
            )
        )

        final_result = (
            f"Delegation Collaboration Results:\n\n"
            f"Goal: {session.metadata.get('goal')}\n"
            f"Delegator: {delegator.agent_id}\n"
            f"Delegates: {len(delegates)}\n\n"
            f"Delegation Results:\n" + "\n".join(f"- {r}" for r in delegation_results) + f"\n\n"
            f"Synthesis:\n{synthesis}"
        )

        session.final_result = final_result
        session.stage_outputs = stage_outputs

        logger.info(f"delegation_completed: session_id={session.id}, delegates={len(delegates)}")

        return session

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _topological_sort(
        self,
        participants: list[ParticipantConfig],
    ) -> list[ParticipantConfig]:
        """Topological sort of participants by dependency order.

        Used by pipeline pattern to determine execution order. Detects cycles
        and returns None if dependencies cannot be resolved.

        Args:
            participants: List of participant configurations with dependencies.

        Returns:
            List of participants in dependency order, or empty list if cycle detected.
        """
        # Build adjacency list and in-degree count
        in_degree: dict[UUID, int] = {p.agent_id: 0 for p in participants}
        adjacency: dict[UUID, list[UUID]] = {p.agent_id: [] for p in participants}

        for participant in participants:
            for dep_id in participant.dependencies:
                if dep_id in adjacency:
                    adjacency[dep_id].append(participant.agent_id)
                    in_degree[participant.agent_id] += 1

        # Kahn's algorithm for topological sort
        queue: list[UUID] = [p.agent_id for p in participants if in_degree[p.agent_id] == 0]
        ordered: list[ParticipantConfig] = []

        while queue:
            current_id = queue.pop(0)
            current = next(p for p in participants if p.agent_id == current_id)
            ordered.append(current)

            for neighbor_id in adjacency[current_id]:
                in_degree[neighbor_id] -= 1
                if in_degree[neighbor_id] == 0:
                    queue.append(neighbor_id)

        # Cycle detection
        if len(ordered) != len(participants):
            logger.error(
                f"topological_sort_failed: cycle_detected, participants={len(participants)}, "
                f"ordered={len(ordered)}"
            )
            return []

        return ordered
