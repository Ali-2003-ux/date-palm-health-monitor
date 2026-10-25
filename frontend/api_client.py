"""HTTP client for the Date Palm Health Monitor backend API.

Wraps every REST endpoint with typed methods, consistent error handling
(`APIError` carrying the server's `detail`) and automatic bearer-token
attachment. Used by the Streamlit dashboard; covered by the test suite
against the real FastAPI app via ASGI transport.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx


class APIError(Exception):
    """A non-2xx response from the backend."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class PalmMonitorClient:
    """Small typed facade over the /api/v1 surface."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 120.0):
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._token = token

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        data: dict | None = None,
        files: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        try:
            response = self._http.request(
                method,
                path,
                json=json,
                data=data,
                files=files,
                params=params,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise APIError(0, f"Cannot reach the backend: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if isinstance(detail, list):  # pydantic validation errors
                detail = "; ".join(str(item) for item in detail)
            raise APIError(response.status_code, str(detail))
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def register(self, email: str, password: str, full_name: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": full_name},
        )

    def login(self, email: str, password: str) -> str:
        body = self._request(
            "POST",
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        self._token = body["access_token"]
        return self._token

    def me(self) -> dict:
        return self._request("GET", "/api/v1/auth/me")

    # ------------------------------------------------------------------
    # Palms
    # ------------------------------------------------------------------
    def list_palms(self) -> list[dict]:
        return self._request("GET", "/api/v1/palms")

    def create_palm(
        self,
        tree_code: str,
        latitude: float,
        longitude: float,
        field_name: str | None = None,
        variety: str | None = None,
        planted_on: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "tree_code": tree_code,
            "latitude": latitude,
            "longitude": longitude,
        }
        if field_name:
            payload["field_name"] = field_name
        if variety:
            payload["variety"] = variety
        if planted_on:
            payload["planted_on"] = planted_on
        return self._request("POST", "/api/v1/palms", json=payload)

    def palm_history(
        self,
        palm_id: str | uuid.UUID,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self._request("GET", f"/api/v1/palms/{palm_id}/history", params=params)

    # ------------------------------------------------------------------
    # Inspections
    # ------------------------------------------------------------------
    def inspect(
        self,
        palm_id: str | uuid.UUID,
        image_bytes: bytes,
        filename: str = "capture.jpg",
        notes: str | None = None,
    ) -> dict:
        data = {"palm_tree_id": str(palm_id)}
        if notes:
            data["notes"] = notes
        return self._request(
            "POST",
            "/api/v1/inspect",
            data=data,
            files={"image": (filename, image_bytes, "image/jpeg")},
        )

    def recent_inspections(
        self, limit: int = 50, status: str | None = None
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self._request("GET", "/api/v1/inspections/recent", params=params)

    def get_image_bytes(self, image_url: str) -> bytes:
        """Fetch a stored inspection photo (public /media static route)."""
        response = self._http.get(image_url)
        if response.status_code != 200:
            raise APIError(response.status_code, "Could not load inspection image.")
        return response.content

    # ------------------------------------------------------------------
    def close(self) -> None:
        self._http.close()
