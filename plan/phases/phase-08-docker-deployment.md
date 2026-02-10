# Phase 8: Docker + Deployment

> **Timeline**: Week 5-6 | **Prerequisites**: Phase 4 (API), Phase 6 (Background Processing) | **Status**: Not Started

## Goal

Containerized deployment to Railway/Render. Multi-stage Docker builds, local development with docker-compose, CI/CD pipeline with GitHub Actions, and deployment configurations for managed hosting platforms.

## Dependencies (Install)

```toml
# No new Python dependencies in pyproject.toml for Phase 8.
# Docker and CI/CD are infrastructure-level, not application-level.
#
# Required external tools:
#   - Docker >= 24.0
#   - docker-compose >= 2.20
#   - GitHub Actions (for CI/CD)
#   - Railway CLI or Render dashboard (for deployment)
```

## Settings Extensions

```python
# No new settings fields for Phase 8.
# Existing settings are consumed via environment variables injected by Docker/deployment:
#   - DATABASE_URL (from docker-compose or Railway/Render)
#   - REDIS_URL (from docker-compose or Railway/Render)
#   - LLM_API_KEY, EMBEDDING_API_KEY (from secrets management)
#   - All other settings from .env or platform env config
```

## New Directories & Files

```
docker/
    Dockerfile                # Multi-stage: python:3.11-slim + uv + app
    Dockerfile.worker         # Same base, celery entrypoint
    docker-compose.yml        # Local dev: api + worker + beat + postgres + redis
    docker-compose.test.yml   # CI: ephemeral test DB + Redis
    .dockerignore

deploy/
    railway/
        railway.toml          # 3 services: api (web), worker, beat
        Procfile
    render/
        render.yaml           # Blueprint: web + 2 workers + managed PG + Redis

.github/
    workflows/
        ci.yml                # CI pipeline: lint + type check + test

tests/test_docker/
    __init__.py
    test_compose.py           # docker-compose up health checks (integration)
```

## Database Tables Introduced

None. Phase 8 introduces no new database tables. All tables are from prior phases.

Reference: `plan/sql/schema.sql` (no Phase 8 section)

## Implementation Details

### 8.1 Docker Configuration

#### Dockerfile (Multi-Stage Build)

```dockerfile
# Stage 1: Dependencies
FROM python:3.11-slim AS deps
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -e .

# Stage 2: App
FROM python:3.11-slim AS app
COPY --from=deps /usr/local /usr/local
COPY src/ src/
COPY workers/ workers/
COPY skills/ skills/
COPY alembic.ini .
EXPOSE 8000
CMD ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

#### Dockerfile.worker

Same base image and dependency stage as the main Dockerfile, but with a Celery entrypoint instead of uvicorn. Used for both the worker and beat services.

### 8.2 Docker Compose (Local Development)

```yaml
services:
  api:
    build: { context: ., dockerfile: docker/Dockerfile }
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    env_file: .env

  worker:
    build: { context: ., dockerfile: docker/Dockerfile.worker }
    command: celery -A workers.celery_app worker -l info
    depends_on: [postgres, redis]

  beat:
    build: { context: ., dockerfile: docker/Dockerfile.worker }
    command: celery -A workers.celery_app beat -l info
    depends_on: [redis]

  postgres:
    image: pgvector/pgvector:pg16
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: skill_agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dev}

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

#### docker-compose.test.yml

Ephemeral variant for CI environments. Uses the same service definitions but with:
- No persistent volumes (clean state every run)
- Test-specific environment variables
- Health checks for service readiness before test execution

### 8.3 Deployment Configs

#### Railway

```
deploy/railway/
    railway.toml      # 3 services: api (web), worker, beat
    Procfile
```

Railway deployment defines three services:
- **api** (web): Runs uvicorn, exposed on port 8000
- **worker**: Runs Celery worker for background task processing
- **beat**: Runs Celery Beat for scheduled task execution

#### Render

```
deploy/render/
    render.yaml       # Blueprint: web + 2 workers + managed PG + Redis
```

Render Blueprint defines:
- **web service**: API server
- **background worker 1**: Celery worker
- **background worker 2**: Celery Beat
- **managed PostgreSQL**: With pgvector extension
- **managed Redis**: For caching and Celery broker

### 8.4 CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_PASSWORD: test }
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv pip install -e ".[dev]"
      - run: alembic upgrade head
      - run: pytest tests/ -v --tb=short
      - run: ruff check src/ tests/ workers/
      - run: mypy src/
```

Pipeline steps:
1. Checkout code
2. Set up uv (Python package manager)
3. Install all dependencies including dev extras
4. Run database migrations against test PostgreSQL
5. Run full test suite
6. Run linter against all source directories
7. Run type checker

### 8.5 .dockerignore

Standard exclusions to keep image size minimal:
- `.git/`, `.github/`
- `__pycache__/`, `*.pyc`
- `.env`, `.env.*` (secrets never baked into images)
- `tests/`, `docs/`
- `*.md` (documentation)
- `.venv/`, `venv/`
- `node_modules/` (if any)

## Tests

```
tests/test_docker/
    __init__.py
    test_compose.py       # docker-compose up health checks (integration)
```

### Key Test Scenarios

- `docker-compose up` starts all 5 services (api, worker, beat, postgres, redis)
- API health check endpoint returns 200 at `:8000/health`
- PostgreSQL accepts connections and has pgvector extension enabled
- Redis accepts connections and responds to PING
- Worker service connects to Redis broker and is ready to process tasks
- Beat service starts Celery Beat scheduler without errors
- Alembic migrations run successfully on fresh PostgreSQL
- Multi-stage Docker build produces a working image
- Final image size is under 500MB
- Environment variables from `.env` are correctly passed to containers
- Services restart correctly after failure (depends_on ordering)
- CI pipeline passes lint, type check, and test steps
- CI services (postgres, redis) are available during test execution

## Acceptance Criteria

- [ ] `docker-compose up` starts all services
- [ ] API reachable at :8000, health check passes
- [ ] Worker processes Celery tasks
- [ ] Migrations run automatically on startup
- [ ] CI pipeline passes on all branches
- [ ] Image size < 500MB

## Critical Constraint

After this phase completes:

```bash
python -m src.cli                    # CLI still works (outside Docker too)
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
docker-compose up                    # All services healthy
```

## Rollback Strategy

**Phase 8 (Docker)**: Delete `docker/` and `deploy/` directories. Delete `.github/workflows/ci.yml`. The application continues to run directly via `python -m src.cli` or `uvicorn api.app:create_app` without any Docker infrastructure.

No database changes to revert. No application code changes to revert. Phase 8 is purely additive infrastructure that wraps the existing application.

**CI/CD Rollback**: Remove `.github/workflows/ci.yml` to disable the pipeline. Existing code is unaffected.

## Links to Main Plan

- **Section 4, Phase 8**: Docker + Deployment (lines 2268-2385)
- **Section 6**: New Directory Summary (docker/, deploy/, .github/workflows/)
- **Section 13**: Implementation Sequence Diagram (Phase 8 timeline)
- **Section 21**: Phase Dependency Graph (Phase 4 + Phase 6 -> Phase 8)
- **Section 23**: Rollback Strategy (Phase 8 rollback details)
