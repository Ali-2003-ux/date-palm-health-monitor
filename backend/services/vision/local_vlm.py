"""Local open-source VLM provider — keyless palm-health diagnosis.

Runs a small multimodal vision-language model (default: SmolVLM-500M,
an Apache-2.0 open model) entirely inside the container on CPU. No API
keys, no external services, no per-request cost. Weights are read from
MODEL_CACHE_DIR (mount a volume there in production; ~1 GB).

Output is parsed and grounded through the same knowledge base and
validation path as the GLM provider, so downstream behaviour is
identical regardless of provider.
"""

from __future__ import annotations

import re
import time
from typing import Any

import cv2
import numpy as np

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger
from backend.services.vision.glm_client import GLMVisionClient
from backend.services.vision.preprocessing import resize_max_side
from backend.services.vision.results import (
    DiagnosisResult,
    ImageQuality,
    InferenceError,
    ProviderUnavailableError,
)

logger = get_logger(__name__)

#: The 500M model gains nothing past this side — CPU inference cost does.
VLM_MAX_SIDE = 896

try:  # heavy deps are optional at import time (installed in the image)
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
except ImportError:  # pragma: no cover - exercised only without the extras
    torch = None
    AutoModelForImageTextToText = None
    AutoProcessor = None

#: Short schema — small VLMs follow terse instructions far better than
#: long ones, and copying the template verbatim must stay parseable.
DIAGNOSIS_PROMPT = """Look at this palm tree photo. Is the tree healthy or diseased? \
Answer with one single JSON line, filled with real values, no placeholders: \
{"is_healthy": true, "problem": null, "confidence": 0.85, "notes": "fronds look green"}"""


