# 🚀 Production Deployment Guide

This document packages everything needed to run the Date Palm Health
Monitoring System in the cloud: a multi-stage Docker image (one image,
two services), a full docker-compose stack with PostgreSQL, a Heroku-style
`Procfile`, and a Render blueprint (`render.yaml`).

---

## 1. Required environment variables

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | ✅ | `python -c "import secrets; print(secrets.token_urlsafe(64))"` — production mode **refuses to boot** without a real one |
| `DATABASE_URL` | ✅ | `postgresql+psycopg2://user:pass@host:5432/palm_monitor` (managed Postgres: add `?sslmode=require` if the provider needs TLS) |
| `POSTGRES_PASSWORD` | ✅ (compose) | Used by the bundled Postgres container |
| `GLM_API_KEY` | optional | z.ai **open-platform** key with GLM-4V access — enables real AI diagnosis; without it inspections return 503 |
| `CORS_ORIGINS` | ✅ | JSON list of public dashboard URLs: `["https://palm-dashboard.onrender.com"]` |
| `ENVIRONMENT` / `DEBUG` | ✅ | `production` / `false` (enables fail-fast safety checks) |
| `STREAMLIT_API_URL` | dashboard | Public URL of the API service, e.g. `https://palm-api.onrender.com` |

**Two persistence rules:** the database must be a managed/volume-backed
PostgreSQL, and `uploads/` (inspection photos) must be on a persistent
disk — containers with ephemeral filesystems will silently lose photos
otherwise.

---

## 2. Option A — Render (recommended, easiest)

1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → pick the repo. Render reads
   `render.yaml` (api + dashboard + PostgreSQL, 5 GB uploads disk).
3. Fill in the prompted secrets (`SECRET_KEY`, `POSTGRES_PASSWORD`,
   `GLM_API_KEY`).
4. After the database is created, copy its **internal** connection string
   into `DATABASE_URL` as `postgresql+psycopg2://…`, and set
   `CORS_ORIGINS` to the dashboard's public URL.
5. First deploy runs migrations automatically (`api-entrypoint.sh`).
6. Create the admin: API service → **Shell** →
   `python scripts/create_admin.py you@farm.com "Strong#Pass1" "Admin"`

---

## 3. Option B — Any VPS with Docker (full control)

```bash
# on the server
git clone <your-repo> && cd date-palm-monitor

export SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(64))")
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export GLM_API_KEY="your-zai-open-platform-key"
export CORS_ORIGINS='["https://dashboard.yourdomain.com"]'

docker compose up -d --build      # postgres + api + dashboard

docker compose exec api python scripts/create_admin.py \
    you@farm.com "Strong#Pass1" "Admin"
```

Put a reverse proxy (Caddy/Traefik/nginx) in front for TLS:
`api.yourdomain.com → :8000`, `dashboard.yourdomain.com → :8501`.
Migrations run automatically on every `api` container start.

To test the exact production stack locally first:
`SECRET_KEY=... POSTGRES_PASSWORD=... docker compose up --build`.

---

## 4. Option C — Heroku (Procfile)

Each Heroku app routes one `web` dyno, so deploy **two apps**:

**API app** (this repo, this `Procfile`):
```bash
heroku create palm-api
heroku config:set ENVIRONMENT=production DEBUG=false SECRET_KEY=... \
    GLM_API_KEY=... CORS_ORIGINS='["https://palm-dashboard-xxx.herokuapp.com"]'
heroku addons:create heroku-postgresql:essential-0
# heroku provides DATABASE_URL in postgres:// form; convert the scheme:
heroku config:set DATABASE_URL="$(heroku config:get DATABASE_URL | sed 's|^postgres://|postgresql+psycopg2://|')"
git push heroku main        # release phase runs: alembic upgrade head
```

**Dashboard app** (same repo, change the Procfile `web:` line to the
streamlit command from the `dashboard:` line):
```bash
heroku create palm-dashboard
heroku config:set STREAMLIT_API_URL=https://palm-api-xxx.herokuapp.com
git push heroku main
```
⚠️ Heroku's filesystem is ephemeral — attach a persistent store for
`uploads/` or extend storage to S3 before relying on photo history.

