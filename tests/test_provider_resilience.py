"""Stabilization tests: provider backoff robustness + tree-context injection."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from backend.services.vision import GLMVisionClient
from backend.services.vision.results import InferenceError
from tests.conftest import TEST_SETTINGS, healthy_payload


def make_client(handler, max_attempts=4, wait=0.01) -> GLMVisionClient:
    return GLMVisionClient(
        settings=TEST_SETTINGS,
        transport=httpx.MockTransport(handler),
        max_attempts=max_attempts,
        initial_retry_wait=wait,
    )


def run(coro):
    return asyncio.run(coro)


DUMMY_QUALITY = None  # _to_result gets quality only via service; client returns raw content


def test_429_with_retry_after_is_honored_and_retried() -> None:
    calls = {"n": 0}
    started = time.monotonic()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(
                429, text="rate limited", headers={"Retry-After": "0.3"}
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(healthy_payload())}}]},
        )

    client = make_client(handler)
    content = run(client._request_completion(b"fake-jpeg"))
    elapsed = time.monotonic() - started

    assert calls["n"] == 3
    assert "is_healthy" in content
    # two waits, each at least the requested Retry-After (0.3s)
    assert elapsed >= 0.55


def test_503_high_demand_retried_up_to_max_attempts() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="high demand")

    client = make_client(handler, max_attempts=4)
    with pytest.raises(InferenceError, match="4 attempts"):
        run(client._request_completion(b"fake-jpeg"))
    assert calls["n"] == 4


def test_context_note_reaches_provider_prompt() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["text"] = body["messages"][1]["content"][1]["text"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(healthy_payload())}}]},
        )

    client = make_client(handler)
    run(client._request_completion(b"fake-jpeg", context_note="variety Barhi; field 'North Plot'"))
    assert "variety Barhi" in captured["text"]
    assert "North Plot" in captured["text"]


def test_no_context_note_leaves_prompt_unchanged() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["text"] = body["messages"][1]["content"][1]["text"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(healthy_payload())}}]},
        )

    client = make_client(handler)
    run(client._request_completion(b"fake-jpeg"))
    assert "Registered tree context" not in captured["text"]
