---
paths: ["tests/**", "src/**/*.py"]
---

# Testing Patterns

Tests mirror the src directory structure:

```
src/agent.py            ->  tests/test_agent.py
src/skill_loader.py     ->  tests/test_skill_loader.py
src/skill_tools.py      ->  tests/test_skill_tools.py
```

## Unit Tests

```python
import pytest
from pathlib import Path
from src.skill_loader import SkillLoader, SkillMetadata

@pytest.mark.unit
def test_skill_loader_discovers_skills(tmp_path):
    """Test that skill loader discovers skills correctly."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: test_skill
description: A test skill
version: 1.0.0
---

# Test Skill

This is a test.
""")

    loader = SkillLoader(tmp_path)
    skills = loader.discover_skills()

    assert len(skills) == 1
    assert skills[0].name == "test_skill"
    assert skills[0].description == "A test skill"
```

## Integration Tests

```python
@pytest.mark.integration
async def test_agent_loads_skill(skill_agent, mock_skill):
    """Test that agent can load a skill via tool call."""
    deps = AgentDependencies()
    await deps.initialize()

    ctx = RunContext(deps=deps)
    result = await load_skill(ctx, "test_skill")

    assert "Test Skill" in result
    assert result.startswith("# Test Skill")
```

## Mock Patterns

```python
@dataclass
class MockDependencies:
    skill_loader: Optional[SkillLoader] = None

@dataclass
class MockContext:
    deps: MockDependencies = field(default_factory=MockDependencies)
```

## Commands

```bash
pytest tests/ -v           # Run all tests
ruff check src/ tests/     # Lint
ruff format src/ tests/    # Format
mypy src/                  # Type checking
```
