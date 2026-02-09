---
name: coding-conventions
description: Enforces existing codebase patterns for Python/Pydantic AI skill agent. Covers formatting, naming, imports, error handling, type annotations, and module boundaries.
version: 1.0.0
author: Agent Team System
---

# Coding Conventions

Codified patterns from the existing codebase. All agents MUST follow these conventions. Do NOT impose new patterns.

## Formatting

- **Tool**: ruff (formatter + linter combined)
- **Config**: `pyproject.toml` → `[tool.ruff]`
- **Line length**: 100 characters
- **Target**: Python 3.11
- **Command**: `ruff format src/ tests/` and `ruff check --fix src/ tests/`

## Naming Conventions

### Files & Modules
- **snake_case** for all Python files: `skill_loader.py`, `http_tools.py`
- **UPPER_CASE** for special files: `SKILL.md`, `CLAUDE.md`, `LEARNINGS.md`

### Functions & Variables
- **snake_case**: `discover_skills()`, `get_llm_model()`, `skill_metadata`
- **Async prefix**: async functions use descriptive names, no `async_` prefix
- **Private**: prefix with `_` for internal: `_parse_skill_metadata()`, `_http_client`

### Classes
- **PascalCase**: `SkillMetadata`, `AgentDependencies`, `Settings`
- **Test classes**: `TestSkillLoader`, `TestLoadSkill`

### Constants
- **UPPER_SNAKE_CASE**: `MAX_RETRIES`, `RETRY_BASE_DELAY`, `MAIN_SYSTEM_PROMPT`

## Import Ordering

Follow this group order (matches existing codebase):

```python
# 1. Standard library
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Literal
from dataclasses import dataclass, field

# 2. Third-party packages
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings
from pydantic_ai import Agent, RunContext
from rich.console import Console

# 3. Local imports (use absolute, not relative)
from src.settings import load_settings, Settings
from src.skill_loader import SkillLoader, SkillMetadata
from src.dependencies import AgentDependencies
```

**Rules:**
- Always use `from src.module import Name` (absolute imports)
- Never use relative imports (`from .module import ...`)
- TYPE_CHECKING imports for circular dependency prevention:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from src.dependencies import AgentDependencies
  ```

## Error Handling

### Pattern: try/except with structured logging
```python
try:
    result = operation()
    logger.info(f"operation_success: key={value}, result_length={len(result)}")
    return result
except SpecificError as e:
    logger.warning(f"operation_specific_error: key={value}, error={str(e)}")
    return f"Error: descriptive message"
except Exception as e:
    logger.exception(f"operation_error: key={value}, error={str(e)}")
    return f"Error: {str(e)}"
```

### Rules:
- Always catch specific exceptions first, then general `Exception`
- Use `logger.exception()` for unexpected errors (includes traceback)
- Use `logger.warning()` for expected failures (missing files, not found)
- Use `logger.info()` for success paths
- Return error strings from tool functions (don't raise)
- Use `raise ValueError(msg) from e` for configuration errors

### Logging Format
- Structured key-value: `f"action_name: key1={value1}, key2={value2}"`
- Logger per module: `logger = logging.getLogger(__name__)`

## Type Annotations

### Required everywhere:
```python
# Function signatures - full annotations
async def load_skill(
    ctx: RunContext["AgentDependencies"],
    skill_name: str,
) -> str:

# Variables with non-obvious types
discovered: List[SkillMetadata] = []
skills: Dict[str, SkillMetadata] = {}
_http_client: Optional[httpx.AsyncClient] = None

# Class fields
skill_loader: Optional[SkillLoader] = None
settings: Optional[Any] = None  # Only when truly dynamic
```

### Typing imports used in codebase:
- `Optional`, `Dict`, `List`, `Any`, `Union`, `Literal` from `typing`
- `Path` from `pathlib`
- `BaseModel`, `Field`, `ConfigDict` from `pydantic`

### mypy config:
- `python_version = "3.11"`
- `warn_return_any = true`

## Documentation Style

### Google-style docstrings on ALL public functions:
```python
async def load_skill(
    ctx: RunContext[AgentDependencies],
    skill_name: str,
) -> str:
    """
    Load the full instructions for a skill (Level 2 progressive disclosure).

    Args:
        ctx: Agent runtime context with dependencies
        skill_name: Name of the skill to load

    Returns:
        Full skill instructions from SKILL.md (body only, without frontmatter)

    Raises:
        ValueError: If skill not found
    """
