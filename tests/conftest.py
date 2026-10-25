"""Shared fixtures for the API test suite.

The app runs against an in-memory SQLite database (StaticPool so all
threads share one connection) and a VisionService whose GLM client rides
an httpx.MockTransport — the real HTTP/parsing stack, no network.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings
from backend.db.base import Base
from backend.db.session import get_db
from backend.main import app
from backend.services.vision import GLMVisionClient, VisionService
from backend.services.vision.local_vlm import LocalVLM
from backend.services.vision.service import get_vision_service

TEST_SETTINGS = Settings(GLM_API_KEY=SecretStr("unit-test-key"))


def infected_payload() -> dict:
    return {
        "is_healthy": False,
        "detected_disease": "Red Palm Weevil",
        "severity": "high",
        "confidence": 0.91,
        "symptoms": ["frass at leaf bases", "crown wilting"],
        "treatment_steps": ["Inject systemic insecticide into galleries."],
        "assessment": "Advanced RPW infestation visible on the trunk.",
    }


def healthy_payload(confidence: float = 0.97) -> dict:
    return {
        "is_healthy": True,
        "detected_disease": None,
        "severity": None,
        "confidence": confidence,
        "symptoms": [],
        "treatment_steps": [],
        "assessment": "Palm appears vigorous.",
    }


class UnavailableVLM(LocalVLM):
    """Deterministic provider stub: fallback disabled in tests."""

    @property
    def available(self) -> bool:
        return False


class GLMMock:
    """Scriptable GLM endpoint: serves `next` payloads; last one sticks."""

    def __init__(self) -> None:
        self.queue: list[dict] = [infected_payload()]
        self.calls = 0

    def push(self, payload: dict) -> None:
        self.queue.append(payload)

    def set_sequence(self, *payloads: dict) -> None:
        """Replace the queue: each payload is served once, last one sticks."""
        assert payloads
        self.queue = list(payloads)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        payload = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )


@pytest.fixture
def glm_mock() -> GLMMock:
    return GLMMock()


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
def uploads_before() -> set[Path]:
    """Snapshot of the uploads dir so the test can clean its files."""
    from backend.core.config import get_settings

    uploads = get_settings().UPLOAD_DIR
    uploads.mkdir(parents=True, exist_ok=True)
    return {p for p in uploads.rglob("*") if p.is_file()}


@pytest.fixture
def client(
    engine,
    session_factory,
    glm_mock: GLMMock,
    uploads_before: set[Path],
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def override_vision() -> VisionService:
        return VisionService(
            settings=TEST_SETTINGS,
            glm_client=GLMVisionClient(
                settings=TEST_SETTINGS,
                transport=httpx.MockTransport(glm_mock.handler),
                max_attempts=2,
                initial_retry_wait=0.01,
            ),
            local_predictor=None,
            local_vlm=UnavailableVLM(TEST_SETTINGS),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_vision_service] = override_vision

    from backend.core.config import get_settings

    uploads = get_settings().UPLOAD_DIR
    with TestClient(app) as test_client:  # enters lifespan (dirs, logging)
        yield test_client

    app.dependency_overrides.clear()
    # Remove files this test wrote into uploads/
    for path in uploads.rglob("*"):
        if path.is_file() and path not in uploads_before:
            path.unlink(missing_ok=True)
    for directory in sorted(
        (d for d in uploads.rglob("*") if d.is_dir()), reverse=True
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


# ----------------------------------------------------------------------
# Convenience helpers for tests
# ----------------------------------------------------------------------


def register_and_login(client: TestClient, email: str, password: str = "Farmer#Pass1") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_palm(client: TestClient, token: str, tree_code: str) -> dict:
    response = client.post(
        "/api/v1/palms",
        json={
            "tree_code": tree_code,
            "latitude": 24.7136,
            "longitude": 46.6753,
            "field_name": "North Plot",
            "variety": "Barhi",
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def tiny_jpeg() -> bytes:
    """A real 24x24 JPEG generated once (no OpenCV dependency here)."""
    import cv2
    import numpy as np

    image = np.zeros((24, 24, 3), dtype=np.uint8)
    image[:, :, 1] = 128
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()
