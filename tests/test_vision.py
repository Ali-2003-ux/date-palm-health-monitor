"""Tests for the vision module: preprocessing, GLM client, service."""

from __future__ import annotations

import asyncio
import json

import cv2
import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from backend.core.config import Settings, get_settings
from backend.models import InspectionStatus, Severity
from backend.services.vision import (
    DiagnosisResult,
    GLMVisionClient,
    ImageQuality,
    InferenceError,
    InvalidImageError,
    VisionService,
)
from backend.services.vision import (
    knowledge_base as kb,
)
from backend.services.vision.preprocessing import (
    MAX_SIDE,
    decode_image,
    encode_jpeg,
    measure_quality,
    preprocess,
    resize_max_side,
    to_data_url,
)

# ----------------------------------------------------------------------
# Helpers: synthetic but real images (drawn with OpenCV, no fixtures)
# ----------------------------------------------------------------------


def make_photo(width: int = 2400, height: int = 1800, blurry: bool = False) -> bytes:
    """A textured 'photo': gradient background + shapes + sensor noise."""
    xs = np.linspace(0, 255, width, dtype=np.float32)
    background = np.tile(xs, (height, 1))
    image = cv2.merge([background, background * 0.6 + 40, 255 - background])
    image = image.astype(np.uint8)

    rng = np.random.default_rng(42)
    for _ in range(60):
        center = (int(rng.integers(0, width)), int(rng.integers(0, height)))
        radius = int(rng.integers(8, 90))
        color = tuple(int(c) for c in rng.integers(0, 255, 3))
        cv2.circle(image, center, radius, color, thickness=-1)
    image = rng.integers(0, 24, image.shape, dtype=np.uint8) + image  # noise

    if blurry:
        image = cv2.GaussianBlur(image, (31, 31), 12)

    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def glm_response(payload: dict) -> httpx.Response:
    """A well-formed GLM chat-completions response wrapping `payload`."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


def run(coro):
    """Drive async code from sync tests (pytest-asyncio not required)."""
    return asyncio.run(coro)


DUMMY_QUALITY = ImageQuality(width_px=640, height_px=480, sharpness=500.0, brightness=128.0)


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


# ----------------------------------------------------------------------
# Preprocessing
# ----------------------------------------------------------------------


def test_decode_and_resize() -> None:
    image = decode_image(make_photo(2400, 1800))
    assert image.shape[:2] == (1800, 2400)  # untouched if under MAX_SIDE? no: over

    resized = resize_max_side(image)
    h, w = resized.shape[:2]
    assert max(h, w) == MAX_SIDE
    assert abs(w / h - 2400 / 1800) < 0.01  # aspect ratio preserved


def test_small_image_not_upscaled() -> None:
    image = decode_image(make_photo(640, 480))
    assert resize_max_side(image).shape[:2] == (480, 640)


def test_corrupt_bytes_rejected() -> None:
    with pytest.raises(InvalidImageError):
        decode_image(b"this is not an image")
    with pytest.raises(InvalidImageError):
        decode_image(b"")


def test_quality_metrics_and_blur_flag() -> None:
    sharp = measure_quality(decode_image(make_photo()))
    blurry = measure_quality(decode_image(make_photo(blurry=True)))

    assert sharp.sharpness > blurry.sharpness
    assert sharp.sharpness > 60 and not sharp.is_blurry
    assert blurry.is_blurry
    assert any("blurry" in w for w in blurry.warnings)
    assert 0 <= sharp.brightness <= 255


def test_jpeg_roundtrip_and_data_url() -> None:
    image = decode_image(make_photo(800, 600))
    jpeg = encode_jpeg(image)
    assert jpeg[:2] == b"\xff\xd8"  # JPEG magic bytes

    data_url = to_data_url(jpeg)
    assert data_url.startswith("data:image/jpeg;base64,")

    decoded = decode_image(jpeg)  # what the pipeline feeds downstream
    assert decoded.shape[:2] == (600, 800)


def test_preprocess_pipeline_output_types() -> None:
    image, quality = preprocess(make_photo(3000, 2000))
    assert max(image.shape[:2]) <= MAX_SIDE
    assert quality.width_px <= MAX_SIDE
    assert isinstance(quality.warnings, tuple)


# ----------------------------------------------------------------------
# Knowledge base
# ----------------------------------------------------------------------


def test_lookup_aliases() -> None:
    assert kb.lookup_disease("Red Palm Weevil").key == "red_palm_weevil"
    assert kb.lookup_disease("RPW").key == "red_palm_weevil"
    assert kb.lookup_disease("bayoud").key == "fusarium_wilt"
    assert kb.lookup_disease("Healthy") is None
    assert kb.lookup_disease("") is None


def test_derive_status() -> None:
    rpw = kb.DISEASES["red_palm_weevil"]
    spot = kb.DISEASES["graphiola_leaf_spot"]

    assert kb.derive_status(True, None, None) is InspectionStatus.HEALTHY
    assert kb.derive_status(False, rpw, Severity.HIGH) is InspectionStatus.CRITICAL
    assert kb.derive_status(False, rpw, Severity.LOW) is InspectionStatus.CRITICAL
    assert kb.derive_status(False, spot, Severity.LOW) is InspectionStatus.INFECTED


# ----------------------------------------------------------------------
# GLM client (real HTTP layer via httpx.MockTransport)
# ----------------------------------------------------------------------


#: Real Settings with a dummy API key: the client must never hit the
#: network (MockTransport) but must pass its key-configured precondition.
TEST_SETTINGS = Settings(GLM_API_KEY=SecretStr("unit-test-key"))


def make_client(handler) -> GLMVisionClient:
    return GLMVisionClient(
        settings=TEST_SETTINGS,
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        initial_retry_wait=0.01,
    )


def test_glm_success_infected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == TEST_SETTINGS.GLM_VISION_MODEL
        user = body["messages"][1]["content"]
        assert any(p["type"] == "image_url" for p in user)
        assert request.headers["Authorization"].startswith("Bearer ")
        return glm_response(infected_payload())

    client = make_client(handler)
    result = run(client.analyze(encode_jpeg(decode_image(make_photo(640, 480))), DUMMY_QUALITY))

    assert result.status is InspectionStatus.CRITICAL
    assert result.detected_disease == "Red Palm Weevil"
    assert result.severity is Severity.HIGH
    assert result.confidence == pytest.approx(0.91)
    assert result.treatment_steps
    assert result.provider == "glm"
    assert result.latency_ms >= 0


def test_glm_success_healthy() -> None:
    payload = {
        "is_healthy": True,
        "detected_disease": None,
        "severity": None,
        "confidence": 0.97,
        "symptoms": [],
        "treatment_steps": [],
        "assessment": "Palm appears vigorous.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return glm_response(payload)

    result = run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))
    assert result.status is InspectionStatus.HEALTHY
    assert result.detected_disease is None and result.severity is None


def test_glm_parses_fenced_json() -> None:
    content = "Sure! Here is my analysis:\n```json\n" + json.dumps(infected_payload()) + "\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    result = run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))
    assert result.detected_disease == "Red Palm Weevil"


def test_glm_retries_transient_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="service unavailable")
        return glm_response(infected_payload())

    result = run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))
    assert calls["n"] == 2  # one failure, then success
    assert result.status is InspectionStatus.CRITICAL


def test_glm_gives_up_after_max_attempts() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    with pytest.raises(InferenceError, match="unreachable"):
        run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))
    assert calls["n"] == 3


def test_glm_no_retry_on_client_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(InferenceError, match="rejected"):
        run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))
    assert calls["n"] == 1  # never retried


def test_glm_malformed_content_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "no json here"}}]}
        )

    with pytest.raises(InferenceError, match="No JSON object"):
        run(make_client(handler).analyze(b"fake-jpeg", DUMMY_QUALITY))


# ----------------------------------------------------------------------
# VisionService end-to-end (preprocess -> provider -> policy)
# ----------------------------------------------------------------------


def make_service(handler) -> VisionService:
    settings = TEST_SETTINGS
    return VisionService(
        settings=settings,
        glm_client=GLMVisionClient(
            settings=settings,
            transport=httpx.MockTransport(handler),
            max_attempts=2,
            initial_retry_wait=0.01,
        ),
        local_predictor=None,  # no torch => fallback disabled in tests
    )


def test_service_full_pipeline_infected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return glm_response(infected_payload())

    service = make_service(handler)
    result = run(service.analyze(make_photo(2600, 1900)))

    assert isinstance(result, DiagnosisResult)
    assert result.status is InspectionStatus.CRITICAL
    assert result.quality.width_px <= MAX_SIDE
    assert result.confidence > 0


def test_service_healthy_low_confidence_warning() -> None:
    payload = {
        "is_healthy": True,
        "detected_disease": None,
        "severity": None,
        "confidence": 0.4,  # below CONFIDENCE_THRESHOLD (0.60)
        "symptoms": [],
        "treatment_steps": [],
        "assessment": "Unsure — image partially obscured.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return glm_response(payload)

    result = run(make_service(handler).analyze(make_photo(800, 600)))
    assert result.status is InspectionStatus.HEALTHY
    assert any("Low confidence" in w for w in result.warnings)


def test_service_oversized_upload_rejected() -> None:
    settings = get_settings()
    service = make_service(lambda request: glm_response(infected_payload()))

    too_big = b"\x00" * (settings.max_upload_size_bytes + 1)
    with pytest.raises(InvalidImageError, match="MB"):
        run(service.analyze(too_big))


def test_service_falls_back_and_surfaces_error_without_local() -> None:
    """GLM fails AND local CNN is unavailable => original error raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="down")

    with pytest.raises(InferenceError):
        run(make_service(handler).analyze(make_photo(640, 480)))