```

### Module docstrings:
```python
"""Progressive disclosure tools for skill-based agent."""
```

## File/Folder Layout

```
src/                    → Core agent implementation
  agent.py              → Pydantic AI agent definition + tool registration
  cli.py                → Rich-based interactive CLI
  dependencies.py       → AgentDependencies (DI container)
  http_tools.py         → HTTP GET/POST with retry
  prompts.py            → System prompt templates
  providers.py          → LLM provider factory
  settings.py           → Pydantic Settings from .env
  skill_loader.py       → SkillLoader + SkillMetadata
  skill_tools.py        → Progressive disclosure tool implementations
  skill_toolset.py      → FunctionToolset wrapper
skills/                 → Skill definitions (each has SKILL.md)
tests/                  → pytest test suite (mirrors src/)
scripts/                → Utility/validation scripts
.claude/                → Agent infra, PRD, commands, plans
```

## Module Boundaries

- `settings.py` → No imports from other src modules
- `providers.py` → Imports only from settings
- `skill_loader.py` → Imports only from stdlib + pydantic + yaml
- `skill_tools.py` → Imports from skill_loader (TYPE_CHECKING for dependencies)
- `skill_toolset.py` → Imports from dependencies + skill_tools
- `dependencies.py` → Imports from skill_loader + settings
- `agent.py` → Imports from all modules (top-level orchestration)
- `cli.py` → Imports from agent + dependencies + settings
- `prompts.py` → No imports (pure string constants)

## Test Patterns

```python
# Test class naming
class TestSkillLoader:
    """Tests for SkillLoader class."""

# Test method naming
def test_skill_loader_discovers_skills(self, tmp_path: Path) -> None:

# Async tests
@pytest.mark.asyncio
async def test_load_weather_skill_returns_instructions(self) -> None:

# Mock pattern
@dataclass
class MockDependencies:
    skill_loader: Optional[SkillLoader] = None

@dataclass
class MockContext:
    deps: MockDependencies = field(default_factory=MockDependencies)
