---
name: research-patterns
description: Research methodology for Python/Pydantic AI ecosystem. Covers source evaluation, search strategies, output format for research agents.
version: 1.0.0
author: Agent Team System
---

# Research Patterns

Methodology for research agents working in this Python/Pydantic AI codebase.

## Search Strategy

### Codebase Search (Always First)

Before external research, search the existing codebase:

```
1. Glob "**/*.py" for file discovery
2. Grep "pattern" src/ for implementation patterns
3. Read specific files for full context
4. Grep "pattern" tests/ for test patterns
5. Read .claude/PRD.md for requirements context
```

### Python Ecosystem Search

For Python packages and patterns:

| Source | Use For | Trust Level |
|--------|---------|-------------|
| PyPI (pypi.org) | Package discovery, versions | High |
| Pydantic AI docs (ai.pydantic.dev) | Framework patterns | High |
| Pydantic docs (docs.pydantic.dev) | Validation patterns | High |
| Python docs (docs.python.org) | Stdlib reference | High |
| GitHub issues/discussions | Bug workarounds | Medium |
| Stack Overflow | Common patterns | Medium |
| Blog posts | Tutorials, opinions | Low-Medium |
| LLM training data | General knowledge | Verify first |

### Pydantic AI Specific Research

Key documentation sources for this project:
- **Agent definition**: `ai.pydantic.dev/agents/`
- **Dependencies**: `ai.pydantic.dev/dependencies/`
- **Tools**: `ai.pydantic.dev/tools/`
- **Toolsets**: `ai.pydantic.dev/toolsets/`
- **Models/Providers**: `ai.pydantic.dev/models/`
- **Testing**: `ai.pydantic.dev/testing/`

### Package Evaluation Criteria

Before recommending a package:

1. **Maintenance**: Last commit within 6 months?
2. **Downloads**: >1000/week on PyPI?
3. **Dependencies**: Minimal dependency chain?
4. **Type support**: Has type stubs or inline types?
5. **License**: Compatible with project (check pyproject.toml)?
6. **Size**: Reasonable for what it does?
7. **Python version**: Supports 3.11+?

## Output Format

Research results MUST use this structure:

```markdown
## Research: [Topic]

**Query**: [What was researched]
**Date**: [When research was done]
**Confidence**: [High|Medium|Low]

### Findings

#### Option 1: [Name]
- **Source**: [URL or file path]
- **Relevance**: [How it applies to this project]
- **Pros**: [Benefits]
- **Cons**: [Drawbacks]
- **Compatibility**: [Works with our stack?]

#### Option 2: [Name]
- ...

### Recommendation

[Which option and why]

### Sources Consulted
1. [Source 1 with URL]
2. [Source 2 with URL]

### Codebase Context
- Related existing code: [file paths]
- Existing patterns to maintain: [patterns]
- Integration points: [where this connects]
```

## Source Evaluation

### Trust Hierarchy
```
Official docs > GitHub source > Published packages > Community posts > LLM knowledge
```

### Verification Steps
1. Check if information matches current Pydantic AI version (>=0.0.30)
2. Verify code examples actually run
3. Cross-reference with project's existing patterns
4. Check for breaking changes between versions
5. Validate against `pyproject.toml` dependency constraints

### Red Flags
- Blog post from >12 months ago (Pydantic AI changes fast)
- Examples using deprecated API patterns
- No version specified in recommendations
- Suggestions that contradict project's CLAUDE.md principles

## Research Types

### 1. Pattern Research
**Goal**: Find how to implement something matching existing patterns
**Method**: Search codebase first → check Pydantic AI docs → check examples/

### 2. Package Research
**Goal**: Find best package for a need
**Method**: PyPI search → GitHub comparison → compatibility check

### 3. Bug Research
**Goal**: Find solution to an error
**Method**: Read error message → search codebase for similar patterns → GitHub issues → Stack Overflow

### 4. Architecture Research
**Goal**: Evaluate design approach
**Method**: Read existing architecture → check Pydantic AI best practices → compare alternatives

## MCP Tool Usage

When using Claude Code tools for research:

- **WebSearch**: Use for current documentation, package discovery
- **WebFetch**: Use to read specific documentation pages
- **Grep**: Search codebase for existing implementations
- **Glob**: Find files by pattern
- **Read**: Read full file contents
- **Bash**: Check package versions (`uv pip list`), run quick validations

## Deliverables

Research agent must produce:
1. **Structured findings** in the output format above
2. **Actionable recommendation** with clear next steps
3. **Codebase context** showing how findings relate to existing code
4. **Risk assessment** of recommended approach
5. **LEARNINGS.md update** if research reveals important patterns
