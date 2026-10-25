"""Tests for the keyless local_vlm provider and its dispatch logic."""

from __future__ import annotations

import asyncio

import pytest

from backend.core.config import Settings
from backend.models import InspectionStatus, Severity
from backend.services.vision.local_vlm import LocalVLM
from backend.services.vision.results import (
    DiagnosisResult,
    ImageQuality,
    ProviderUnavailableError,
)
from backend.services.vision.service import VisionService

QUALITY = ImageQuality(
    width_px=640, height_px=480, sharpness=500.0, brightness=128.0
)


def make_result(**overrides) -> DiagnosisResult:
    payload = {
        "detected_disease": None,
        "severity": None,
        "confidence": 0.9,
        "status": InspectionStatus.HEALTHY,
        "symptoms": [],
        "treatment_steps": [],
        "assessment": "ok",
        "provider": "local_vlm",
        "model": "stub",
        "latency_ms": 10,
        "quality": QUALITY,
    }
    payload.update(overrides)
    return DiagnosisResult(**payload)


class StubVLM:
    """Deterministic stand-in for the heavy model in dispatch tests."""

    available = True

    def __init__(self, result=None, fail=False):
        self.result = result or make_result()
        self.fail = fail
        self.calls = 0

    def predict(self, image, quality):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return self.result

    def verify_connection(self):
        return {
            "provider": "local_vlm", "model": "stub", "key_configured": True,
            "reachable": not self.fail, "authenticated": not self.fail,
            "detail": "OK" if not self.fail else "unavailable",
        }


class UnavailableVLM(LocalVLM):
    @property
    def available(self):
        return False


def test_settings_accept_local_vlm_provider() -> None:
    settings = Settings(VISION_PROVIDER="local_vlm")
    assert settings.LOCAL_VLM_MODEL.startswith("HuggingFaceTB/")
    assert settings.MODEL_CACHE_DIR.as_posix().endswith("ml/models/hf")


def test_local_vlm_unavailable_without_torch() -> None:
    service = VisionService(
        settings=Settings(VISION_PROVIDER="local_vlm"),
        local_vlm=UnavailableVLM(Settings()),
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(service._run_vlm(None, QUALITY))


def test_dispatch_uses_local_vlm_when_configured() -> None:
    stub = StubVLM()
    service = VisionService(
        settings=Settings(VISION_PROVIDER="local_vlm"), local_vlm=stub
    )
    result = asyncio.run(service._run_vlm("img", QUALITY))
    assert result.provider == "local_vlm"
    assert stub.calls == 1


def test_glm_failure_falls_back_to_local_vlm() -> None:
    from tests.conftest import GLMMock

    glm_mock = GLMMock()
    import httpx

    glm_mock.handler = staticmethod(
        lambda request: httpx.Response(500, text="down")
    )
    from backend.services.vision import GLMVisionClient

    stub = StubVLM(make_result(detected_disease="Red Palm Weevil",
                               severity=Severity.HIGH,
                               status=InspectionStatus.CRITICAL,
                               confidence=0.71))
    service = VisionService(
        settings=Settings(VISION_PROVIDER="glm"),
        glm_client=GLMVisionClient(
            settings=Settings(GLM_API_KEY=None),
            transport=httpx.MockTransport(glm_mock.handler),
            max_attempts=1,
            initial_retry_wait=0.001,
        ),
        local_vlm=stub,
    )
    # GLM has no key -> immediate InferenceError -> fallback to local_vlm
    result = asyncio.run(
        service._diagnose(b"j", "img", QUALITY, "test.jpg")
    )
    assert result.provider == "local_vlm"
    assert result.detected_disease == "Red Palm Weevil"


def test_provider_status_local_vlm() -> None:
    service = VisionService(
        settings=Settings(VISION_PROVIDER="local_vlm"),
        local_vlm=StubVLM(),
    )
    status = asyncio.run(service.provider_status())
    assert status["provider"] == "local_vlm"
    assert status["authenticated"] is True
