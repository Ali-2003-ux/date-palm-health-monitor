# =====================================================================
# Hugging Face Spaces image — the ENTIRE stack in ONE container:
#
#   nginx :7860  (public door, HF app_port)
#     ├─ /api/* /media/* /docs /redoc /openapi.json /health → uvicorn :8000
#     └─ everything else (/, /_stcore/* websockets)           → streamlit :8501
#   supervisord manages nginx + uvicorn + streamlit
#
# External requirements (set as HF Space Secrets):
#   DATABASE_URL      e.g. postgres://user:pass@ep-xxx.neon.tech/db?sslmode=require
#   SECRET_KEY        long random string
#   STREAMLIT_API_URL the Space's own public URL (same-origin proxying)
#   GLM_API_KEY       optional — enables real AI diagnosis
# =====================================================================

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx-light supervisor ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# HF Spaces run containers as UID 1000
RUN useradd --create-home --uid 1000 user

WORKDIR /app

COPY requirements.txt requirements-vlm.txt ./
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /app/.venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch \
    && /app/.venv/bin/pip install --no-cache-dir -r requirements-vlm.txt

COPY --chown=user:user alembic.ini ./
COPY --chown=user:user backend/ backend/
COPY --chown=user:user frontend/ frontend/
COPY --chown=user:user migrations/ migrations/
COPY --chown=user:user ml/ ml/
COPY --chown=user:user scripts/ scripts/
COPY --chown=user:user hf-space/nginx.conf /etc/nginx/nginx.conf
COPY --chown=user:user hf-space/supervisord.conf /etc/supervisor/conf.d/app.conf
COPY --chown=user:user hf-space/hf-entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/uploads /app/ml/models/hf /run /var/log/supervisor /var/lib/nginx \
    && chown -R user:user /app /run /var/log/supervisor /var/lib/nginx

USER user
EXPOSE 7860
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