Railway/Fly work the same way: two services from one repo, using the
start commands in the `Procfile`.

---

## 4.5 Option D — Hugging Face Spaces (free, no credit card)

Single container, single public URL: nginx on :7860 routes `/api/*`,
`/media/*`, `/docs` to FastAPI and everything else (incl. Streamlit
websockets) to the dashboard; supervisord manages all processes. Uses a
free external Postgres (e.g. [Neon](https://neon.tech)) —
`hf-space/` holds the configs, verified to run in ~165 MB of RAM.

```bash
pip install huggingface_hub

# one-time credentials (kept out of chat/git via files):
#   data/hf_token.txt   <- WRITE token from huggingface.co/settings/tokens
#   data/neon_url.txt   <- postgres://... connection string from neon.tech
python scripts/deploy_hf.py \
    --username YOUR_HF_NAME \
    --token-file data/hf_token.txt \
    --database-url-file data/neon_url.txt \
    --glm-api-key-file data/glm_key.txt      # optional
```

Public URL: `https://<username>-date-palm-health-monitor.hf.space`
(build ~5–10 min). Free-tier caveats: the Space sleeps after 48 h of
inactivity (ping `/health` on a schedule to keep it warm), and the
filesystem is ephemeral — inspection photos are lost on rebuild unless
you attach persistent storage or extend storage to S3.

Seed the admin against the external database from your machine:
```bash
DATABASE_URL="$(cat data/neon_url.txt)" python scripts/create_admin.py \
    you@farm.com "Strong#Pass1" "Admin"
```

---

## 5. Post-deploy checklist

- [ ] `GET https://<api>/health` returns `{"status": "ok", "environment": "production"}`
- [ ] Admin account created (`scripts/create_admin.py`) and login works
- [ ] Dashboard loads, tree registration works (proves DB + CORS)
- [ ] `POST /api/v1/inspect` with a photo returns a diagnosis (proves the
      GLM key; a 503 means the key is missing/invalid)
- [ ] Uploaded photos still exist after a redeploy (volume mounted)
- [ ] `docker compose logs api` / platform logs are error-free

## 6. Operations notes

- **Scaling the API:** `WORKERS` env (default 2) or platform replicas.
  Migrations run per container start; Alembic stamps idempotently.
- **Schema changes:** edit models → `alembic revision --autogenerate -m "…"`
  → commit → deploy; the entrypoint applies it automatically.
- **Rotating the GLM key / SECRET_KEY:** update the platform env var and
  restart. Rotating `SECRET_KEY` invalidates all issued JWTs (users just
  sign in again).
- **Backups:** database snapshots via your provider; `uploads/` volume
  snapshots or rsync the volume.

---

## 7. Option E — Streamlit Community Cloud (100% free, no card, 24/7)

Single-process deployment: the Streamlit app runs the ENTIRE system
in-process (auth, Neon Postgres, Gemini diagnosis) — no backend server.

1. Go to **https://share.streamlit.io** → sign in with GitHub.
2. **New app** → repo `Ali-2003-ux/date-palm-health-monitor`, branch
   `main`, main file path **`frontend/app.py`** → Deploy.
3. App **Settings → Secrets** → paste (template: `data/streamlit_secrets.example.toml`):
   ```toml
   PALM_CLOUD = "1"
   DATABASE_URL = "<your Neon connection string>"
   GLM_API_KEY = "<your Gemini API key>"
   SECRET_KEY = "<long random string>"
   ```
4. Save — the app restarts into cloud mode. URL: `https://<app-name>.streamlit.app`

Verified locally in `PALM_CLOUD=1` mode against Neon + Gemini: login,
palms, real-photo diagnosis (cause/symptoms/treatment/prevention),
history with embedded photos. Notes: inspection photos are stored
base64-embedded (≤1024 px) in Neon because cloud filesystems are
ephemeral; the SmolVLM fallback is disabled in cloud mode (1 GB RAM) —
if Gemini quota is exhausted the UI shows a friendly retry message.
