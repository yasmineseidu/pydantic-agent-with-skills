"""Run evaluation suite for skill-based agent."""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Any
from pydantic_evals import Dataset
from src.agent import skill_agent
from src.dependencies import AgentDependencies
from tests.evals.evaluators import (
    SkillWasLoaded,
    ToolWasCalled,
    ResponseContains,
    ResponseNotEmpty,
)

# All custom evaluators must be registered
CUSTOM_EVALUATORS = [
    SkillWasLoaded,
    ToolWasCalled,
    ResponseContains,
    ResponseNotEmpty,
]


def extract_tool_calls(result: Any) -> list[tuple[str, dict]]:
    """
    Extract tool calls from agent result messages.

    Returns list of (tool_name, args) tuples.
    """
    tool_calls = []

    for msg in result.all_messages():
        if hasattr(msg, 'parts'):
            for part in msg.parts:
                if hasattr(part, 'part_kind') and part.part_kind == 'tool-call':
                    tool_name = part.tool_name
                    # Extract args - use args_as_dict() method
                    args = {}
                    if hasattr(part, 'args_as_dict'):
                        args = part.args_as_dict()
                    tool_calls.append((tool_name, args))

    return tool_calls


async def run_agent_task(inputs: str) -> dict[str, Any]:
    """
    Run the agent and return structured output for evaluation.

    Returns dict with:
        - response: The agent's text response
        - tools_called: List of (tool_name, args) tuples
    """
    deps = AgentDependencies()
    await deps.initialize()

    result = await skill_agent.run(inputs, deps=deps)

    # Extract tool calls from messages
    tool_calls = extract_tool_calls(result)

    return {
        'response': result.output,
        'tools_called': tool_calls,
    }


async def run_evals(dataset_name: str = None, verbose: bool = False) -> int:
    """
    Execute evaluation suite against the skill agent.

    Args:
        dataset_name: Specific dataset to run (None = all)
        verbose: Show detailed output including reasons

    Returns:
        Exit code (0 = success, 1 = failures)
    """
    evals_dir = Path('tests/evals')

    # Select datasets to run
    if dataset_name:
        yaml_files = [evals_dir / f'{dataset_name}.yaml']
    else:
        yaml_files = list(evals_dir.glob('*.yaml'))

    print("\n" + "=" * 60)
    print("RUNNING EVALUATIONS")
    print("=" * 60)

    all_passed = True
    total_cases = 0
    passed_cases = 0

    for yaml_file in yaml_files:
        if not yaml_file.exists():
            print(f"\n[WARNING] Skipping {yaml_file.name} - not found")
            continue


        print(f"\n{'=' * 60}")
        print(f"Running: {yaml_file.stem}")
        print(f"{'=' * 60}\n")

        try:
            # Load dataset with custom evaluators
            dataset = Dataset.from_file(
                yaml_file,
                custom_evaluator_types=CUSTOM_EVALUATORS,
            )

            print(f"Loaded {len(dataset.cases)} test cases")

            # Run evaluation
            print("Running evaluations...")
            report = await dataset.evaluate(run_agent_task)

            # Print results with ASCII-safe formatting
            print("\nResults:")
            print("-" * 60)

            # Process successful cases
            for case in report.cases:
                case_name = case.name
                total_cases += 1

                # Check all assertions (boolean evaluators)
                case_passed = True
                eval_details = []

                # Check assertions (boolean results)
                for eval_name, eval_result in case.assertions.items():
                    value = eval_result.value
                    passed = value is True

                    if not passed:
                        case_passed = False

                    status = "PASS" if passed else "FAIL"
                    reason = ""
                    if eval_result.reason:
                        reason = f" - {eval_result.reason}"

                    eval_details.append(f"    [{status}] {eval_name}{reason}")

                # Check scores (numeric results - pass if > 0)
                for eval_name, eval_result in case.scores.items():
                    value = eval_result.value
                    passed = value > 0

                    if not passed:
                        case_passed = False

                    status = "PASS" if passed else "FAIL"
                    reason = ""
                    if eval_result.reason:
                        reason = f" - {eval_result.reason}"

                    eval_details.append(f"    [{status}] {eval_name}: {value}{reason}")

                if case_passed:
                    passed_cases += 1
                    print(f"[PASS] {case_name}")
                else:
                    all_passed = False
                    print(f"[FAIL] {case_name}")

                if verbose or not case_passed:
                    for detail in eval_details:
                        print(detail)

            # Process failures
            for failure in report.failures:
                total_cases += 1
                all_passed = False
                print(f"[ERROR] {failure.name}: {failure.error}")

            print("-" * 60)
            print(f"Cases: {passed_cases}/{total_cases} passed")

        except Exception as e:
            print(f"  [ERROR] {e}")
            all_passed = False
            if verbose:
                import traceback
                traceback.print_exc()

    print("\n" + "=" * 60)
    summary = "ALL PASSED" if all_passed else "SOME FAILURES"
    print(f"EVALUATION COMPLETE: {summary}")
    print(f"Total: {passed_cases}/{total_cases} cases passed")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run skill agent evaluations')
    parser.add_argument('--dataset', help='Specific dataset to run')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()
    exit_code = asyncio.run(run_evals(args.dataset, args.verbose))
    sys.exit(exit_code)
