"""Single-process backend for Streamlit Community Cloud.

Implements the SAME interface as frontend.api_client.PalmMonitorClient but
talks directly to SQLAlchemy + the vision service in-process — no FastAPI
server, no second deploy. Enabled via PALM_CLOUD=1 (Streamlit secrets):
the Streamlit app becomes the entire system.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.logging import get_logger, setup_logging
from backend.core.security import hash_password, verify_password
from backend.db.base import Base  # noqa: F401 - registers metadata
from backend.models import InspectionLog, InspectionStatus, PalmTree, User
from backend.services.vision.preprocessing import decode_image

setup_logging()
logger = get_logger(__name__)


class CloudAuthError(Exception):
    """Login/registration failure with a user-friendly message."""


class LocalBackend:
    """Drop-in replacement for PalmMonitorClient backed by the local DB."""

    def __init__(self, database_url: str, glm_api_key: str) -> None:
        import os

        os.environ.setdefault("DATABASE_URL", database_url)
        if glm_api_key:
            os.environ.setdefault("GLM_API_KEY", glm_api_key)
        os.environ.setdefault("ENVIRONMENT", "production")
        os.environ.setdefault("DEBUG", "false")
        os.environ.setdefault("VISION_PROVIDER", "glm")
        # Cloud instances have ~1 GB RAM: the SmolVLM fallback (needs torch,
        # ~2 GB) is disabled — Gemini-only with honest errors.
        os.environ["VISION_PROVIDER"] = "glm"

        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        try:  # idempotent — Neon is already migrated; covers fresh forks
            alembic_path = str(Path(__file__).resolve().parents[1] / "alembic.ini")
            alembic_command.upgrade(AlembicConfig(alembic_path), "head")
        except Exception as exc:  # noqa: BLE001 - never block boot on this
            logger.warning("startup migration skipped: %s", exc)

        from backend.core.config import Settings
        from backend.db.session import get_session_factory
        from backend.services.vision.service import VisionService as _VS

        self._settings = Settings()
        self._factory: sessionmaker[Session] = get_session_factory()
        self._vision: Any = _VS(self._settings)

    # ------------------------------------------------------------------
    # Session helper
    # ------------------------------------------------------------------
    def _db(self) -> Session:
        return self._factory()

    # ------------------------------------------------------------------
    # Authentication (session carried by the Streamlit app, not JWT)
    # ------------------------------------------------------------------
    def register(self, email: str, password: str, full_name: str) -> dict:
        with self._db() as session:
            exists = session.scalar(select(User).where(User.email == email.strip().lower()))
            if exists is not None:
                raise CloudAuthError("An account with this email already exists.")
            user = User(
                email=email, hashed_password=hash_password(password),
                full_name=full_name,
            )
            session.add(user)
            session.commit()
            return self._user_dict(user)

    def login(self, email: str, password: str) -> str:
        with self._db() as session:
            user = session.scalar(select(User).where(User.email == email.strip().lower()))
            if user is None or not verify_password(password, user.hashed_password):
                raise CloudAuthError("Incorrect email or password.")
            if not user.is_active:
                raise CloudAuthError("This account is disabled.")
        return "local-session"  # placeholder; identity lives in session_state

    def login_user(self, email: str, password: str) -> dict:
        """Verify credentials and return the full user dict (cloud sessions)."""
        with self._db() as session:
            user = session.scalar(select(User).where(User.email == email.strip().lower()))
            if user is None or not verify_password(password, user.hashed_password):
                raise CloudAuthError("Incorrect email or password.")
            if not user.is_active:
                raise CloudAuthError("This account is disabled.")
            return self._user_dict(user)

    def me(self, user_id: str | None = None) -> dict:
        with self._db() as session:
            user = session.get(User, uuid.UUID(str(user_id))) if user_id else None
            if user is None:
                raise CloudAuthError("Session expired — sign in again.")
            return self._user_dict(user)

    @staticmethod
    def _user_dict(user: User) -> dict:
        return {
            "id": str(user.id), "email": user.email, "full_name": user.full_name,
            "role": user.role.value, "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Palms
    # ------------------------------------------------------------------
    def list_palms(self, user: dict | None = None) -> list[dict]:
        with self._db() as session:
            query = select(PalmTree)
            if user and user["role"] == "farmer":
                query = query.where(PalmTree.owner_id == uuid.UUID(user["id"]))
            palms = session.scalars(query.order_by(PalmTree.tree_code)).all()
            out = []
            for palm in palms:
                logs = session.scalars(
                    select(InspectionLog)
                    .where(InspectionLog.palm_tree_id == palm.id)
                    .order_by(InspectionLog.inspected_at.desc())
                ).all()
                latest = logs[0] if logs else None
                out.append({
                    "id": str(palm.id), "owner_id": str(palm.owner_id),
                    "tree_code": palm.tree_code,
                    "latitude": float(palm.latitude), "longitude": float(palm.longitude),
                    "field_name": palm.field_name, "variety": palm.variety,
                    "planted_on": palm.planted_on.isoformat() if palm.planted_on else None,
                    "location_metadata": palm.location_metadata,
                    "created_at": palm.created_at.isoformat(),
                    "total_inspections": len(logs),
                    "latest_status": latest.status.value if latest else None,
                    "latest_disease": latest.detected_disease if latest else None,
                })
            return out

    def create_palm(self, tree_code: str, latitude: float, longitude: float,
                    field_name: str | None = None, variety: str | None = None,
                    planted_on: str | None = None, user: dict | None = None) -> dict:
        with self._db() as session:
            owner = uuid.UUID(user["id"]) if user else None
            if owner is None:
                raise CloudAuthError("Sign in required.")
            exists = session.scalar(select(PalmTree).where(PalmTree.tree_code == tree_code))
            if exists is not None:
                raise CloudAuthError(f"Tree code '{tree_code}' is already registered.")
            palm = PalmTree(
                owner_id=owner, tree_code=tree_code, latitude=latitude,
                longitude=longitude, field_name=field_name, variety=variety,
                **({"planted_on": planted_on} if planted_on else {}),
            )
            session.add(palm)
            session.commit()
            return {"id": str(palm.id), "tree_code": palm.tree_code}

    def palm_history(self, palm_id: str, limit: int = 50,
                     status: str | None = None) -> list[dict]:
        with self._db() as session:
            query = (
                select(InspectionLog)
                .where(InspectionLog.palm_tree_id == uuid.UUID(palm_id))
                .order_by(InspectionLog.inspected_at.desc())
                .limit(limit)
            )
            if status:
                query = query.where(InspectionLog.status == InspectionStatus(status))
            return [self._log_dict(log) for log in session.scalars(query).all()]

    def recent_inspections(self, limit: int = 50, status: str | None = None,
                           user: dict | None = None) -> list[dict]:
        with self._db() as session:
            query = select(InspectionLog).join(PalmTree).order_by(
                InspectionLog.inspected_at.desc()
            )
            if user and user["role"] == "farmer":
                query = query.where(PalmTree.owner_id == uuid.UUID(user["id"]))
            if status:
                query = query.where(InspectionLog.status == InspectionStatus(status))
            return [self._log_dict(log) for log in session.scalars(query.limit(limit)).all()]

    @staticmethod
    def _log_dict(log: InspectionLog) -> dict:
        return {
            "id": str(log.id), "palm_tree_id": str(log.palm_tree_id),
            "inspected_by": str(log.inspected_by) if log.inspected_by else None,
            "inspected_at": log.inspected_at.isoformat(),
            "image_url": "",  # photos ride inside detection_details (b64)
            "detected_disease": log.detected_disease,
            "severity": log.severity.value if log.severity else None,
            "confidence": float(log.confidence),
            "status": log.status.value,
            "treatment_recommendation": log.treatment_recommendation,
            "detection_details": log.detection_details or {},
            "created_at": log.created_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Inspection — the full AI pipeline, in-process
    # ------------------------------------------------------------------
    def inspect(self, palm_id: str, image_bytes: bytes, filename: str = "capture.jpg",
                notes: str | None = None, user: dict | None = None) -> dict:
        from backend.services.vision.preprocessing import encode_jpeg, resize_max_side
        from backend.services.vision.results import InferenceError

        with self._db() as session:
            palm = session.get(PalmTree, uuid.UUID(palm_id))
            if palm is None:
                raise CloudAuthError("Palm tree not found.")

            context_bits = [f"tree code {palm.tree_code}"]
            if palm.variety:
                context_bits.append(f"variety {palm.variety}")
            if palm.field_name:
                context_bits.append(f"field '{palm.field_name}'")

            try:
                diagnosis = asyncio.run(
                    self._vision.analyze(image_bytes, filename=filename,
                                         context_note="; ".join(context_bits))
                )
            except InferenceError as exc:
                raise CloudAuthError(
                    "The AI engine is temporarily unavailable (provider "
                    "quota or connectivity). Please retry in a few minutes."
                ) from exc

            # Store a compact copy (max 1024 px) — the full-resolution
            # original never needs to round-trip through the database.
            try:
                compact = encode_jpeg(resize_max_side(
                    decode_image(image_bytes), max_side=1024
                ))
            except Exception:  # noqa: BLE001 - embedding is best-effort
                compact = image_bytes

            details = {
                "model": diagnosis.model, "provider": diagnosis.provider,
                "latency_ms": diagnosis.latency_ms,
                "symptoms": diagnosis.symptoms,
                "assessment": diagnosis.assessment,
                "image_quality": diagnosis.quality.model_dump(),
                "warnings": list(diagnosis.warnings),
                "notes": notes,
                # Cloud mode: filesystems are ephemeral — embed the photo.
                "image_b64": base64.b64encode(compact).decode("ascii"),
            }
            log = InspectionLog(
                palm_tree_id=palm.id,
                inspected_by=uuid.UUID(user["id"]) if user else None,
                inspected_at=datetime.now(UTC),
                image_path=f"embedded://{filename}",
                detected_disease=diagnosis.detected_disease,
                severity=diagnosis.severity,
                confidence=Decimal(str(diagnosis.confidence)),
                status=diagnosis.status,
                treatment_recommendation="\n".join(diagnosis.treatment_steps) or None,
                detection_details=details,
            )
            session.add(log)
            session.commit()

            return {
                "diagnosis": diagnosis.model_dump(),
                "inspection": self._log_dict(log),
            }

    def get_image_bytes(self, image_url: str, log: dict | None = None) -> bytes:
        """Photos are embedded in detection_details in cloud mode."""
        details = (log or {}).get("detection_details") or {}
        b64 = details.get("image_b64")
        if b64:
            return base64.b64decode(b64)
        raise RuntimeError("stored photo unavailable")

    def vision_status(self) -> dict:
        status = asyncio.run(self._vision.provider_status())
        return status
