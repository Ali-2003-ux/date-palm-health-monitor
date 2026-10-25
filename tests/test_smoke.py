"""Smoke tests: verify configuration loads and the API skeleton boots."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.core.config import Settings, get_settings


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.APP_NAME
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.VISION_PROVIDER in {"glm", "local_cnn"}


def test_database_url_composition() -> None:
    # Fresh instance (no .env interference) verifies URL composition from parts.
    settings = Settings(
        POSTGRES_USER="u", POSTGRES_PASSWORD="p@ss", POSTGRES_HOST="db",
        POSTGRES_PORT=5432, POSTGRES_DB="palm", DATABASE_URL=None,
    )
    url = settings.database_url
    assert url == "postgresql+psycopg2://u:p%40ss@db:5432/palm"


def test_database_url_platform_shim() -> None:
    # Managed platforms inject postgres:// URLs; SQLAlchemy needs the driver form.
    settings = Settings(DATABASE_URL="postgres://u:p@host:5432/db")
    assert settings.database_url == "postgresql+psycopg2://u:p@host:5432/db"


def test_health_endpoint() -> None:
    from backend.main import app

    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["inference_provider"] in {"glm", "local_cnn"}
