---
paths: ["src/**/*.py", "skills/**"]
---

# Common Pitfalls

## 1. Forgetting to Parse Frontmatter

```python
# WRONG - Returns frontmatter + body
def load_skill_wrong(skill_path):
    return skill_path.read_text()

# CORRECT - Strip frontmatter, return only body
def load_skill_correct(skill_path):
    content = skill_path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content
```

## 2. Missing File Path Security

```python
# WRONG - Directory traversal vulnerability
target_file = skill_path / file_path

# CORRECT - Validate file is within skill directory
target_file = skill_path / file_path
if not target_file.resolve().is_relative_to(skill_path.resolve()):
    raise SecurityError("File must be within skill directory")
```

## 3. Not Initializing Dependencies

```python
# WRONG - Dependencies not initialized
@skill_agent.tool
async def load_skill_tool(ctx: RunContext[AgentDependencies], skill_name: str) -> str:
    return await load_skill(ctx, skill_name)  # ctx.deps.skill_loader is None!

# CORRECT - Initialize dependencies first (via system_prompt decorator)
@skill_agent.system_prompt
async def get_system_prompt(ctx: RunContext[AgentDependencies]) -> str:
    await ctx.deps.initialize()  # Initialize before using
    return generate_prompt(ctx.deps.skill_loader)
```

## 4. Missing Type Hints

```python
# WRONG - No type hints
def load_skill(ctx, skill_name):
    return ctx.deps.skill_loader.skills[skill_name]

# CORRECT - Full type hints
async def load_skill(
    ctx: RunContext[AgentDependencies],
    skill_name: str
) -> str:
    return await ctx.deps.skill_loader.load_skill(skill_name)
```
