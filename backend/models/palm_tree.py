"""PalmTree model — registered date palms with GPS tagging."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, JSONVariant

if TYPE_CHECKING:
    from backend.models.inspection_log import InspectionLog
    from backend.models.user import User


class PalmTree(Base):
    """A single registered date palm, GPS-tagged and owned by a user."""

    __tablename__ = "palm_trees"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tree_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    field_name: Mapped[str | None] = mapped_column(String(120), index=True)
    variety: Mapped[str | None] = mapped_column(String(80))
    location_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    planted_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship()
    inspections: Mapped[list[InspectionLog]] = relationship(
        back_populates="palm_tree", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<PalmTree code={self.tree_code!r} "
            f"lat={self.latitude} lng={self.longitude}>"
        )
