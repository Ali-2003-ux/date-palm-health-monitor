"""Vision service — the single entry point for palm health analysis.

Validates and preprocesses the uploaded image, then dispatches to the
configured inference provider:

  * ``glm``       — GLM-4V cloud API (needs a key)
  * ``local_vlm`` — keyless open-source VLM in-container (SmolVLM)
  * ``local_cnn`` — locally trained MobileNetV2 (needs weights)

If the primary provider fails, the service degrades through the other
local providers before giving up.
"""

from __future__ import annotations

import asyncio

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger
from backend.services.vision.glm_client import GLMVisionClient
from backend.services.vision.local_cnn import LocalCNNPredictor
from backend.services.vision.local_vlm import LocalVLM
from backend.services.vision.preprocessing import encode_jpeg, preprocess
from backend.services.vision.results import (
    DiagnosisResult,
    InferenceError,
    InvalidImageError,
    ProviderUnavailableError,
)

logger = get_logger(__name__)


class VisionService:
    """Facade over preprocessing + inference providers."""

    def __init__(
        self,
        settings: Settings | None = None,
        glm_client: GLMVisionClient | None = None,
        local_predictor: LocalCNNPredictor | None = None,
        local_vlm: LocalVLM | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._glm = glm_client or GLMVisionClient(self._settings)
        self._local = local_predictor  # None => CNN fallback disabled
        self._vlm = local_vlm if local_vlm is not None else LocalVLM(self._settings)
        self._local_load_attempted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def analyze(
        self,
        image_bytes: bytes,
        filename: str = "image.jpg",
        context_note: str | None = None,
    ) -> DiagnosisResult:
        """Preprocess, diagnose and return the structured result.

        `context_note` carries registered tree metadata (variety, field) so
        vision providers can ground their verdict agronomically.
        """
        if len(image_bytes) > self._settings.max_upload_size_bytes:
            raise InvalidImageError(
                f"Image is {len(image_bytes) / 1_048_576:.1f} MB; the limit is "
                f"{self._settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        image, quality = preprocess(image_bytes)
        jpeg = encode_jpeg(image)

        result = await self._diagnose(jpeg, image, quality, filename, context_note)
        self._apply_threshold_policy(result)
        return result

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------
    async def _diagnose(
        self, jpeg, image, quality, filename, context_note: str | None = None
    ) -> DiagnosisResult:
        provider = self._settings.VISION_PROVIDER

        if provider == "local_vlm":
            return await self._run_vlm(image, quality)
        if provider == "local_cnn":
            return await self._run_local(image, quality)

        # Primary: GLM-4V / Gemini API. Degrade to local providers on failure.
        try:
            return await self._glm.analyze(
                jpeg, quality, filename, context_note=context_note
            )
        except InferenceError as exc:
            logger.warning("GLM provider failed (%s); trying local fallbacks.", exc)
            for fallback in (self._run_vlm, self._run_local):
                try:
                    return await fallback(image, quality)
                except ProviderUnavailableError:
                    continue
            raise exc from None

    async def _run_vlm(self, image, quality) -> DiagnosisResult:
        """Keyless open-source VLM (CPU) — our default offline provider."""
        if not self._vlm.available:
            raise ProviderUnavailableError(
                "Local VLM unavailable: torch/transformers not installed."
            )
        # CPU-bound inference — keep the event loop responsive.
        return await asyncio.to_thread(self._vlm.predict, image, quality)

    async def _run_local(self, image, quality) -> DiagnosisResult:
        """Run the local CNN, loading weights lazily on first use."""
        if self._local is None and not self._local_load_attempted:
            self._local_load_attempted = True
            try:
                self._local = LocalCNNPredictor(
                    self._settings.MODEL_WEIGHTS_PATH
                )
            except ProviderUnavailableError as exc:
                logger.warning("Local CNN unavailable: %s", exc)
                raise
        if self._local is None:
            raise ProviderUnavailableError(
                "Local CNN provider is not available (see log for the reason)."
            )
        # CPU-bound inference — keep the event loop responsive.
        return await asyncio.to_thread(self._local.predict, image, quality)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    async def provider_status(self) -> dict:
        """Health of the configured inference provider (for /diagnostics)."""
        provider = self._settings.VISION_PROVIDER
        if provider == "local_vlm":
            return await asyncio.to_thread(self._vlm.verify_connection)
        if provider == "local_cnn":
            available = self._local is not None or self._settings.MODEL_WEIGHTS_PATH.is_file()
            return {
                "provider": "local_cnn",
                "model": "mobilenetv2",
                "key_configured": True,
                "reachable": available,
                "authenticated": available,
                "detail": (
                    "OK — local CNN weights available."
                    if available
                    else f"CNN weights not found at {self._settings.MODEL_WEIGHTS_PATH}."
                ),
            }
        return await self._glm.verify_connection()

    # ------------------------------------------------------------------
    # Post-processing policy
    # ------------------------------------------------------------------
    def _apply_threshold_policy(self, result: DiagnosisResult) -> None:
        """Flag low-confidence diagnoses so the UI can ask for a re-shoot."""
        threshold = self._settings.CONFIDENCE_THRESHOLD
        if result.status.value == "healthy" and result.confidence < threshold:
            result.warnings += (
                (f"Low confidence ({result.confidence:.0%} < {threshold:.0%}) "
                "for a healthy verdict — consider a closer, better-lit photo."),
            )
            logger.info(
                "Low-confidence healthy verdict: %.2f (threshold %.2f)",
                result.confidence,
                threshold,
            )


_vision_service: VisionService | None = None


def get_vision_service() -> VisionService:
    """Module-level singleton for FastAPI dependency injection."""
    global _vision_service
    if _vision_service is None:
        _vision_service = VisionService()
    return _vision_service
