"""
Centralised application configuration.

Every runtime tunable lives here and is sourced from environment
variables (12-factor style), with an optional `.env` file at the project
root for local development. Run `python scripts/check_env.py` to validate
the configuration before starting the services.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Project root — the folder containing `backend/`, `ml/`, `frontend/`, ...
BASE_DIR: Path = Path(__file__).resolve().parents[2]

#: Placeholder secret; accepted only outside production environments.
_INSECURE_DEFAULT_SECRET: str = (
    "dev-only-secret-key-change-in-production-0123456789abcdef"
)


class Settings(BaseSettings):
    """All environment-driven settings, validated once at load time."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env may also carry frontend-only variables
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "Date Palm Health Monitor"
    APP_DESCRIPTION: str = (
        "AI-powered monitoring of date palm health: disease detection "
        "(Red Palm Weevil, fungal infections) and agricultural analytics."
    )
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # HTTP server
    # ------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)
    WORKERS: int = Field(default=1, ge=1, le=32)
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"]
    )

    # ------------------------------------------------------------------
    # Database (PostgreSQL)
    # ------------------------------------------------------------------
    POSTGRES_USER: str = "palm_admin"
    POSTGRES_PASSWORD: SecretStr = SecretStr("change-me-strong-password")
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = Field(default=5432, ge=1, le=65535)
    POSTGRES_DB: str = "palm_monitor"
    #: Optional full DSN — overrides the individual POSTGRES_* variables.
    DATABASE_URL: str | None = None
    DB_ECHO_LOG: bool = False
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)

    # ------------------------------------------------------------------
    # Security / authentication (used from Step 2 onward)
    # ------------------------------------------------------------------
    SECRET_KEY: SecretStr = SecretStr(_INSECURE_DEFAULT_SECRET)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, ge=1)

    # ------------------------------------------------------------------
    # AI inference (implemented in Step 3)
    # ------------------------------------------------------------------
    VISION_PROVIDER: Literal["glm", "local_cnn", "local_vlm"] = "glm"
    #: OpenAI-compatible vision provider. Production default: Google Gemini.
    GLM_API_KEY: SecretStr | None = None
    GLM_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GLM_VISION_MODEL: str = "gemini-2.5-flash"
    #: Open-source local VLM (keyless) — weights under MODEL_CACHE_DIR.
    LOCAL_VLM_MODEL: str = "HuggingFaceTB/SmolVLM-500M-Instruct"
    MODEL_CACHE_DIR: Path = BASE_DIR / "ml" / "models" / "hf"
    INFERENCE_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=600)
    CONFIDENCE_THRESHOLD: float = Field(default=0.60, ge=0.0, le=1.0)
    MODEL_WEIGHTS_PATH: Path = BASE_DIR / "ml" / "models" / "mobilenetv2_palm_best.pt"

    # ------------------------------------------------------------------
    # File storage
    # ------------------------------------------------------------------
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MAX_UPLOAD_SIZE_MB: int = Field(default=15, ge=1, le=100)
    ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Accept a comma-separated string from .env: CORS_ORIGINS=a,b,c"""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("UPLOAD_DIR", "MODEL_WEIGHTS_PATH", mode="after")
    @classmethod
    def _anchor_to_project_root(cls, value: Path) -> Path:
        """Interpret relative paths from .env relative to the project root."""
        return value if value.is_absolute() else (BASE_DIR / value).resolve()

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY.get_secret_value() == _INSECURE_DEFAULT_SECRET:
                raise ValueError(
                    "SECRET_KEY still equals the insecure development default. "
                    'Generate a real key with: python -c "import secrets; '
                    'print(secrets.token_urlsafe(64))"'
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be false when ENVIRONMENT=production.")
        return self

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    @property
    def database_url(self) -> str:
        """SQLAlchemy connection URL using the sync psycopg2 driver."""
        if self.DATABASE_URL:
            # Managed platforms (Render, Heroku, Neon) inject `postgres://`
            # or bare `postgresql://` URLs; SQLAlchemy 2.x needs the driver
            # pinned or it defaults to psycopg3 (not installed).
            for prefix in ("postgres://", "postgresql://"):
                if self.DATABASE_URL.startswith(prefix):
                    return self.DATABASE_URL.replace(
                        prefix, "postgresql+psycopg2://", 1
                    )
            return self.DATABASE_URL
        password = quote_plus(self.POSTGRES_PASSWORD.get_secret_value())
        user = quote_plus(self.POSTGRES_USER)
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def ensure_dirs(self) -> None:
        """Create runtime directories on demand (safe to call repeatedly)."""
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.MODEL_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached, validated settings singleton."""
    return Settings()
