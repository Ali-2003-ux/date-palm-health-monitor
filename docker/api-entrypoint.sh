#!/bin/sh
# API container entrypoint: run migrations, then serve.
# Retries migrations briefly so the container survives slow database starts.
set -e

echo "[entrypoint] applying database migrations..."
attempt=1
until alembic upgrade head; do
    if [ "$attempt" -ge 5 ]; then
        echo "[entrypoint] migrations failed after $attempt attempts" >&2
        exit 1
    fi
    echo "[entrypoint] database not ready (attempt $attempt), retrying in 3s..."
    attempt=$((attempt + 1))
    sleep 3
done

echo "[entrypoint] starting API on port ${PORT:-8000} with ${WORKERS:-2} workers"
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-2}"
