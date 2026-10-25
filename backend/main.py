"""
FastAPI application entry point.

Mounts the /api/v1 routers (auth, palms, inspections), the /media static
files for stored inspection photos, and system endpoints. Configuration
comes from .env via backend.core.config; schema is managed by Alembic.

Run locally (development):
    python run_api.py
or directly:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.api.errors import register_exception_handlers
from backend.api.v1.router import api_router
from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.db.session import dispose_engine

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    settings.ensure_dirs()

    if settings.VISION_PROVIDER == "glm" and settings.GLM_API_KEY is None:
        logger.warning(
            "VISION_PROVIDER is 'glm' but GLM_API_KEY is not set; "
            "inference requests will fail until a key is configured in .env"
        )

    logger.info(
        "Starting %s v%s (environment=%s, inference=%s)",
        settings.APP_NAME,
        __version__,
        settings.ENVIRONMENT,
        settings.VISION_PROVIDER,
    )
    yield
    dispose_engine()
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    """Application factory — keeps the app importable and testable."""
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=__version__,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "Authentication", "description": "Register, login, profile"},
            {"name": "Palm Trees", "description": "GPS-tagged palm registry and history"},
            {"name": "Inspections", "description": "AI palm-health analysis"},
            {"name": "System", "description": "Health probes"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # Stored inspection photos; check_dir=False — lifespan creates the dir.
    app.mount(
        "/media",
        StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False),
        name="media",
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["System"], summary="Service health probe")
    async def health() -> dict[str, str]:
        """Lightweight liveness probe for load balancers and the dashboard."""
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": __version__,
            "environment": settings.ENVIRONMENT,
            "inference_provider": settings.VISION_PROVIDER,
        }

    return app


app = create_app()
