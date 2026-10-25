# =====================================================================
# Date Palm Health Monitoring System — production image.
#
# One image, two roles (selected by the start command):
#   API:       docker/api-entrypoint.sh   (migrations + uvicorn)
#   Dashboard: streamlit run frontend/app.py ...
#
# Build:  docker build -t palm-monitor .
# Run:    docker run -p 8000:8000 palm-monitor
# Stack:  docker compose up -d   (api + dashboard + postgres)
# =====================================================================

# ------------------------- build stage -------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --upgrade pip \
    && /app/.venv/bin/pip install -r requirements.txt

# ------------------------- runtime stage -----------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root runtime user; /app/uploads is the image-storage volume target.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

# NOTE: COPY flattens directory sources into the destination, so each
# directory needs its own explicit target (COPY backend/ /app/ would put
# main.py at /app/main.py instead of /app/backend/main.py).
COPY --chown=appuser:appuser alembic.ini /app/
COPY --chown=appuser:appuser backend/ /app/backend/
COPY --chown=appuser:appuser frontend/ /app/frontend/
COPY --chown=appuser:appuser migrations/ /app/migrations/
COPY --chown=appuser:appuser ml/ /app/ml/
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser docker/ /app/docker/

# Windows build contexts may not carry the Unix exec bit — make it explicit.
RUN chmod +x /app/docker/api-entrypoint.sh

USER appuser

# API by default; docker-compose / render override the command for the
# dashboard service.
EXPOSE 8000 8501
CMD ["docker/api-entrypoint.sh"]
