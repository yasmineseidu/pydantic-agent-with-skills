# Stage 1: dependencies
FROM python:3.11-slim AS deps

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -e .

# Stage 2: application
FROM python:3.11-slim AS app

ENV PYTHONPATH=/app/src
WORKDIR /app

COPY --from=deps /usr/local /usr/local
COPY src/ src/
COPY workers/ workers/
COPY skills/ skills/
COPY alembic.ini ./
COPY pyproject.toml uv.lock ./

EXPOSE 8000
CMD ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
