# 🌴 Date Palm Health Monitoring System

AI-powered platform for monitoring date palm health, detecting diseases
(**Red Palm Weevil**, **fungal infections**, nutrient deficiencies) and
delivering agricultural analytics to farmers and agronomists.

## Architecture Overview

```
┌──────────────────────────┐        ┌─────────────────────────────────────┐
│  Streamlit Dashboard     │  HTTP  │  FastAPI Backend (/api/v1)          │
│  (frontend/app.py)       │◄──────►│  ┌───────────────────────────────┐  │
│  • image upload / camera │        │  │ api/v1     REST routers       │  │
│  • farm health stats     │        │  │ services   vision inference   │  │
│  • GPS map + alerts      │        │  │ schemas    pydantic I/O       │  │
│  • diagnosis reports     │        │  │ models     SQLAlchemy ORM     │  │
└──────────────────────────┘        │  │ db         engine + sessions  │  │
                                    │  └───────────────────────────────┘  │
                                    └───────────────┬─────────────────────┘
                                                    │
                    ┌───────────────────────────────┼──────────────────────┐
                    ▼                               ▼                      ▼
        ┌───────────────────────┐      ┌────────────────────┐   ┌──────────────────┐
        │ PostgreSQL            │      │ Inference backends │   │ Image storage    │
        │ users / palms / logs  │      │ • GLM-4V API (httpx)│  │ uploads/ (local) │
        └───────────────────────┘      │ • local CNN (torch) │   └──────────────────┘
                                       └────────────────────┘
```

## Tech Stack

| Layer          | Technology                                                        |
| -------------- | ----------------------------------------------------------------- |
| API            | FastAPI, Uvicorn, Pydantic v2, pydantic-settings                  |
| Database       | PostgreSQL 15+, SQLAlchemy 2.x, Alembic migrations                |
| Auth           | JWT (PyJWT) + bcrypt password hashing, role-based (Farmer/Agronomist/Admin) |
| Computer Vision| OpenCV + Pillow preprocessing; GLM-4V vision API or local PyTorch CNN (MobileNetV2/ResNet) |
| Dashboard      | Streamlit, Folium maps, Plotly analytics                          |
| Testing        | pytest + FastAPI TestClient, ruff linting                         |

## Project Structure

```
date-palm-monitor/
├── requirements.txt          # pinned production dependencies
├── .env.example              # template for all environment variables
├── run_api.py                # development launcher for the API
├── run_dashboard.py          # development launcher for the dashboard
├── Dockerfile                # production image (API + dashboard)
├── docker-compose.yml        # full stack: postgres + api + dashboard
├── render.yaml               # Render.com blueprint
├── Procfile                  # Heroku/Railway/Fly process definitions
├── DEPLOYMENT.md             # production deployment guide
├── alembic.ini               # Alembic config (DB URL comes from .env)
├── migrations/               # Alembic: env.py + versioned migrations
├── docker/
│   └── api-entrypoint.sh     # container start: migrations + uvicorn
├── backend/
│   ├── main.py               # FastAPI app factory + /health (Steps 1, 4)
│   ├── core/
│   │   ├── config.py         # validated Settings from .env (pydantic-settings)
│   │   └── logging.py        # console + rotating-file logging
│   ├── db/                   # engine, session factory, init (Step 2)
│   ├── models/               # ORM: User, PalmTree, InspectionLog (Step 2)
│   ├── schemas/              # Pydantic request/response models (Step 4)
│   ├── api/v1/               # REST endpoints (Step 4)
│   ├── services/vision/      # Step 3: preprocessing, GLM-4V client, local CNN, knowledge base
│   └── utils/                # shared helpers
├── ml/
│   └── models/               # trained CNN weights (.pt/.keras, git-ignored)
├── frontend/
│   ├── app.py                # Streamlit dashboard (Step 5)
│   └── api_client.py         # typed HTTP client for the backend API
├── scripts/
│   └── check_env.py          # environment & configuration verification
├── tests/                    # pytest suite (smoke tests included)
└── uploads/                  # uploaded palm images (git-ignored, runtime)
```

## Quick Start

**Prerequisites:** Python 3.10 – 3.12 (64-bit), PostgreSQL 15+.

```bash
cd date-palm-monitor

# 1. Create and activate a virtual environment (Windows Git Bash)
python -m venv .venv
source .venv/Scripts/activate        # PowerShell: .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure the environment
cp .env.example .env                 # then edit .env (DB credentials, GLM_API_KEY)

# 4. Verify the environment
python scripts/check_env.py

# 5. Create the database schema (requires PostgreSQL running, configured in .env)
alembic upgrade head

# 6. Run the API
python run_api.py                    # Swagger UI: http://localhost:8000/docs

# 7. Run the dashboard (in a second terminal)
python run_dashboard.py              # UI: http://localhost:8501

# 8. Create an admin/agronomist account (after configuring the DB)
python scripts/create_admin.py admin@farm.com "Strong#Pass123" "Site Admin"

# 9. Run the test suite
pytest -v
```

## Production deployment

The repo ships a complete cloud-deployment package — see **[DEPLOYMENT.md](DEPLOYMENT.md)**
for the full guide:

- **`Dockerfile`** — multi-stage production image (non-root, one image for both services)
- **`docker-compose.yml`** — full stack: PostgreSQL + API (auto-migrations) + dashboard
- **`render.yaml`** — one-blueprint deploy on Render (api + dashboard + managed Postgres)
- **`Procfile`** — Heroku/Railway/Fly process definitions

```bash
SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(64))") \
POSTGRES_PASSWORD=change-me docker compose up -d --build
```

## Database migrations

Schema migrations use **Alembic**; the target database is read from `.env`
(the same `Settings` the app uses), so the CLI and the API never drift apart:

```bash
alembic upgrade head                                   # apply all migrations
alembic downgrade -1                                   # revert the last migration
alembic revision --autogenerate -m "describe change"   # new migration from model edits
DATABASE_URL=... alembic upgrade head --sql            # offline SQL (no server needed)
```

### Configuration notes

- All settings are read from `.env` (see `.env.example`) and validated at
  startup by `backend/core/config.py` — invalid values fail fast with a
  clear message. `ENVIRONMENT=production` additionally refuses the default
  `SECRET_KEY` and refuses `DEBUG=true`.
- **Inference provider**: `VISION_PROVIDER=glm` uses the GLM-4V
  vision-language API (set `GLM_API_KEY`); `VISION_PROVIDER=local_cnn`
  runs a locally trained MobileNetV2/ResNet — enable the optional
  `torch`/`torchvision` block in `requirements.txt` and place weights in
  `ml/models/`.
- Uploaded images are stored under `uploads/` (git-ignored).

## Implementation Roadmap

- [x] **Step 1** — Project architecture, environment & configuration (this scaffold)
- [x] **Step 2** — Database schema & SQLAlchemy models + Alembic migrations (User, PalmTree, InspectionLog)
- [x] **Step 3** — CV & AI inference (`backend/services/vision/`): OpenCV preprocessing, GLM-4V client with retries, local CNN fallback, disease knowledge base
- [x] **Step 4** — FastAPI endpoints: `POST /api/v1/inspect`, `POST /api/v1/palms`, `GET /api/v1/palms/{id}/history`, auth (JWT, roles), `/media` image serving
- [x] **Step 5** — Streamlit dashboard: login, image upload + live camera, farm health stats, GPS map, diagnosis reports, alerts
