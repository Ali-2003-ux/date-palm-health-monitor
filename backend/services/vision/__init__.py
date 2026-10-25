"""Computer vision and AI inference module (Step 3).

Public surface:
    VisionService.analyze(image_bytes, filename) -> DiagnosisResult
"""

from backend.services.vision.glm_client import GLMVisionClient
from backend.services.vision.local_cnn import LocalCNNPredictor
from backend.services.vision.results import (
    DiagnosisResult,
    ImageQuality,
    InferenceError,
    InvalidImageError,
    ProviderUnavailableError,
    VisionError,
)
from backend.services.vision.service import VisionService, get_vision_service

__all__ = [
    "DiagnosisResult",
    "GLMVisionClient",
    "ImageQuality",
    "InferenceError",
    "InvalidImageError",
    "LocalCNNPredictor",
    "ProviderUnavailableError",
    "VisionError",
    "VisionService",
    "get_vision_service",
]
