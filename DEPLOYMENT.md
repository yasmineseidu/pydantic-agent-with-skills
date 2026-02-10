# Deployment Guide

This guide covers local development with Docker, environment configuration, and deployment to Railway and Render.

## Prerequisites

- Docker >= 24.0
- Docker Compose >= 2.20
- Git

## 1. Local Development with Docker

### Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd pydantic-agent-with-skills

# 2. Create .env file from example
cp .env.example .env
# Edit .env with your actual values (see Environment Variables below)

# 3. Start all services
docker compose -f docker/docker-compose.yml up -d

# 4. Verify services are running
docker compose -f docker/docker-compose.yml ps

# 5. Check API health
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.1.0","services":null}

# 6. Check readiness (includes DB + Redis status)
curl http://localhost:8000/ready
# Expected: {"status":"ok","version":"0.1.0","services":{"database":{"status":"connected",...}}}

# 7. Access API documentation
open http://localhost:8000/docs
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8000 | FastAPI application server |
| worker | - | Celery background task worker |
| beat | - | Celery Beat periodic task scheduler |
| postgres | 5432 | PostgreSQL with pgvector extension |
| redis | 6379 | Redis for caching and Celery broker |

### Stopping Services

```bash
# Stop all services
docker compose -f docker/docker-compose.yml down

# Stop and remove volumes (fresh database)
docker compose -f docker/docker-compose.yml down -v
```

### Rebuilding After Code Changes

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

### Database Migrations

Migrations run automatically on container startup via `docker/entrypoint.sh`. To skip automatic migrations:

```bash
SKIP_MIGRATIONS=true docker compose -f docker/docker-compose.yml up -d
```

To run migrations manually:

```bash
docker compose -f docker/docker-compose.yml exec api alembic upgrade head
docker compose -f docker/docker-compose.yml exec api alembic current
```

## 2. Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for LLM provider | `sk-or-v1-...` |

### LLM Provider Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openrouter` | Provider: `openrouter`, `openai`, or `ollama` |
| `LLM_MODEL` | `anthropic/claude-sonnet-4.5` | Model identifier |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | Provider API URL |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | None | PostgreSQL URL: `postgresql+asyncpg://user:pass@host:5432/db` |
| `DATABASE_POOL_SIZE` | `5` | Connection pool size |
| `DATABASE_POOL_OVERFLOW` | `10` | Max overflow connections |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | None | Redis URL: `redis://host:6379/0` |
| `REDIS_KEY_PREFIX` | `ska:` | Key namespace prefix |

### Authentication (Phase 4)

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | None | Secret for JWT token signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `ADMIN_EMAIL` | None | Bootstrap admin email |
| `ADMIN_PASSWORD` | None | Bootstrap admin password |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |

### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_API_KEY` | None | OpenAI API key for embeddings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `1536` | Embedding vector size |

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `SKILLS_DIR` | `skills` | Path to skills directory |
| `APP_ENV` | `development` | Environment name |
| `LOG_LEVEL` | `INFO` | Logging level |

### Docker-Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_MIGRATIONS` | unset | Set to `true` to skip auto-migrations |
| `POSTGRES_PASSWORD` | `dev` | PostgreSQL password (docker-compose) |

## 3. Deploy to Railway

### Prerequisites

- Railway account (https://railway.app)
- Railway CLI: `npm i -g @railway/cli`

### Steps

```bash
# 1. Login to Railway
railway login

# 2. Create a new project
railway init

# 3. Add PostgreSQL plugin
railway add --plugin postgresql

# 4. Add Redis plugin
railway add --plugin redis

# 5. Set environment variables
railway variables set LLM_API_KEY=sk-or-v1-your-key
railway variables set JWT_SECRET_KEY=your-secret-key
railway variables set ADMIN_EMAIL=admin@example.com
railway variables set ADMIN_PASSWORD=secure-password
# DATABASE_URL and REDIS_URL are auto-set by Railway plugins

# 6. Deploy
railway up

# 7. Verify
railway logs
```

### Railway Configuration

The `deploy/railway/railway.toml` defines three services:
- **api**: uvicorn web server on port 8000
- **worker**: Celery background task worker
- **beat**: Celery Beat scheduler

### Health Check

Railway monitors `GET /health` automatically. The `/ready` endpoint provides detailed dependency status.

## 4. Deploy to Render

### Prerequisites

- Render account (https://render.com)
- GitHub repository connected to Render

### Steps

1. Log in to Render Dashboard
2. Click "New" then "Blueprint"
3. Connect your GitHub repository
4. Select `deploy/render/render.yaml` as the Blueprint file
5. Configure environment variables:
   - `LLM_API_KEY`
   - `JWT_SECRET_KEY`
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD`
   - `DATABASE_URL` (auto-set by Render managed PostgreSQL)
   - `REDIS_URL` (auto-set by Render managed Redis)
6. Click "Apply"

### Render Blueprint Services

The `deploy/render/render.yaml` defines:
- **skill-agent-api**: Web service (Docker)
- **skill-agent-worker**: Celery worker (Docker)
- **skill-agent-beat**: Celery Beat (Docker)
- **skill-agent-redis**: Managed Redis
- **skill-agent-postgres**: Managed PostgreSQL

## 5. Troubleshooting

### "Connection refused" on localhost:8000

The API service may still be starting. Check service status and logs:

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs api
```

Ensure postgres and redis are healthy before the API starts (health checks handle this automatically).

### "Migration failed" on startup

Verify `DATABASE_URL` is correctly formatted:

```
postgresql+asyncpg://user:password@host:5432/database_name
```

Check the migration log:

```bash
docker compose -f docker/docker-compose.yml logs api | grep -i migration
```

To run migrations manually:

```bash
docker compose -f docker/docker-compose.yml exec api alembic upgrade head
```

### "Worker not processing tasks"

Check Celery worker logs:

```bash
docker compose -f docker/docker-compose.yml logs worker
```

Verify Redis connectivity:

```bash
docker compose -f docker/docker-compose.yml exec redis redis-cli ping
# Expected: PONG
```

Verify `CELERY_BROKER_URL` or `REDIS_URL` is set in your `.env` file.

### Health check returns unhealthy

```bash
# Check liveness
curl http://localhost:8000/health

# Check readiness (includes DB/Redis status)
curl http://localhost:8000/ready
```

If `/ready` returns 503, the database is unreachable. Check postgres logs:

```bash
docker compose -f docker/docker-compose.yml logs postgres
```

### Image size too large

The target is < 500MB per image. If images are larger:

```bash
docker images | grep skill-agent
```

Ensure `.dockerignore` excludes `tests/`, `docs/`, `*.md`, `.claude/`, `plan/`, `reports/`, `examples/`.

### Resetting everything

```bash
# Stop services, remove volumes, remove images
docker compose -f docker/docker-compose.yml down -v --rmi local
```
