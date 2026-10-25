"""InspectionLog model — AI inspection results for palm trees."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, JSONVariant, enum_values

if TYPE_CHECKING:
    from backend.models.palm_tree import PalmTree
    from backend.models.user import User


class InspectionStatus(str, enum.Enum):
    """Overall health verdict for one inspection."""

    HEALTHY = "healthy"
    INFECTED = "infected"
    CRITICAL = "critical"


class Severity(str, enum.Enum):
    """Disease severity level reported by the AI inference."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InspectionLog(Base):
    """One AI inspection of a palm: result, confidence and treatment plan.

    Append-only record — corrections are new inspections, never edits.
    """

    __tablename__ = "inspection_logs"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    palm_tree_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("palm_trees.id", ondelete="CASCADE"), index=True
    )
    inspected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    image_path: Mapped[str] = mapped_column(String(512))
    detected_disease: Mapped[str | None] = mapped_column(String(120))
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, name="inspection_severity", values_callable=enum_values)
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspection_status", values_callable=enum_values)
    )
    treatment_recommendation: Mapped[str | None] = mapped_column(Text)
    detection_details: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    palm_tree: Mapped[PalmTree] = relationship(back_populates="inspections")
    inspector: Mapped[User | None] = relationship()

    @property
    def image_url(self) -> str:
        """Public URL of the stored photo (served via the /media mount)."""
        from backend.services.storage import image_url as to_url  # local: avoid cycles

        return to_url(self.image_path)

    def __repr__(self) -> str:
        return (
            f"<InspectionLog palm={self.palm_tree_id} status={self.status.value} "
            f"disease={self.detected_disease!r} confidence={self.confidence}>"
        )
