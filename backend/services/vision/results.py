"""Structured result contract and exceptions for the vision module."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.models import InspectionStatus, Severity


class VisionError(Exception):
    """Base class for all vision-module failures."""


class InvalidImageError(VisionError):
    """The uploaded bytes are not a usable image (corrupt/empty/oversized)."""


class InferenceError(VisionError):
    """An inference provider failed after retries."""


class ProviderAuthError(InferenceError):
    """The provider rejected our credentials (HTTP 401/403).

    Distinguished from transient failures so the API can tell users the
    truth: 'retry' will not help until the key is fixed.
    """


class ProviderUnavailableError(InferenceError):
    """The configured provider cannot run (missing key, weights or library)."""


class ImageQuality(BaseModel):
    """Objective quality metrics from OpenCV analysis of the input image."""

    model_config = ConfigDict(frozen=True)

    width_px: int
    height_px: int
    sharpness: float = Field(description="Variance of the Laplacian (blur metric)")
    brightness: float = Field(description="Mean pixel intensity 0-255")
    warnings: tuple[str, ...] = ()

    @property
    def is_blurry(self) -> bool:
        return self.sharpness < 60.0


class DiagnosisResult(BaseModel):
    """Structured AI diagnosis — the single output contract of Step 3.

    Field names align 1:1 with the `inspection_logs` columns so Step 4
    can persist this directly.
    """

    detected_disease: str | None
    severity: Severity | None
    confidence: float = Field(ge=0.0, le=1.0)
    status: InspectionStatus
    symptoms: list[str] = Field(default_factory=list)
    treatment_steps: list[str] = Field(default_factory=list)
    assessment: str | None = None
    provider: str
    model: str
    latency_ms: int
    quality: ImageQuality
    warnings: tuple[str, ...] = ()
