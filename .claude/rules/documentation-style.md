---
paths: ["**/*.py", "**/*.md"]
---

# Documentation Style

## Google-style Docstrings

Use Google-style docstrings for all functions, classes, and modules:

```python
async def load_skill(
    ctx: RunContext[AgentDependencies],
    skill_name: str
) -> str:
    """
    Load the full instructions for a skill (Level 2 progressive disclosure).

    Args:
        ctx: Agent runtime context with dependencies
        skill_name: Name of the skill to load

    Returns:
        Full skill instructions from SKILL.md

    Raises:
        ValueError: If skill not found
    """
```

## Module Docstrings

Every module gets a one-line docstring:

```python
"""Progressive disclosure tools for skill-based agent."""
```

## Required Sections

- `Args:` - all parameters with types and descriptions
- `Returns:` - return type and description
- `Raises:` - exceptions that can be raised (if any)
