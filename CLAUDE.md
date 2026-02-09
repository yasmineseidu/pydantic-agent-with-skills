# Custom Skill-Based Pydantic AI Agent Development Instructions

## Project Overview

Framework-agnostic skill system for AI agents that extracts the progressive disclosure pattern from Claude Skills and implements it as a native feature in Pydantic AI. This system enables developers to build AI agents with modular, reusable skills that load instructions and resources on-demand, eliminating context window constraints while maintaining type safety and testability.

**Key Innovation**: Unlike Claude Skills which are locked to the Claude ecosystem, this implementation makes advanced skill capabilities available to ANY AI agent framework. Demonstrates how to take successful patterns from proprietary systems and apply them to open frameworks.

## Core Principles

@.claude/rules/coding-principles.md

**Architecture:**

```
custom-skill-agent/
├── src/                      # Skill-based agent implementation
│   ├── agent.py              # Pydantic AI agent with skills
│   ├── skill_loader.py       # Skill discovery and metadata
│   ├── skill_tools.py        # Progressive disclosure tools
│   ├── dependencies.py       # AgentDependencies with SkillLoader
│   ├── providers.py          # LLM provider configuration
│   ├── settings.py           # Pydantic Settings
│   ├── prompts.py            # Skill-aware system prompts
│   └── cli.py                # Rich-based CLI
├── skills/                   # Skill library
│   ├── weather/              # Simple skill demo
│   └── code_review/          # Advanced skill demo
├── examples/                 # MongoDB RAG reference (DO NOT MODIFY)
└── tests/                    # Test suite
```

---

## Documentation Style

@.claude/rules/documentation-style.md

---

## Development Workflow

**Setup environment:**
```bash
# Create virtual environment
python -m venv .venv

# Activate environment
source .venv/bin/activate  # Unix
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
# Or if using uv:
uv pip install -e .
```

**Run CLI agent:**
```bash
python -m src.cli
```

**Run tests:**
```bash
pytest tests/ -v
```

---

## Configuration Management

@.claude/rules/configuration.md

---

## Progressive Disclosure Pattern

@.claude/rules/skill-system.md

---

## Agent Dependencies

**Adapted from examples/dependencies.py but simpler (no database):**

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
from src.skill_loader import SkillLoader
from src.settings import load_settings

@dataclass
class AgentDependencies:
    """Dependencies injected into the agent context."""

    # Skill system
    skill_loader: Optional[SkillLoader] = None

    # Session context
    session_id: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # Configuration
    settings: Optional[Any] = None

    async def initialize(self) -> None:
        """Initialize skill loader and settings."""
        if not self.settings:
            self.settings = load_settings()

        if not self.skill_loader:
            skills_dir = Path(self.settings.skills_dir)
            self.skill_loader = SkillLoader(skills_dir)
            self.skill_loader.discover_skills()

            print(f"Loaded {len(self.skill_loader.skills)} skills:")
            for skill in self.skill_loader.skills.values():
                print(f"  - {skill.name}: {skill.description}")
```

---

## Pydantic AI Agent Integration

### Agent Definition

**Dynamic system prompt with skill metadata:**

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from src.providers import get_llm_model
from src.dependencies import AgentDependencies
from src.prompts import MAIN_SYSTEM_PROMPT

class AgentState(BaseModel):
    """Minimal shared state for the agent."""
    pass

# Create agent
skill_agent = Agent(
    get_llm_model(),
    deps_type=AgentDependencies,
    system_prompt=""  # Will be set dynamically
)

# Dynamic system prompt with skill metadata
@skill_agent.system_prompt
async def get_system_prompt(ctx: RunContext[AgentDependencies]) -> str:
    """Generate system prompt with skill metadata."""
    await ctx.deps.initialize()
    skill_metadata = ctx.deps.skill_loader.get_skill_metadata_prompt()
    return MAIN_SYSTEM_PROMPT.format(skill_metadata=skill_metadata)
```

### Tool Registration

**Register skill tools with agent:**

