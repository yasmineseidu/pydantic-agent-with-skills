# Interface Contracts

Shared interfaces between modules. Coordinator-managed to prevent conflicts.

## Existing Interfaces

### Settings -> All Modules
**Owner**: builder
**Contract**:
- Input: `.env` file with environment variables
- Output: `Settings` object with typed fields
- Access: `load_settings() -> Settings`
- Error: `ValueError` if required fields missing

### AgentDependencies -> Agent Tools
**Owner**: builder
**Contract**:
- Input: `AgentDependencies` with `skill_loader`, `settings`
- Output: Initialized dependencies via `await deps.initialize()`
- Access: `ctx.deps.skill_loader`, `ctx.deps.settings`
- Error: `None` check on `skill_loader` before use

### SkillLoader -> Skill Tools
**Owner**: builder
**Contract**:
- Input: `skills_dir: Path`
- Output: `Dict[str, SkillMetadata]` via `discover_skills()`
- Access: `skill_loader.skills[name]`
- Error: Return error string (not raise) from tools

### Skill Tools -> Agent
**Owner**: builder
**Contract**:
- `load_skill(ctx, name) -> str` - Full SKILL.md body
- `read_skill_file(ctx, name, path) -> str` - Resource content
- `list_skill_files(ctx, name, dir) -> str` - File listing
- Error: All return `"Error: ..."` strings, never raise

## New Interface Template

```markdown
### [Module A] <-> [Module B]
**Owner**: [agent name]
**Contract**:
- Input: [type/shape]
- Output: [type/shape]
- Error: [error handling agreement]
**Last verified**: [date]
```
