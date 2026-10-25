#!/bin/sh
# Hugging Face Space entrypoint: migrations (with retry), then all services.
set -e

echo "[hf-entrypoint] applying database migrations..."
attempt=1
until alembic upgrade head; do
    if [ "$attempt" -ge 10 ]; then
        echo "[hf-entrypoint] migrations failed after $attempt attempts" >&2
        exit 1
    fi
    echo "[hf-entrypoint] database not ready (attempt $attempt), retrying in 5s..."
    attempt=$((attempt + 1))
    sleep 5
done

echo "[hf-entrypoint] starting nginx + api + dashboard on :7860"
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
