"""Palm tree registry: registration, listing, detail and history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.security import CurrentUser, ensure_palm_access
from backend.db.session import get_db
from backend.models import InspectionLog, InspectionStatus, PalmTree, User, UserRole
from backend.schemas import (
    InspectionRead,
    PalmTreeCreate,
    PalmTreeRead,
    PalmTreeReadWithStats,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/palms", tags=["Palm Trees"])

DbSession = Annotated[Session, Depends(get_db)]


def get_palm_or_404(palm_id: uuid.UUID, db: Session, user: User) -> PalmTree:
    """Fetch a palm and enforce role-based access."""
    palm = db.get(PalmTree, palm_id)
    if palm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Palm tree not found."
        )
    ensure_palm_access(palm.owner_id, user)
    return palm


@router.post(
    "",
    response_model=PalmTreeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new palm tree with GPS tagging",
)
def register_palm(
    payload: PalmTreeCreate, db: DbSession, user: CurrentUser
) -> PalmTree:
    palm = PalmTree(**payload.model_dump(), owner_id=user.id)
    db.add(palm)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tree code '{payload.tree_code}' is already registered.",
        ) from exc
    logger.info(
        "Registered palm %s at (%s, %s) by user %s",
        palm.tree_code,
        palm.latitude,
        palm.longitude,
        user.id,
    )
    return palm


@router.get(
    "",
    response_model=list[PalmTreeReadWithStats],
    summary="List palm trees (own palms for farmers, all for staff)",
)
def list_palms(db: DbSession, user: CurrentUser) -> list[dict]:
    query = select(PalmTree)
    if user.role is UserRole.FARMER:
        query = query.where(PalmTree.owner_id == user.id)
    palms = db.scalars(query.order_by(PalmTree.tree_code)).all()
    if not palms:
        return []
    palm_ids = [palm.id for palm in palms]

    counts = dict(
        db.execute(
            select(InspectionLog.palm_tree_id, func.count())
            .where(InspectionLog.palm_tree_id.in_(palm_ids))
            .group_by(InspectionLog.palm_tree_id)
        ).all()
    )

    # Latest inspection per palm via row_number() — portable across
    # PostgreSQL and SQLite (unlike DISTINCT ON).
    ranked = (
        select(
            InspectionLog.palm_tree_id.label("palm_id"),
            InspectionLog.status.label("status"),
            InspectionLog.detected_disease.label("disease"),
            func.row_number()
            .over(
                partition_by=InspectionLog.palm_tree_id,
                order_by=InspectionLog.inspected_at.desc(),
            )
            .label("rn"),
        )
        .where(InspectionLog.palm_tree_id.in_(palm_ids))
        .subquery()
    )
    latest_rows = db.execute(
        select(ranked.c.palm_id, ranked.c.status, ranked.c.disease).where(
            ranked.c.rn == 1
        )
    ).all()
    latest_by_palm = {row.palm_id: row for row in latest_rows}

    results: list[dict] = []
    for palm in palms:
        latest = latest_by_palm.get(palm.id)
        results.append(
            {
                **PalmTreeRead.model_validate(palm).model_dump(),
                "total_inspections": counts.get(palm.id, 0),
                "latest_status": latest.status.value if latest else None,
                "latest_disease": latest.disease if latest else None,
            }
        )
    return results


@router.get(
    "/{palm_id}",
    response_model=PalmTreeRead,
    summary="Palm tree details",
)
def get_palm(palm_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PalmTree:
    return get_palm_or_404(palm_id, db, user)


@router.get(
    "/{palm_id}/history",
    response_model=list[InspectionRead],
    summary="Historical inspection logs for one tree",
)
def palm_history(
    palm_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    inspection_status: InspectionStatus | None = Query(default=None, alias="status"),
) -> list[InspectionLog]:
    palm = get_palm_or_404(palm_id, db, user)

    query = (
        select(InspectionLog)
        .where(InspectionLog.palm_tree_id == palm.id)
        .order_by(InspectionLog.inspected_at.desc())
        .limit(limit)
    )
    if inspection_status is not None:
        query = query.where(InspectionLog.status == inspection_status)
    return list(db.scalars(query).all())
