"""Custom evaluators for skill-based agent.

These evaluators work with AgentOutput which contains both the response
and tool call information extracted from the agent run.
"""

from dataclasses import dataclass
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, EvaluationReason


@dataclass
class SkillWasLoaded(Evaluator):
    """Verify that load_skill_tool was called with the expected skill name.

    Works with task functions that return a dict with 'tools_called' key
    containing a list of (tool_name, args) tuples.
    """

    skill_name: str

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        """Check if correct skill was loaded via tool call."""
        output = ctx.output

        # Handle dict output with tool call info
        if isinstance(output, dict) and "tools_called" in output:
            tools = output["tools_called"]
            for tool_name, args in tools:
                if tool_name == "load_skill_tool":
                    called_skill = args.get("skill_name", "")
                    if called_skill == self.skill_name:
                        return EvaluationReason(
                            value=True, reason=f'Correctly loaded "{self.skill_name}" skill'
                        )

            # Check if load_skill_tool was called at all
            tool_names = [t[0] for t in tools]
            if "load_skill_tool" in tool_names:
                return EvaluationReason(
                    value=False,
                    reason=f'load_skill_tool called but with wrong skill (expected "{self.skill_name}")',
                )

            return EvaluationReason(
                value=False, reason=f"load_skill_tool was NOT called (tools called: {tool_names})"
            )

        return EvaluationReason(value=False, reason="Output does not contain tool call information")


@dataclass
class ToolWasCalled(Evaluator):
    """Verify a specific tool was called during execution.

    Works with task functions that return a dict with 'tools_called' key.
    """

    tool_name: str

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        """Check if tool was called."""
        output = ctx.output

        if isinstance(output, dict) and "tools_called" in output:
            tool_names = [t[0] for t in output["tools_called"]]

            if self.tool_name in tool_names:
                return EvaluationReason(value=True, reason=f'Tool "{self.tool_name}" was called')

            return EvaluationReason(
                value=False, reason=f'Tool "{self.tool_name}" was NOT called (tools: {tool_names})'
            )

        return EvaluationReason(value=False, reason="Output does not contain tool call information")


@dataclass
class ResponseContains(Evaluator):
    """Verify the response contains expected text.

    Works with task functions that return a dict with 'response' key.
    """

    text: str
    case_sensitive: bool = False

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        """Check if response contains the expected text."""
        output = ctx.output

        # Handle dict output
        if isinstance(output, dict) and "response" in output:
            response = output["response"]
        elif isinstance(output, str):
            response = output
        else:
            return EvaluationReason(value=False, reason="Cannot extract response from output")

        check_response = response if self.case_sensitive else response.lower()
        check_text = self.text if self.case_sensitive else self.text.lower()

        if check_text in check_response:
            return EvaluationReason(value=True, reason=f'Response contains "{self.text}"')

        return EvaluationReason(value=False, reason=f'Response does NOT contain "{self.text}"')


@dataclass
class ResponseNotEmpty(Evaluator):
    """Verify the response is not empty.

    Works with task functions that return a dict with 'response' key.
    """

    min_length: int = 10

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        """Check if response has minimum length."""
        output = ctx.output

        # Handle dict output
        if isinstance(output, dict) and "response" in output:
            response = output["response"]
        elif isinstance(output, str):
            response = output
        else:
            return EvaluationReason(value=False, reason="Cannot extract response from output")

        if len(response) >= self.min_length:
            return EvaluationReason(
                value=True, reason=f"Response has {len(response)} chars (min: {self.min_length})"
            )

        return EvaluationReason(
            value=False,
            reason=f"Response too short: {len(response)} chars (min: {self.min_length})",
        )
