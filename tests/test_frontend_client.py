"""Tests for the dashboard's API client against the real FastAPI app.

The app (with the same SQLite + mocked-GLM dependency overrides as the
API tests) runs on a real uvicorn server in a background thread, and the
client talks to it over actual HTTP — a true integration test.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy.orm import Session, sessionmaker

from backend.db.session import get_db
from backend.main import app
from backend.services.vision import GLMVisionClient, VisionService
from backend.services.vision.service import get_vision_service
from frontend.api_client import APIError, PalmMonitorClient
from tests.conftest import TEST_SETTINGS, GLMMock, healthy_payload, tiny_jpeg


@pytest.fixture
def client(
    engine,
    session_factory: sessionmaker[Session],
    glm_mock: GLMMock,
    uploads_before,
) -> PalmMonitorClient:
    def override_get_db():
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
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_vision_service] = override_vision

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start within 15s"

    api = PalmMonitorClient(f"http://127.0.0.1:{port}")
    yield api

    api.close()
    app.dependency_overrides.clear()


def test_register_login_me(client: PalmMonitorClient) -> None:
    client.register("dash@farm.com", "Dash#Pass123", "Dash User")
    token = client.login("dash@farm.com", "Dash#Pass123")
    assert token
    me = client.me()
    assert me["email"] == "dash@farm.com"
    assert me["role"] == "farmer"


def test_login_failure_raises_api_error(client: PalmMonitorClient) -> None:
    with pytest.raises(APIError) as excinfo:
        client.login("nobody@farm.com", "Wrong#Pass1")
    assert excinfo.value.status_code == 401


def test_palms_and_inspection_flow(client: PalmMonitorClient, glm_mock: GLMMock) -> None:
    client.register("flow@farm.com", "Flow#Pass123", "Flow User")
    client.login("flow@farm.com", "Flow#Pass123")

    palm = client.create_palm(
        "PALM-DASH-1", 24.7136, 46.6753, field_name="South", variety="Barhi"
    )
    assert palm["tree_code"] == "PALM-DASH-1"

    glm_mock.set_sequence(healthy_payload())
    report = client.inspect(
        palm["id"], tiny_jpeg(), "trunk.jpg", notes="routine check"
    )
    assert report["diagnosis"]["status"] == "healthy"
    assert report["inspection"]["image_url"].startswith("/media/")

    history = client.palm_history(palm["id"])
    assert len(history) == 1
    assert history[0]["treatment_recommendation"] is None

    image = client.get_image_bytes(report["inspection"]["image_url"])
    assert image[:2] == b"\xff\xd8"

    listing = client.list_palms()
    assert listing[0]["latest_status"] == "healthy"
    assert listing[0]["total_inspections"] == 1


def test_history_status_filter(client: PalmMonitorClient, glm_mock: GLMMock) -> None:
    from tests.conftest import infected_payload

    client.register("filter@farm.com", "Filter#Pass1", "Filter User")
    client.login("filter@farm.com", "Filter#Pass1")
    palm = client.create_palm("PALM-FILT", 1.0, 1.0)

    glm_mock.set_sequence(infected_payload(), healthy_payload())
    client.inspect(palm["id"], tiny_jpeg(), "a.jpg")
    client.inspect(palm["id"], tiny_jpeg(), "b.jpg")

    all_logs = client.palm_history(palm["id"])
    assert [log["status"] for log in all_logs] == ["healthy", "critical"]
    critical_only = client.palm_history(palm["id"], status="critical")
    assert [log["status"] for log in critical_only] == ["critical"]

    alerts = client.recent_inspections(status="critical")
    assert len(alerts) == 1


def test_duplicate_palm_conflict_surfaces_detail(client: PalmMonitorClient) -> None:
    client.register("dup@farm.com", "Dup#Pass123", "Dup User")
    client.login("dup@farm.com", "Dup#Pass123")
    client.create_palm("PALM-CONFLICT", 1.0, 1.0)
    with pytest.raises(APIError) as excinfo:
        client.create_palm("PALM-CONFLICT", 1.0, 1.0)
    assert excinfo.value.status_code == 409
    assert "already registered" in excinfo.value.detail
