#!/bin/sh
# Rebuild and swap the LIVE public container (minimal downtime).
#
# Reads secrets from git-ignored files:
#   data/neon_url.txt    Neon Postgres connection string
#   data/glm_key.txt     GLM API key (optional)
#   data/secret_key.txt  stable JWT secret (created on first run)
#
# The image is built BEFORE the old container is stopped, so the actual
# downtime is only the container swap (~20-30 s).
set -e
cd "$(dirname "$0")/.."

[ -f data/neon_url.txt ] || { echo "missing data/neon_url.txt" >&2; exit 1; }
[ -f data/secret_key.txt ] || python -c "import secrets;print(secrets.token_urlsafe(64))" > data/secret_key.txt

GLM_ARG=""
if [ -s data/glm_key.txt ]; then
  GLM_ARG="-e GLM_API_KEY=$(cat data/glm_key.txt)"
fi

echo "[redeploy] building image (old container keeps serving)..."
docker build -q -t palm-hf:local -f hf-space/Dockerfile.hf . > /dev/null

echo "[redeploy] swapping container..."
docker rm -f palm-live > /dev/null 2>&1 || true

# Keyless diagnosis: local open-source VLM. Model weights are cached on a
# host volume when available (avoids re-downloading ~1 GB per container).
MODEL_MOUNT=""
MODEL_DIR="${PALM_MODEL_DIR:-/d/palm-models}"
if [ -d "$MODEL_DIR" ]; then
  MODEL_MOUNT="-v $(cygpath -w "$MODEL_DIR" 2>/dev/null || echo "$MODEL_DIR"):/app/ml/models/hf"
fi

# STREAMLIT_API_URL points at the in-container nginx loopback: the dashboard
# never depends on the public tunnel for API calls.
docker run -d --name palm-live --restart unless-stopped -p 7860:7860 \
  -e DATABASE_URL="$(cat data/neon_url.txt)" \
  -e SECRET_KEY="$(cat data/secret_key.txt)" \
  $GLM_ARG \
  -e VISION_PROVIDER=local_vlm \
  -e INFERENCE_TIMEOUT_SECONDS=180 \
  -e ENVIRONMENT=production \
  -e DEBUG=false \
  -e STREAMLIT_API_URL=http://localhost:7860 \
  $MODEL_MOUNT \
  palm-hf:local > /dev/null

echo "[redeploy] waiting for boot..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:7860/health > /dev/null 2>&1; then
    echo "[redeploy] live: container healthy after ~${i}s"
    exit 0
  fi
  sleep 1
done
echo "[redeploy] container did not become healthy in 30s — check: docker logs palm-live" >&2
exit 1
