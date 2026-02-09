---
paths: ["**"]
---

# Mandatory Practices (NON-NEGOTIABLE)

These 6 practices are enforced at 3 layers: this rule, per-agent instructions, and `.claude/skills/coding-conventions/`.

## 1. Grep Local Codebase FIRST

Before writing ANY code, grep THIS project to study existing patterns.

```
Grep "from src." src/
Grep "{pattern}" src/
```

Read the target file. Never assume -- verify by reading actual files.

## 2. Grep MCP

AFTER grepping local, use `grep_query` (grep-mcp server) to search GitHub for battle-tested code.

```
grep_query: query="{pattern}", language="python"
```

See `.claude/skills/coding-conventions/` for full grep-mcp workflow.

## 3. LSP After Every Edit

- `getDiagnostics` after EVERY edit
- `goToDefinition` before modifying
- `findReferences` before renaming

## 4. Plan Before Execute

Outline plan BEFORE non-trivial changes. List: files to read, searches, changes per file, verification.

## 5. Learn From Mistakes

Read `LEARNINGS.md` at start. Write concise learnings at end.
Format: `MISTAKE: X -> Y` | `PATTERN: X -> Y` | `GOTCHA: X -> Y` (1 line, max 120 chars).

## 6. Task Management

ALL work tracked via TaskUpdate. `in_progress` when starting, `completed` only after tests pass + lint clean. Never mark complete with failing tests.

## Additional Required Practices

7. **Read before write**: Always read existing files before modifying
8. **Match patterns**: Follow existing codebase conventions exactly
9. **Type everything**: Full type annotations, no exceptions
10. **Google docstrings**: Args/Returns/Raises on all public functions
11. **Structured logging**: `f"action_name: key={value}"` format
12. **Test after change**: Run `pytest tests/ -v` after any code change
13. **Lint after change**: Run `ruff check src/ tests/` after any code change
14. **Respect ownership**: Only modify files you own (see team-coordination skill)
