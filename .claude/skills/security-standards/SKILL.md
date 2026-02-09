---
name: security-standards
description: Security standards for the skill agent codebase. Covers secrets management, input validation, path traversal prevention, OWASP adapted for Python/Pydantic AI.
version: 1.0.0
author: Agent Team System
---

# Security Standards

Security requirements adapted for this Python/Pydantic AI skill agent codebase.

## Secrets Management

### .gitignore Coverage
Current `.gitignore` covers:
- `.env` (API keys, database URLs)
- `.venv/`, `venv/`, `env/` (virtual environments)

### Missing Coverage (ADD THESE)
- `*.key` - Private key files
- `*.pem` - Certificate files
- `*.p12` - PKCS12 files
- `*.pfx` - Windows certificate files
- `credentials.json` - Service account files
- `*.secret` - Generic secret files

### Environment Variables
- ALL secrets in `.env` file only
- Access via `Settings(BaseSettings)` - never `os.getenv()` directly
- `.env.example` must use PLACEHOLDER values, never real keys
- Current `.env.example` issue: Contains real API keys (MUST be cleaned)

### Secret Patterns to Flag
```python
# NEVER do this:
api_key = "sk-or-v1-..."  # Hardcoded secret
password = "admin123"       # Hardcoded password

# ALWAYS do this:
api_key = settings.llm_api_key  # From Pydantic Settings
```

## Input Validation

### Path Traversal Prevention
This codebase already implements path security correctly. Maintain this pattern:

```python
# REQUIRED for all file access in skills:
target_file = skill.skill_path / file_path
resolved_target = target_file.resolve()
resolved_skill = skill.skill_path.resolve()

if not resolved_target.is_relative_to(resolved_skill):
    return "Error: Access denied - file must be within skill directory"
```

### URL Validation
For `http_tools.py` HTTP requests:
- Validate URL scheme (http/https only)
- Don't follow redirects to internal networks
- Timeout all requests (current: 30s - good)
- Truncate large responses (current: 50KB - good)

### User Input in CLI
- `cli.py` handles user input via `Prompt.ask()` (Rich library)
- Input goes to LLM as prompt - no direct code execution
- Special commands (`exit`, `info`, `clear`) are safe string comparisons

## Authentication Patterns

### Current Auth Model
- LLM API keys stored in `.env` → loaded via `Settings`
- No user authentication (single-user CLI app)
- No session tokens or cookies

### API Key Security
```python
# Good pattern (from settings.py):
class Settings(BaseSettings):
    llm_api_key: str = Field(..., description="API key")
    # Pydantic Settings never logs field values by default
```

### Database Credentials
- Database URL in `.env` only
- `.env.example` must NOT contain real database URLs
- Current issue: `.env.example` contains real Neon DB URL (MUST be cleaned)

## OWASP Top 10 - Python/Pydantic AI Adaptation

### A01: Broken Access Control
- **Risk**: Low (single-user CLI app)
- **Mitigation**: Path traversal prevention in skill tools
- **Check**: `is_relative_to()` on all file paths

### A02: Cryptographic Failures
- **Risk**: Medium (API keys in transit)
- **Mitigation**: HTTPS for all LLM API calls
- **Check**: Verify `llm_base_url` uses `https://`

### A03: Injection
- **Risk**: Low (no SQL, no shell execution from user input)
- **Mitigation**: User input goes to LLM prompt only
- **Check**: No `os.system()`, `subprocess.run()`, or `eval()` with user input

### A04: Insecure Design
- **Risk**: Low
- **Mitigation**: Progressive disclosure limits what agent can access
- **Check**: Skills can only read within their own directory

### A05: Security Misconfiguration
- **Risk**: Medium
- **Mitigation**: Pydantic Settings validates all config at startup
- **Check**: `load_settings()` raises on invalid config

### A06: Vulnerable Components
- **Risk**: Medium (dependency chain)
- **Mitigation**: Pin dependencies in `pyproject.toml`
- **Check**: Regular `uv pip audit` or equivalent

### A07: Auth Failures
- **Risk**: Low (no auth system)
- **Mitigation**: N/A for MVP

### A08: Software/Data Integrity
- **Risk**: Low
- **Mitigation**: Skills loaded from local filesystem only
- **Check**: No remote skill loading in MVP

### A09: Logging Failures
- **Risk**: Low
- **Mitigation**: Structured logging on all operations
- **Check**: Never log secret values (API keys, passwords)
- **Pattern**: `logger.info(f"action: key={safe_value}")` - never log `settings.llm_api_key`

### A10: SSRF
- **Risk**: Medium (agent can make HTTP requests)
- **Mitigation**: User controls URLs through LLM interaction
- **Check**: `http_tools.py` makes requests agent decides on
- **Future**: Add URL allowlist for production

## Security Review Checklist

When reviewing code changes, check:

1. [ ] No hardcoded secrets (grep for `sk-`, `password=`, `token=`)
2. [ ] File paths validated with `resolve()` + `is_relative_to()`
3. [ ] HTTP requests use timeouts
4. [ ] No `eval()`, `exec()`, or `os.system()` with dynamic input
5. [ ] Logging doesn't include secret values
6. [ ] `.env.example` uses placeholder values only
7. [ ] New dependencies are from trusted sources
8. [ ] Error messages don't leak internal paths or stack traces to users

## Incident Response

If a security issue is found:
1. **Stop**: Don't deploy or merge
2. **Document**: Record in LEARNINGS.md under "Security Issues"
3. **Fix**: Prioritize fix above all other work
4. **Verify**: Security review of the fix
5. **Learn**: Update this skill with new check
