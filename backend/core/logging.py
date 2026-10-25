"""
Centralised logging configuration.

Provides one `setup_logging()` call that configures the root logger with:
  * a console handler (stdout), and
  * a rotating file handler under `logs/palm_monitor.log`
    (5 MB per file, 5 rotated backups).

All modules then obtain loggers via `get_logger(__name__)`.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from backend.core.config import BASE_DIR, get_settings

_LOG_DIR = BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "palm_monitor.log"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def setup_logging(level: int | None = None) -> None:
    """Configure the root logger exactly once (idempotent)."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    if level is None:
        level = logging.DEBUG if settings.DEBUG else logging.INFO

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Uvicorn installs its own handlers on import; keep them aligned.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(noisy)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    _configured = True
    logging.getLogger(__name__).debug("Logging configured (file: %s)", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger; call `setup_logging()` once at startup."""
    return logging.getLogger(name)


def log_file_path() -> Path:
    """Absolute path of the rotating log file (useful for diagnostics)."""
    return _LOG_FILE
