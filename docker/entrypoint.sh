#!/bin/bash
# docker/entrypoint.sh - Container entrypoint with migration automation.
set -e

echo "=== Starting Skill Agent ==="

# Run database migrations unless explicitly skipped
if [ "$SKIP_MIGRATIONS" != "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    echo "Migrations complete."
fi

# Execute the main command (uvicorn or celery)
echo "Starting application: $@"
exec "$@"