```python
from src.skill_tools import load_skill, read_skill_file, list_skill_files

@skill_agent.tool
async def load_skill_tool(
    ctx: RunContext[AgentDependencies],
    skill_name: str
) -> str:
    """Load full instructions for a skill."""
    return await load_skill(ctx, skill_name)

@skill_agent.tool
async def read_skill_file_tool(
    ctx: RunContext[AgentDependencies],
    skill_name: str,
    file_path: str
) -> str:
    """Read a file from a skill's directory."""
    return await read_skill_file(ctx, skill_name, file_path)

@skill_agent.tool
async def list_skill_files_tool(
    ctx: RunContext[AgentDependencies],
    skill_name: str,
    directory: str = ""
) -> str:
    """List files available in a skill's directory."""
    return await list_skill_files(ctx, skill_name, directory)
```

---

## Testing

@.claude/rules/testing-patterns.md

---

## Common Pitfalls

@.claude/rules/common-pitfalls.md

---

## Quick Reference

**Skill Discovery:**
```python
loader = SkillLoader(Path("skills"))
skills = loader.discover_skills()
prompt_section = loader.get_skill_metadata_prompt()
```

**Progressive Disclosure:**
```python
# Level 1: Metadata in system prompt (automatic)
# Level 2: Load full instructions
instructions = await load_skill(ctx, "weather")

# Level 3: Load resources
api_docs = await read_skill_file(ctx, "weather", "references/api_reference.md")
```

**Pydantic AI Agent:**
```python
# Define agent
agent = Agent(model, deps_type=AgentDependencies, system_prompt="")

# Add dynamic system prompt
@agent.system_prompt
async def get_prompt(ctx: RunContext[AgentDependencies]) -> str:
    await ctx.deps.initialize()
    return generate_prompt_with_skills(ctx.deps.skill_loader)

# Add tool
@agent.tool
async def tool_func(ctx: RunContext[AgentDependencies], arg: str) -> str:
    """Tool description."""
    pass
```

---

## Implementation-Specific References

For detailed implementation patterns, see:

- **PRD**: `.claude/PRD.md` - Complete product requirements and architecture
- **Examples Reference**: `examples/` - Production MongoDB RAG agent patterns
  - `examples/agent.py` - Pydantic AI agent structure
  - `examples/dependencies.py` - Dependency injection pattern
  - `examples/cli.py` - Rich CLI with streaming
  - `examples/settings.py` - Pydantic Settings configuration

---

## Workshop Context

This project serves as a workshop demonstration showing how to:
1. Extract successful patterns from proprietary systems (Claude Skills)
2. Implement those patterns in open frameworks (Pydantic AI)
3. Build framework-agnostic, reusable components
4. Scale beyond context window limitations through progressive disclosure

**Key Demonstration Points:**
- Progressive disclosure eliminates context window constraints
- Skills are portable across any AI framework
- Type-safe, testable agent architecture
- Simple, understandable implementation

**Workshop Deliverables:**
- Complete working skill-based agent
- Two demo skills (Weather, Code Review)
- Clear documentation of progressive disclosure pattern
- Attendees can extend with their own skills

---

# Agent Team System

@.claude/rules/agent-system.md

## Mandatory Practices

@.claude/rules/mandatory-practices.md

## Security

@.claude/rules/security.md

## Detected Commands

```bash
# Development
python -m src.cli          # Run the CLI agent
pytest tests/ -v           # Run all tests
ruff format src/ tests/    # Format code
ruff check src/ tests/     # Lint code
ruff check --fix src/ tests/  # Auto-fix lint issues
mypy src/                  # Type checking
uv pip install -e .        # Install dependencies
```

## Project Structure

```
src/                       # Core agent implementation (8 modules)
skills/                    # 5 skill directories (weather, code_review, etc.)
tests/                     # pytest test suite (mirrors src/)
scripts/                   # Utility scripts
.claude/agents/            # 19 agent definitions
.claude/skills/            # 4 agent team skills
.claude/rules/             # 9 modular path-scoped rules
.claude/commands/          # Claude Code slash commands
.claude/plans/             # Implementation plans
team-registry/             # Team definitions and run logs
reports/                   # PRD decomposition and review reports
```

## CI/CD

No CI/CD pipeline detected. When one is added:
- Tests: `pytest tests/ -v`
- Lint: `ruff check src/ tests/`
- Types: `mypy src/`
- Format: `ruff format --check src/ tests/`
