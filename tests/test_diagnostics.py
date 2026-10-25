"""Tests for vision-provider diagnostics and auth-error surfacing."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_SETTINGS,
    auth,
    create_palm,
    healthy_payload,
    register_and_login,
    tiny_jpeg,
)


def glm_handler_with(status: int, body: dict | None = None):
    """GLM mock transport responding with a fixed HTTP status."""

    def handler(request: httpx.Request) -> httpx.Response:
        if status == 200:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(body or healthy_payload())}}]},
            )
        return httpx.Response(status, text="probe failure")

    return handler


def _install(client_mockable, handler):
    """Point the app's vision service at a new GLM transport."""
    from backend.main import app
    from backend.services.vision import GLMVisionClient, VisionService
    from backend.services.vision.service import get_vision_service

    service = VisionService(
        settings=TEST_SETTINGS,
        glm_client=GLMVisionClient(
            settings=TEST_SETTINGS,
            transport=httpx.MockTransport(handler),
            max_attempts=2,
            initial_retry_wait=0.01,
        ),
        local_predictor=None,
    )
    app.dependency_overrides[get_vision_service] = lambda: service


# ----------------------------------------------------------------------
# Diagnostics endpoint
# ----------------------------------------------------------------------


def test_diagnostics_reports_valid_key(client: TestClient) -> None:
    token = register_and_login(client, "diag-ok@test.dev")
    _install(client, glm_handler_with(200))
    response = client.get("/api/v1/diagnostics/vision", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "glm"
    assert body["key_configured"] is True
    assert body["reachable"] is True
    assert body["authenticated"] is True


def test_diagnostics_reports_rejected_key(client: TestClient) -> None:
    token = register_and_login(client, "diag-bad@test.dev")
    _install(client, glm_handler_with(401))
    response = client.get("/api/v1/diagnostics/vision", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["key_configured"] is True
    assert body["reachable"] is True
    assert body["authenticated"] is False
    assert "rejected" in body["detail"].lower()


def test_diagnostics_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/diagnostics/vision")
    assert response.status_code == 401


# ----------------------------------------------------------------------
# Auth-error surfacing on /inspect
# ----------------------------------------------------------------------


def test_inspect_auth_failure_returns_error_code(client: TestClient) -> None:
    token = register_and_login(client, "authfail@test.dev")
    palm = create_palm(client, token, "PALM-AUTHFAIL")

    from backend.main import app
    from backend.services.vision import GLMVisionClient, VisionService
    from backend.services.vision.service import get_vision_service

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text='{"error":{"code":"401","message":"bad token"}}')

    app.dependency_overrides[get_vision_service] = lambda: VisionService(
        settings=TEST_SETTINGS,
        glm_client=GLMVisionClient(
            settings=TEST_SETTINGS,
            transport=httpx.MockTransport(handler),
            max_attempts=2,
            initial_retry_wait=0.01,
        ),
        local_predictor=None,
    )

    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"]},
        files={"image": ("x.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "vision_provider_auth"
    assert "administrator" in body["detail"]
    assert calls["n"] == 1  # auth failures are never retried


def test_client_parses_error_code() -> None:
    from frontend.api_client import APIError

    error = APIError(503, "AI diagnosis is not available", "vision_provider_auth")
    assert error.error_code == "vision_provider_auth"
    assert error.status_code == 503


@pytest.mark.parametrize("probe_status", [400, 422])
def test_diagnostics_treats_non_auth_http_as_authenticated(
    client: TestClient, probe_status: int
) -> None:
    """A 400/422 probe still proves the key itself was accepted."""
    token = register_and_login(client, f"diag-{probe_status}@test.dev")
    _install(client, glm_handler_with(probe_status))
    body = client.get("/api/v1/diagnostics/vision", headers=auth(token)).json()
    assert body["authenticated"] is True
