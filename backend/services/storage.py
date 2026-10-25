"""Local filesystem storage for inspection photos.

Files land under `UPLOAD_DIR/{tree_code}/YYYYMMDD_HHMMSS_{short-uuid}.jpg`
and are served by the `/media` static mount, so the stored relative path
maps directly to a retrievable URL.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_SAFE_CODE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_segment(value: str) -> str:
    """Sanitise a tree code for use as a directory name."""
    cleaned = _SAFE_CODE_RE.sub("-", value).strip("-")
    return cleaned or "unknown"


def save_palm_image(tree_code: str, jpeg_bytes: bytes) -> Path:
    """Persist JPEG bytes and return the ABSOLUTE stored path."""
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid4().hex[:8]}.jpg"
    target_dir = settings.UPLOAD_DIR / _safe_segment(tree_code)

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(jpeg_bytes)
    logger.info("Stored inspection image: %s (%d KB)", target, len(jpeg_bytes) // 1024)
    return target


def image_url(stored_path: Path | str) -> str:
    """Public URL for a stored image via the /media static mount."""
    settings = get_settings()
    absolute = Path(stored_path)
    try:
        relative = absolute.resolve().relative_to(settings.UPLOAD_DIR.resolve())
    except ValueError:
        relative = Path(absolute.name)
    return f"/media/{relative.as_posix()}"
