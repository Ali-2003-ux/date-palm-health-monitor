#!/usr/bin/env python
"""Environment verification for the Date Palm Health Monitoring System.

Run before starting development or deployment:

    python scripts/check_env.py

Checks performed:
  1. Python version (3.10 – 3.12).
  2. Every required third-party package imports and reports its version.
  3. Application configuration loads and passes pydantic validation.
  4. Runtime directories exist / can be created.
  5. Configuration warnings (missing GLM API key, default SECRET_KEY,
     missing CNN weights, etc.).

Exit code is 0 when the environment is usable, 1 otherwise.
"""

from __future__ import annotations

import importlib
import sys
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 12)

# import candidates (first that works) -> PyPI distribution name for version lookup
REQUIRED_PACKAGES: dict[tuple[str, ...], str] = {
    ("fastapi",): "fastapi",
    ("uvicorn",): "uvicorn",
    ("pydantic",): "pydantic",
    ("pydantic_settings",): "pydantic-settings",
    ("sqlalchemy",): "sqlalchemy",
    ("alembic",): "alembic",
    ("psycopg2",): "psycopg2-binary",
    ("jwt",): "pyjwt",
    ("bcrypt",): "bcrypt",
    ("cv2",): "opencv-python-headless",
    ("PIL",): "pillow",
    ("numpy",): "numpy",
    ("httpx",): "httpx",
    ("tenacity",): "tenacity",
    ("pandas",): "pandas",
    ("streamlit",): "streamlit",
    ("folium",): "folium",
    ("streamlit_folium",): "streamlit-folium",
    ("plotly",): "plotly",
    ("multipart", "python_multipart"): "python-multipart",
    ("dateutil",): "python-dateutil",
    ("email_validator",): "email-validator",
    ("pytest",): "pytest",
}

OK, FAIL, WARN = "[OK]  ", "[FAIL]", "[WARN]"

failures: list[str] = []
warnings: list[str] = []


def check_python() -> None:
    current = sys.version_info[:2]
    if MIN_PYTHON <= current <= MAX_PYTHON:
        print(f"{OK} Python {sys.version.split()[0]} (supported: 3.10-3.12)")
    else:
        failures.append(
            f"Python {current[0]}.{current[1]} is not supported; use 3.10 - 3.12"
        )
        print(f"{FAIL} Python {sys.version.split()[0]}")


def check_packages() -> None:
    for candidates, distribution in REQUIRED_PACKAGES.items():
        module = None
        for name in candidates:
            try:
                module = importlib.import_module(name)
                break
            except ImportError:
                continue
        if module is None:
            failures.append(f"Package '{distribution}' is not installed")
            print(f"{FAIL} {distribution:<26} (missing)")
            continue
        try:
            version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            version = "unknown version"
        print(f"{OK} {distribution:<26} {version}")


def check_config() -> None:
    try:
        from backend.core.config import get_settings

        settings = get_settings()
    except Exception as exc:  # noqa: BLE001 — surface any validation error
        failures.append(f"Configuration failed validation: {exc}")
        print(f"{FAIL} configuration: {exc}")
        return

    print(f"{OK} configuration loaded (ENVIRONMENT={settings.ENVIRONMENT})")
    print(
        f"      database -> postgresql://{settings.POSTGRES_USER}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    print(f"      inference -> {settings.VISION_PROVIDER} (model: {settings.GLM_VISION_MODEL})")

    if settings.ENVIRONMENT == "production":
        print(f"{OK} production safety checks passed (SECRET_KEY set, DEBUG off)")
    elif settings.SECRET_KEY.get_secret_value().startswith("dev-only"):
        warnings.append("SECRET_KEY is the development default — fine locally, never in production")
        print(f"{WARN} SECRET_KEY uses the development default")

    if settings.VISION_PROVIDER == "glm" and settings.GLM_API_KEY is None:
        warnings.append("GLM_API_KEY is not set — image inspection will fail until configured")
        print(f"{WARN} GLM_API_KEY is not set in .env")

    if settings.VISION_PROVIDER == "local_cnn" and not settings.MODEL_WEIGHTS_PATH.exists():
        warnings.append(
            f"MODEL_WEIGHTS_PATH does not exist: {settings.MODEL_WEIGHTS_PATH}"
        )
        print(f"{WARN} CNN weights not found at {settings.MODEL_WEIGHTS_PATH}")


def check_directories() -> None:
    try:
        from backend.core.config import get_settings

        settings = get_settings()
        settings.ensure_dirs()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"Runtime directories could not be created: {exc}")
        print(f"{FAIL} runtime directories: {exc}")
        return

    print(f"{OK} runtime directories ready ({settings.UPLOAD_DIR.name}/, ml/models/)")


def main() -> int:
    print("=" * 70)
    print("Date Palm Health Monitoring System — environment check")
    print("=" * 70)

    check_python()
    check_packages()
    check_config()
    check_directories()

    print("-" * 70)
    for warning in warnings:
        print(f"{WARN} {warning}")

    if failures:
        print(f"\nRESULT: {len(failures)} problem(s) found:")
        for failure in failures:
            print(f"  - {failure}")
        print("Fix the items above (usually: pip install -r requirements.txt)")
        return 1

    print("\nRESULT: environment is ready ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