class LocalVLM:
    """CPU inference with an open-source vision-language model."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model_id = self._settings.LOCAL_VLM_MODEL
        self._cache_dir = str(self._settings.MODEL_CACHE_DIR)
        self._model = None
        self._processor = None
        self._load_attempted = False

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return torch is not None

    def _ensure_loaded(self) -> None:
        """Lazy-load model + processor once (slow first call)."""
        if self._model is not None:
            return
        if self._load_attempted and self._model is None:
            raise ProviderUnavailableError(
                "Local VLM failed to load earlier; check container logs."
            )
        self._load_attempted = True
        if torch is None:
            raise ProviderUnavailableError(
                "Local VLM requires torch+transformers — build the image "
                "with requirements-vlm.txt."
            )
        logger.info("Loading local VLM %s (cache: %s)...", self._model_id, self._cache_dir)
        started = time.monotonic()
        self._processor = AutoProcessor.from_pretrained(
            self._model_id, cache_dir=self._cache_dir
        )
        self._model = AutoModelForImageTextToText.from_pretrained(
            self._model_id,
            cache_dir=self._cache_dir,
            dtype=torch.float32,
            _attn_implementation="eager",
        )
        self._model.eval()
        logger.info(
            "Local VLM loaded in %.1fs", time.monotonic() - started
        )

    # ------------------------------------------------------------------
    def predict(self, image_bgr: np.ndarray, quality: ImageQuality) -> DiagnosisResult:
        """Synchronous CPU inference (call via asyncio.to_thread)."""
        self._ensure_loaded()

        started = time.monotonic()
        model_input = resize_max_side(image_bgr, max_side=VLM_MAX_SIDE)
        rgb = cv2.cvtColor(model_input, cv2.COLOR_BGR2RGB)

        messages = [{
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": DIAGNOSIS_PROMPT},
            ],
        }]
        prompt = self._processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        inputs = self._processor(
            text=prompt, images=[rgb], return_tensors="pt"
        )

        with torch.inference_mode():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=350,
                do_sample=False,
            )

        generated = output_ids[:, inputs["input_ids"].shape[1]:]
        content = self._processor.batch_decode(
            generated, skip_special_tokens=True
        )[0].strip()

        payload = self._parse_verdict(content)
        result = GLMVisionClient._to_result(
            payload,
            quality,
            started,
            model=self._model_id,
        )
        result.provider = "local_vlm"
        result.warnings += (
            ("Verdict produced by the on-device open-source model (SmolVLM) — "
            "a coarse first-pass screening, not an expert diagnosis."),
        )
        if not result.treatment_steps:
            result.treatment_steps = [
                ("Capture a closer photo of the affected area (trunk, crown, "
                "fronds) and re-run the inspection."),
                "Consult an agronomist before applying any treatment.",
            ]
        if result.detected_disease is None and result.status.value != "healthy":
            result.warnings += (
                ("The on-device model reported a problem but could not name it; "
                "verdict is provisional."),
            )
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_verdict(content: str) -> dict[str, Any]:
        """Map raw VLM output onto the GLM payload schema.

        Ladder: strict JSON -> regex scan -> error. Small models often
        emit fragments (e.g. an echoed template); whatever verdict we can
        honestly extract, we use — nothing is fabricated.
        """
        try:
            return GLMVisionClient._extract_json(content)
        except InferenceError:
            logger.debug("VLM output was not strict JSON; falling back to regex")

        healthy = re.search(
            r'"?is_healthy"?\s*:\s*(true|false)', content, re.IGNORECASE
        )
        if healthy is None:
            bare = LocalVLM._bare_verdict(content)
            if bare is not None:
                return bare
            raise InferenceError(
                f"Local VLM produced no usable verdict: {content[:200]!r}"
            )

        is_healthy = healthy.group(1).lower() == "true"
        problem_match = re.search(
            r'"?problem"?\s*:\s*"([^"]{2,80})"', content, re.IGNORECASE
        )
        confidence_match = re.search(
            r'"?confidence"?\s*:\s*([01](?:\.\d+)?)', content
        )
        notes_match = re.search(r'"?notes"?\s*:\s*"([^"]{2,200})"', content)

        return {
            "is_healthy": is_healthy,
            "detected_disease": None if is_healthy else problem_match.group(1),
            "confidence": (
                float(confidence_match.group(1)) if confidence_match else 0.45
            ),
            "assessment": notes_match.group(1) if notes_match else content[:200],
        }

    @staticmethod
    def _bare_verdict(content: str) -> dict[str, Any] | None:
        """Last resort: classify a one-word/one-sentence answer.

        Small models often answer 'True.' or 'Yes, healthy'. Returns a
        payload only when a clear health signal exists; never invents a
        disease name (None stays None -> provisional warning upstream).
        """
        text = content.strip().lower()
        if len(text) > 300:  # long rambling output without any verdict markers
            return None
        unhealthy = re.search(
            r"\b(false|no\b|diseased|disease|infected|problem|damage|"
            r"pest|rot|spot|wilt|unhealthy|sick)\b",
            text,
        )
        healthy = re.search(
            r"\b(true|yes|healthy|normal|fine|no problem|no disease)\b", text
        )
        if unhealthy:
            return {
                "is_healthy": False,
                "detected_disease": None,
                "confidence": 0.40,
                "assessment": content[:200],
            }
        if healthy:
            return {
                "is_healthy": True,
                "detected_disease": None,
                "confidence": 0.40,
                "assessment": content[:200],
            }
        return None

    def verify_connection(self) -> dict[str, Any]:
        """Diagnostics shape matching the GLM probe."""
        try:
            self._ensure_loaded()
        except ProviderUnavailableError as exc:
            return {
                "provider": "local_vlm",
                "model": self._model_id,
                "key_configured": True,
                "reachable": False,
                "authenticated": False,
                "detail": str(exc),
            }
        return {
            "provider": "local_vlm",
            "model": self._model_id,
            "key_configured": True,
            "reachable": True,
            "authenticated": True,
            "detail": "OK — local open-source model loaded, no API key needed.",
        }
