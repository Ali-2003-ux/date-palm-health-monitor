"""Vision service — the single entry point for palm health analysis.

Validates and preprocesses the uploaded image, dispatches to the
configured inference provider (GLM-4V API by default) and falls back to
the local CNN when the primary provider is unavailable and the optional
PyTorch stack is installed.
"""

from __future__ import annotations

import asyncio

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger
from backend.services.vision.glm_client import GLMVisionClient
from backend.services.vision.local_cnn import LocalCNNPredictor
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
    ) -> None:
        self._settings = settings or get_settings()
        self._glm = glm_client or GLMVisionClient(self._settings)
        self._local = local_predictor  # None => fallback disabled
        self._local_load_attempted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def analyze(
        self, image_bytes: bytes, filename: str = "image.jpg"
    ) -> DiagnosisResult:
        """Preprocess, diagnose and return the structured result."""
        if len(image_bytes) > self._settings.max_upload_size_bytes:
            raise InvalidImageError(
                f"Image is {len(image_bytes) / 1_048_576:.1f} MB; the limit is "
                f"{self._settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        image, quality = preprocess(image_bytes)
        jpeg = encode_jpeg(image)

        result = await self._diagnose(jpeg, image, quality, filename)
        self._apply_threshold_policy(result)
        return result

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------
    async def _diagnose(self, jpeg, image, quality, filename) -> DiagnosisResult:
        provider = self._settings.VISION_PROVIDER
        if provider == "local_cnn":
            return await self._run_local(image, quality)

        # Primary: GLM-4V API. On failure, degrade to local CNN if possible.
        try:
            return await self._glm.analyze(jpeg, quality, filename)
        except InferenceError as exc:
            logger.warning("GLM provider failed (%s); trying local fallback.", exc)
            try:
                return await self._run_local(image, quality)
            except ProviderUnavailableError:
                raise exc from None

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
