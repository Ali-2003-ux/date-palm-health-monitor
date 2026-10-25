"""Local CNN inference (MobileNetV2) — offline fallback provider.

Runs a locally trained MobileNetV2 checkpoint from `ml/models/` on CPU or
GPU. The checkpoint must be a torch-saved dict containing the model
`state_dict` and the ordered `class_names` it was trained on (see
ml/train/ utilities in a later step). Class names must match knowledge
base keys (e.g. "red_palm_weevil", "healthy").

PyTorch is an OPTIONAL dependency: when it is not installed the
constructor raises ProviderUnavailableError with install instructions,
and the service skips this provider.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.core.logging import get_logger
from backend.services.vision import knowledge_base as kb
from backend.services.vision.results import (
    DiagnosisResult,
    ImageQuality,
    ProviderUnavailableError,
)

logger = get_logger(__name__)

try:  # torch is optional (see requirements.txt)
    import torch
    from torchvision import transforms
    from torchvision.models import MobileNet_V2_Weights, mobilenet_v2
except ImportError:  # pragma: no cover - exercised only without torch
    torch = None
    transforms = None
    mobilenet_v2 = None
    MobileNet_V2_Weights = None

#: Input normalisation the pretrained MobileNetV2 backbone expects.
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


class LocalCNNPredictor:
    """Loads a trained MobileNetV2 once and classifies palm images."""

    def __init__(self, weights_path, device: str | None = None) -> None:
        if torch is None:
            raise ProviderUnavailableError(
                "Local CNN provider requested but PyTorch is not installed. "
                "Install the optional stack: "
                "pip install 'torch>=2.5,<3.0' 'torchvision>=0.20,<1.0'"
            )
        weights_path = str(weights_path)
        if not Path(weights_path).is_file():
            raise ProviderUnavailableError(
                f"CNN weights not found at {weights_path}. Train or download "
                "a MobileNetV2 checkpoint and place it there, or switch "
                "VISION_PROVIDER back to 'glm'."
            )

        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        checkpoint: dict[str, Any] = torch.load(
            weights_path, map_location=self.device, weights_only=False
        )
        self.class_names: list[str] = list(checkpoint["class_names"])
        state_dict = checkpoint["state_dict"]

        model = mobilenet_v2(weights=None)
        model.classifier[1] = torch.nn.Linear(
            model.last_channel, len(self.class_names)
        )
        model.load_state_dict(state_dict)
        model.to(self.device)
        model.eval()
        self.model = model

        self._transform = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(_IMAGENET_MEAN, _IMAGENET_STD),
            ]
        )
        logger.info(
            "Local CNN loaded (%d classes: %s) on %s",
            len(self.class_names),
            ", ".join(self.class_names),
            self.device,
        )

    def predict(
        self, image_bgr: np.ndarray, quality: ImageQuality
    ) -> DiagnosisResult:
        """Classify a preprocessed BGR image and build the diagnosis."""
        if torch is None:  # pragma: no cover - constructor already guards
            raise ProviderUnavailableError("PyTorch not installed.")

        started = time.monotonic()
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        tensor = self._transform(rgb).unsqueeze(0).to(self.device)

        with torch.inference_mode():
            probabilities = torch.softmax(self.model(tensor), dim=1)[0]
        top_idx = int(torch.argmax(probabilities).item())
        class_name = self.class_names[top_idx]
        confidence = float(probabilities[top_idx].item())

        entry = kb.lookup_disease(class_name)
        is_healthy = entry is None or entry is kb.HEALTHY
        if is_healthy:
            status = kb.derive_status(True, None, None)
        else:
            status = kb.derive_status(False, entry, entry.default_severity)

        result = DiagnosisResult(
            detected_disease=None if is_healthy else entry.display_name,
            severity=None if is_healthy else entry.default_severity,
            confidence=confidence,
            status=status,
            symptoms=[f"Classified as '{class_name}' by local CNN"],
            treatment_steps=[] if is_healthy else list(entry.treatment_steps),
            assessment=(
                "Offline CNN classification. A vision-language model is not "
                "available; verify the finding with an agronomist."
                if not is_healthy
                else "Offline CNN classification: no disease detected."
            ),
            provider="local_cnn",
            model="mobilenetv2",
            latency_ms=int((time.monotonic() - started) * 1000),
            quality=quality,
            warnings=(
                ("Diagnosis produced by the offline CNN fallback — lower "
                "contextual accuracy than the vision-language model."),
            ),
        )
        logger.info(
            "Local CNN prediction: class=%s confidence=%.2f (%d ms)",
            class_name,
            confidence,
            result.latency_ms,
        )
        return result
