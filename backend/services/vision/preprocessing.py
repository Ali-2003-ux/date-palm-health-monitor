"""OpenCV image preprocessing for palm inspection photos.

Pipeline: decode bytes (PIL, honouring EXIF orientation) -> BGR numpy
array -> downscale to the provider's max side -> objective quality
metrics (Laplacian blur variance, mean brightness) -> JPEG re-encode.
"""

from __future__ import annotations

import base64
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

from backend.services.vision.results import ImageQuality, InvalidImageError

#: GLM-4V accepts larger images but anything past ~1568 px adds latency
#: without adding diagnostic value for trunk/frond symptoms.
MAX_SIDE = 1568
JPEG_QUALITY = 90
_MIN_SIDE = 224  # below this the image cannot be diagnosed meaningfully
_BLUR_THRESHOLD = 60.0  # variance of Laplacian under this => blurry
_DARK_THRESHOLD = 35.0
_OVEREXPOSED_THRESHOLD = 220.0


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode raw bytes to a BGR numpy array, applying EXIF rotation.

    Raises InvalidImageError for empty, corrupt or non-image payloads.
    """
    if not image_bytes:
        raise InvalidImageError("Image payload is empty.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_image:
            pil_image = ImageOps.exif_transpose(pil_image)
            rgb = np.asarray(pil_image.convert("RGB"))
    except Exception as exc:
        raise InvalidImageError(f"Cannot decode image: {exc}") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def resize_max_side(image: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    """Downscale so the longest side is at most `max_side` (never upscales)."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def measure_quality(image: np.ndarray) -> ImageQuality:
    """Compute blur / brightness metrics and collect usability warnings."""
    height, width = image.shape[:2]
    warnings: list[str] = []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())

    if min(height, width) < _MIN_SIDE:
        warnings.append(
            f"Very small image ({width}x{height}px) — detail may be insufficient."
        )
    if sharpness < _BLUR_THRESHOLD:
        warnings.append(
            f"Image appears blurry (sharpness {sharpness:.0f} < "
            f"{_BLUR_THRESHOLD:.0f}) — re-shoot with stable focus."
        )
    if brightness < _DARK_THRESHOLD:
        warnings.append(
            f"Image is very dark (brightness {brightness:.0f}) — re-shoot in "
            "daylight."
        )
    elif brightness > _OVEREXPOSED_THRESHOLD:
        warnings.append(
            f"Image is overexposed (brightness {brightness:.0f}) — avoid "
            "shooting directly into the sun."
        )

    return ImageQuality(
        width_px=width,
        height_px=height,
        sharpness=sharpness,
        brightness=brightness,
        warnings=tuple(warnings),
    )


def encode_jpeg(image: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    """Encode a BGR array to JPEG bytes for storage or API upload."""
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise InvalidImageError("JPEG encoding failed.")
    return buffer.tobytes()


def to_data_url(jpeg_bytes: bytes) -> str:
    """Wrap JPEG bytes as a base64 data URL for vision-API payloads."""
    encoded = base64.b64encode(jpeg_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def preprocess(image_bytes: bytes) -> tuple[np.ndarray, ImageQuality]:
    """Full pipeline: decode + EXIF-orient + downscale + measure quality."""
    image = resize_max_side(decode_image(image_bytes))
    return image, measure_quality(image)
