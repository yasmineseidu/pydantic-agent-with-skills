---
paths: ["skills/**", "src/skill_*.py"]
---

# Progressive Disclosure Pattern

## The Three Levels

**Level 1 - Metadata Discovery (Always Loaded)**
```yaml
# In system prompt - minimal tokens (~100 per skill)
---
name: weather
description: Get weather information for locations. Use when user asks about weather.
---
```

**Level 2 - Full Instructions (Loaded on Invocation)**
```python
agent.call_tool("load_skill", skill_name="weather")
# Returns: Full SKILL.md body with detailed instructions
```

**Level 3 - Resources (Loaded on Demand)**
```python
agent.call_tool("read_skill_file",
    skill_name="weather",
    file_path="references/api_reference.md"
)
```

## Skill Directory Structure

```
skills/skill-name/
├── SKILL.md                 # YAML frontmatter + instructions
├── scripts/                 # Optional: Python/Bash scripts
├── references/              # Optional: Documentation, guides
└── assets/                  # Optional: Templates, data files
```

## SKILL.md Format

```markdown
---
name: skill-name
description: Brief description for agent discovery (1-2 sentences)
version: 1.0.0
author: Your Name
---

# Skill Name

Brief overview of what this skill does.

## When to Use
## Available Operations
## Instructions
## Resources
## Examples
## Notes
```

## SkillLoader Class

Core responsibilities:
1. Scan `skills/` directory for skill folders
2. Parse YAML frontmatter from SKILL.md files
3. Maintain skill metadata registry
4. Generate system prompt section with skill metadata

## SkillMetadata Model

```python
class SkillMetadata(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    skill_path: Path
```

## Skill Tools

### load_skill (Level 2)
Load full instructions when agent decides to use a skill. Strips YAML frontmatter, returns body only.

### read_skill_file (Level 3)
Load specific resource files. Validates file is within skill directory (path traversal prevention).

### list_skill_files (Resource Discovery)
Lists all files available in a skill's directory tree.
