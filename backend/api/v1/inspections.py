"""Inspection endpoints: AI image analysis and recent-inspection feed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.security import CurrentUser
from backend.db.session import get_db
from backend.models import InspectionLog, InspectionStatus, PalmTree, UserRole
from backend.schemas import InspectionRead, InspectResponse, VisionStatus
from backend.services.storage import save_palm_image
from backend.services.vision import VisionService
from backend.services.vision.results import DiagnosisResult
from backend.services.vision.service import get_vision_service

logger = get_logger(__name__)
router = APIRouter(tags=["Inspections"])

DbSession = Annotated[Session, Depends(get_db)]
VisionDep = Annotated[VisionService, Depends(get_vision_service)]


def _palm_for_inspection(palm_id: uuid.UUID, db: Session, user) -> PalmTree:
    palm = db.get(PalmTree, palm_id)
    if palm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Palm tree {palm_id} not found.",
        )
    # Farmers inspect only their own trees; agronomists/admins any tree.
    if user.role is UserRole.FARMER and palm.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this palm tree.",
        )
    return palm


@router.post(
    "/inspect",
    response_model=InspectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a palm photo for real-time AI health analysis",
)
async def inspect(
    db: DbSession,
    user: CurrentUser,
    vision: VisionDep,
    image: Annotated[UploadFile, File(description="JPEG/PNG photo of the palm")],
    palm_tree_id: Annotated[uuid.UUID, Form(description="Tree to inspect")],
    captured_at: Annotated[datetime | None, Form(description="Capture time (UTC)")] = None,
    notes: Annotated[str | None, Form(description="Optional field notes")] = None,
) -> InspectResponse:
    settings = get_settings()
    palm = _palm_for_inspection(palm_tree_id, db, user)

    extension = Path(image.filename or "").suffix.lower()
    if extension and extension not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported image type '{extension}'. Allowed: "
                f"{', '.join(sorted(settings.ALLOWED_IMAGE_EXTENSIONS))}"
            ),
        )

    image_bytes = await image.read()

    # VisionService raises InvalidImageError / InferenceError — mapped to
    # HTTP responses by the exception handlers in backend/api/errors.py.
    diagnosis: DiagnosisResult = await vision.analyze(
        image_bytes, filename=image.filename or "upload"
    )

    stored_path = save_palm_image(palm.tree_code, image_bytes)
    log = InspectionLog(
        palm_tree_id=palm.id,
        inspected_by=user.id,
        inspected_at=captured_at or datetime.now(UTC),
        image_path=str(stored_path),
        detected_disease=diagnosis.detected_disease,
        severity=diagnosis.severity,
        confidence=Decimal(str(diagnosis.confidence)),
        status=diagnosis.status,
        treatment_recommendation="\n".join(diagnosis.treatment_steps) or None,
        detection_details={
            "model": diagnosis.model,
            "provider": diagnosis.provider,
            "latency_ms": diagnosis.latency_ms,
            "symptoms": diagnosis.symptoms,
            "assessment": diagnosis.assessment,
            "image_quality": diagnosis.quality.model_dump(),
            "warnings": list(diagnosis.warnings),
            "notes": notes,
        },
    )
    db.add(log)
    db.flush()
    logger.info(
        "Inspection %s recorded for palm %s: %s (%s, %.0f%%)",
        log.id,
        palm.tree_code,
        diagnosis.detected_disease or "healthy",
        diagnosis.status.value,
        diagnosis.confidence * 100,
    )
    return InspectResponse(
        diagnosis=diagnosis, inspection=InspectionRead.model_validate(log)
    )


@router.get(
    "/inspections/recent",
    response_model=list[InspectionRead],
    summary="Most recent inspections across visible palms (dashboard feed)",
)
def recent_inspections(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    inspection_status: InspectionStatus | None = Query(default=None, alias="status"),
) -> list[InspectionLog]:
    query = select(InspectionLog).join(PalmTree).order_by(
        InspectionLog.inspected_at.desc()
    )
    if user.role is UserRole.FARMER:
        query = query.where(PalmTree.owner_id == user.id)
    if inspection_status is not None:
        query = query.where(InspectionLog.status == inspection_status)
    return list(db.scalars(query.limit(limit)).all())


@router.get(
    "/diagnostics/vision",
    response_model=VisionStatus,
    summary="Live health of the AI diagnosis provider",
)
async def vision_diagnostics(
    user: CurrentUser, vision: VisionDep
) -> VisionStatus:
    """Probes the configured provider with a minimal request.

    Any authenticated user may call it — it exposes provider health only,
    never key material. Lets the UI warn before a photo is taken.
    """
    return VisionStatus(**await vision.provider_status())
