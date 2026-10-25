"""End-to-end API tests: auth, palm registry, inspection flow."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import (
    auth,
    create_palm,
    healthy_payload,
    infected_payload,
    register_and_login,
    tiny_jpeg,
)

# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------


def test_health_no_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_login_me_flow(client: TestClient) -> None:
    token = register_and_login(client, "farmer@example.com")
    response = client.get("/api/v1/auth/me", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "farmer@example.com"
    assert body["role"] == "farmer"


def test_register_duplicate_email_conflict(client: TestClient) -> None:
    register_and_login(client, "dup@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "Another#Pass1",
            "full_name": "Dup",
        },
    )
    assert response.status_code == 409


def test_login_wrong_password(client: TestClient) -> None:
    register_and_login(client, "victim@example.com", "Correct#Pass1")
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "victim@example.com", "password": "Wrong#Pass1"},
    )
    assert response.status_code == 401


def test_short_password_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "short", "full_name": "X Y"},
    )
    assert response.status_code == 422


def test_protected_endpoints_require_token(client: TestClient) -> None:
    for method, url in [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/palms"),
        ("get", "/api/v1/inspections/recent"),
    ]:
        response = getattr(client, method)(url)
        assert response.status_code == 401, f"{url} returned {response.status_code}"


def test_invalid_token_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/palms", headers=auth("not-a-jwt"))
    assert response.status_code == 401


# ----------------------------------------------------------------------
# Palm registry
# ----------------------------------------------------------------------


def test_register_and_get_palm(client: TestClient) -> None:
    token = register_and_login(client, "palm-owner@example.com")
    palm = create_palm(client, token, "PALM-0001")
    assert palm["tree_code"] == "PALM-0001"
    assert float(palm["latitude"]) == 24.713600
    assert palm["variety"] == "Barhi"

    detail = client.get(f"/api/v1/palms/{palm['id']}", headers=auth(token))
    assert detail.status_code == 200
    assert detail.json()["id"] == palm["id"]


def test_duplicate_tree_code_conflict(client: TestClient) -> None:
    token = register_and_login(client, "codes@example.com")
    create_palm(client, token, "PALM-DUP")
    response = client.post(
        "/api/v1/palms",
        json={"tree_code": "PALM-DUP", "latitude": 1.0, "longitude": 1.0},
        headers=auth(token),
    )
    assert response.status_code == 409


def test_invalid_gps_rejected(client: TestClient) -> None:
    token = register_and_login(client, "gps@example.com")
    response = client.post(
        "/api/v1/palms",
        json={"tree_code": "PALM-BAD", "latitude": 95.0, "longitude": 0.0},
        headers=auth(token),
    )
    assert response.status_code == 422


def test_farmer_cannot_access_foreign_palm(client: TestClient) -> None:
    owner = register_and_login(client, "owner@example.com")
    intruder = register_and_login(client, "intruder@example.com")
    palm = create_palm(client, owner, "PALM-OWNED")

    response = client.get(f"/api/v1/palms/{palm['id']}", headers=auth(intruder))
    assert response.status_code == 403
    response = client.get(f"/api/v1/palms/{palm['id']}/history", headers=auth(intruder))
    assert response.status_code == 403


def test_farmer_lists_only_own_palms(client: TestClient) -> None:
    farmer_a = register_and_login(client, "a@example.com")
    farmer_b = register_and_login(client, "b@example.com")
    create_palm(client, farmer_a, "PALM-A1")
    create_palm(client, farmer_a, "PALM-A2")
    create_palm(client, farmer_b, "PALM-B1")

    listing = client.get("/api/v1/palms", headers=auth(farmer_a)).json()
    assert sorted(p["tree_code"] for p in listing) == ["PALM-A1", "PALM-A2"]


def test_unknown_palm_404(client: TestClient) -> None:
    token = register_and_login(client, "lost@example.com")
    response = client.get("/api/v1/palms/00000000-0000-0000-0000-000000000000", headers=auth(token))
    assert response.status_code == 404


# ----------------------------------------------------------------------
# Inspect + history
# ----------------------------------------------------------------------


def test_inspect_infected_persists_log_and_image(client: TestClient, glm_mock) -> None:
    token = register_and_login(client, "inspector@example.com")
    palm = create_palm(client, token, "PALM-INS1")

    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"]},
        files={"image": ("trunk.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()

    diagnosis = body["diagnosis"]
    assert diagnosis["detected_disease"] == "Red Palm Weevil"
    assert diagnosis["severity"] == "high"
    assert diagnosis["status"] == "critical"
    assert diagnosis["confidence"] == 0.91

    inspection = body["inspection"]
    assert inspection["palm_tree_id"] == palm["id"]
    assert inspection["status"] == "critical"
    assert inspection["confidence"] == 0.91
    assert inspection["treatment_recommendation"].startswith("Inject systemic")
    assert inspection["image_url"].startswith("/media/")
    assert glm_mock.calls == 1

    # The stored image is actually served back over the /media mount.
    media = client.get(inspection["image_url"])
    assert media.status_code == 200
    assert media.content[:2] == b"\xff\xd8"


def test_history_returns_newest_first_with_filters(client: TestClient, glm_mock) -> None:
    token = register_and_login(client, "historian@example.com")
    palm = create_palm(client, token, "PALM-HIST")

    glm_mock.set_sequence(infected_payload(), healthy_payload())

    first = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"], "captured_at": "2026-10-20T08:00:00Z"},
        files={"image": ("a.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"], "captured_at": "2026-10-24T08:00:00Z"},
        files={"image": ("b.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert second.status_code == 201
    assert glm_mock.calls == 2

    history = client.get(f"/api/v1/palms/{palm['id']}/history", headers=auth(token))
    assert history.status_code == 200
    logs = history.json()
    assert len(logs) == 2
    assert logs[0]["status"] == "healthy"  # newest first
    assert logs[1]["status"] == "critical"
    assert logs[0]["inspected_at"] > logs[1]["inspected_at"]

    infected_only = client.get(
        f"/api/v1/palms/{palm['id']}/history",
        params={"status": "critical"},
        headers=auth(token),
    )
    assert [log["status"] for log in infected_only.json()] == ["critical"]

    limited = client.get(
        f"/api/v1/palms/{palm['id']}/history", params={"limit": 1}, headers=auth(token)
    )
    assert len(limited.json()) == 1


def test_inspect_unknown_palm_404(client: TestClient) -> None:
    token = register_and_login(client, "ghost@example.com")
    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": "00000000-0000-0000-0000-000000000000"},
        files={"image": ("x.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert response.status_code == 404


def test_inspect_corrupt_image_400(client: TestClient) -> None:
    token = register_and_login(client, "corrupt@example.com")
    palm = create_palm(client, token, "PALM-CORRUPT")
    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"]},
        files={"image": ("bad.jpg", b"not an image at all", "image/jpeg")},
        headers=auth(token),
    )
    assert response.status_code == 400
    assert "Invalid image" in response.json()["detail"]


def test_inspect_wrong_extension_422(client: TestClient) -> None:
    token = register_and_login(client, "ext@example.com")
    palm = create_palm(client, token, "PALM-EXT")
    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"]},
        files={"image": ("clip.gif", b"gifdata", "image/gif")},
        headers=auth(token),
    )
    assert response.status_code == 422


def test_inspect_inference_failure_503(client: TestClient, glm_mock) -> None:
    token = register_and_login(client, "down@example.com")
    palm = create_palm(client, token, "PALM-DOWN")

    import httpx

    glm_mock.handler = lambda request: httpx.Response(500, text="unavailable")
    response = client.post(
        "/api/v1/inspect",
        data={"palm_tree_id": palm["id"]},
        files={"image": ("x.jpg", tiny_jpeg(), "image/jpeg")},
        headers=auth(token),
    )
    assert response.status_code == 503


def test_recent_inspections_feed_scoped_to_owner(client: TestClient, glm_mock) -> None:
    farmer = register_and_login(client, "feed@example.com")
    other = register_and_login(client, "other@example.com")
    palm = create_palm(client, farmer, "PALM-FEED")
    other_palm = create_palm(client, other, "PALM-OTHER")

    for tree_id in (palm["id"], other_palm["id"]):
        response = client.post(
            "/api/v1/inspect",
            data={"palm_tree_id": tree_id},
            files={"image": ("x.jpg", tiny_jpeg(), "image/jpeg")},
            headers=auth(farmer if tree_id == palm["id"] else other),
        )
        assert response.status_code == 201

    mine = client.get("/api/v1/inspections/recent", headers=auth(farmer)).json()
    assert len(mine) == 1
    assert mine[0]["palm_tree_id"] == palm["id"]