```

## Grep Local Codebase (MANDATORY - DO THIS FIRST)

**Before writing ANY code, grep THIS project to study existing patterns.**
This is the FIRST step. Always. No exceptions.

### Required Searches Before Coding
```
Grep "from src." src/           → Map import graph
Grep "class {Name}" src/        → Find existing class patterns
Grep "async def" src/           → Find async patterns
Grep "try:|except " src/        → Find error handling patterns
Grep "{function_name}" src/     → Check if it already exists
Glob "src/**/*.py"              → See all source files
Glob "tests/test_*.py"          → See all test files
Read the file you're about to modify
```

### What You're Looking For
- How existing code handles the same problem (don't reinvent)
- Import style, naming conventions, error return format
- Test patterns for the module you're changing
- Whether the function/class already exists somewhere

### Anti-Patterns
- Writing code without reading the target file first
- Assuming import style instead of grepping for it
- Creating a new utility that already exists in src/

## Grep MCP (MANDATORY - NON-NEGOTIABLE)

**AFTER grepping local, use `grep_query` to search millions of GitHub repos for battle-tested code.**
MCP server: `grep-mcp` (configured in `.claude/settings.json` + `~/.claude/settings.json`).
Applies to ALL coding agents.

### How to Search
```
grep_query: query="pydantic ai {feature}", language="python"
grep_query: query="{service} client async", language="python"
grep_query: query="{pattern} {framework}", language="python"
grep_query: query="{error message}", language="python"
grep_query: query="{function_name}", repo="owner/repo"        → search specific repo
grep_query: query="{pattern}", path="src/"                     → filter by path
```

### Workflow
1. `grep_query` with language="python" to find battle-tested implementations
2. Read the matched code snippets (includes file paths + line numbers)
3. Adapt to this project's conventions (imports, types, logging)
4. If your approach differs from battle-tested code, justify why

### Skip ONLY When
- Typo/string fix or < 5 lines changed
- Pattern already exists in this codebase (found via local grep)

## LSP Operations (MANDATORY - NON-NEGOTIABLE)

**Every code-editing agent MUST use LSP.** No exceptions. Applies to: builder,
reviewer, skill-builder, system-architect, tester, technical-researcher, architecture-designer.

### After EVERY Edit
```
LSP getDiagnostics on the edited file
→ If errors: fix immediately before continuing
→ If warnings: evaluate, fix if relevant
```

### Before Modifying a Function
```
LSP goToDefinition on the function
→ Read and understand current implementation
→ Check return type, parameters, side effects
```

### Before Renaming or Refactoring
```
LSP findReferences for the symbol
→ Count all usages across the codebase
→ Plan changes for ALL call sites before starting
→ Never rename without checking every reference
```

### When Unsure About Types
```
LSP hover on the variable/function
→ Verify actual type matches your assumption
→ If type mismatch: fix your code, not the type
```

### When Working with Interfaces/ABCs
```
LSP goToImplementation
→ Find all concrete implementations
→ Ensure changes are compatible with all implementations
```

### Failure Mode
If LSP is unavailable or returns no results:
- Fall back to `Grep` for finding references
- Fall back to `Read` + manual inspection for definitions
- NEVER skip the check entirely -- always verify before modifying

## Plan Before Execute (MANDATORY)

**Every agent MUST plan before executing non-trivial work.** Writing code without
a plan leads to rework, bugs, and wasted context.

### When to Plan (ALWAYS for these)
- Creating a new file or module
- Modifying more than 2 functions
- Changes that affect more than 1 file
- Any change where the approach isn't immediately obvious
- Implementing something you haven't built before in this codebase

### Plan Format (write in your output BEFORE coding)
```markdown
### Plan: [what you're about to do]
1. **Read**: [files you need to read first]
2. **Search**: [GitHub patterns to search for]
3. **Changes**: [exact list of changes, file by file]
4. **Dependencies**: [what must happen in what order]
5. **Verification**: [how you'll verify each change works]
6. **Rollback**: [how to undo if something breaks]
```

### Skip Planning ONLY When
- Fixing a typo or single-line change
- Running tests or linting (no code changes)
- Reading files for investigation

### Anti-Patterns (NEVER DO)
- Start editing without reading the target file first
- Make changes across multiple files without listing them
- "I'll figure it out as I go" -- ALWAYS plan first
- Skip the verification step in your plan

## Learning Protocol (MANDATORY - ALL AGENTS)

**Read LEARNINGS.md first. Write learnings last. Keep entries to 1 line each.**

### Startup
1. Read LEARNINGS.md
2. Grep LEARNINGS.md for keywords related to your task
3. Check "Mistakes" section for relevant traps

### Shutdown -- Write Concise Learnings
```markdown
### Learnings
- MISTAKE: {what went wrong} → {fix} (1 line)
- PATTERN: {what worked} → {how to reuse} (1 line)
- GOTCHA: {surprise} → {workaround} (1 line)
```

**Format rules:**
- 1 line per learning, max 120 chars
- No paragraphs, no filler, no "completed successfully"
- Only write learnings that help OTHERS avoid mistakes or reuse patterns
- Skip if nothing new was learned

## Task Progress Tracking (MANDATORY - ALL AGENTS)

**Every piece of work MUST be tracked via TaskUpdate.** No untracked work.

### When You Receive a Task
```
TaskUpdate: status = "in_progress"
→ You are now accountable for this task
```

### During Work
```
If blocked: TaskUpdate status stays "in_progress", report BLOCKER in output
If scope changes: note in output, coordinator creates new tasks
```

### When Complete
```
TaskUpdate: status = "completed"
→ Only mark complete when ALL verification passes
→ NEVER mark complete if tests fail or errors remain
```

### When Stuck
```
Keep status "in_progress"
Report what's blocking you in your output
Coordinator will route to the right agent or escalate
```

### Anti-Patterns (NEVER DO)
- Do work without an associated task
- Mark task complete before running verification
- Silently abandon a task (always report status)
- Create your own tasks (that's the coordinator's job)

## Enforcement Layers

1. **Grep MCP**: Search GitHub before writing new code (NON-NEGOTIABLE)
2. **LSP**: getDiagnostics after every edit, goToDefinition before modifying (NON-NEGOTIABLE)
3. **Plan**: Outline changes before implementing (NON-NEGOTIABLE)
4. **Learning**: Read LEARNINGS.md first, write learnings last (NON-NEGOTIABLE)
5. **Task tracking**: TaskUpdate in_progress/completed on every task (NON-NEGOTIABLE)
6. **ruff format**: Auto-formats on save/hook
7. **ruff check**: Linting errors block commits
8. **mypy**: Type errors block commits
9. **pytest**: Test failures block merges
10. **Review agent**: Checks all enforcement during review
11. **This skill**: Agents reference before writing code
