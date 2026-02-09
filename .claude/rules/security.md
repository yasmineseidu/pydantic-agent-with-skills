---
paths: ["src/**/*.py"]
---

# Security Standards

For full OWASP-adapted security details, see `.claude/skills/security-standards/`.

## Path Traversal Prevention

REQUIRED for all file access in skills:

```python
target_file = skill.skill_path / file_path
if not target_file.resolve().is_relative_to(skill.skill_path.resolve()):
    return "Error: Access denied - file must be within skill directory"
```

## Secrets Management

- ALL secrets in `.env` only -- access via `Settings(BaseSettings)`
- Never `os.getenv()` directly
- Never hardcode secrets: `api_key = "sk-..."` is FORBIDDEN
- Never log secret values (API keys, passwords, tokens)

## Input Validation

- Validate URL scheme (http/https only) for HTTP tools
- Timeout all requests (30s default)
- Truncate large responses (50KB default)
- No `eval()`, `exec()`, or `os.system()` with dynamic input

## Security Review Checklist

1. No hardcoded secrets (grep for `sk-`, `password=`, `token=`)
2. File paths validated with `resolve()` + `is_relative_to()`
3. HTTP requests use timeouts
4. No `eval()`, `exec()`, or `os.system()` with dynamic input
5. Logging doesn't include secret values
6. `.env.example` uses placeholder values only
7. Error messages don't leak internal paths or stack traces
