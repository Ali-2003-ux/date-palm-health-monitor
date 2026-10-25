"""Convenience development launcher for the FastAPI backend.

Usage:
    python run_api.py                 # start the API using settings from .env

Production deployments should run uvicorn directly, e.g.:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from __future__ import annotations

import uvicorn

from backend.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    main()
