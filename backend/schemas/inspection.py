"""Inspection schemas — API shape of AI diagnosis results."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from backend.models import InspectionStatus, Severity
from backend.services.vision.results import DiagnosisResult


class InspectionRead(BaseModel):
    """A persisted inspection log row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    palm_tree_id: UUID
    inspected_by: UUID | None
    inspected_at: datetime
    image_url: str
    detected_disease: str | None
    severity: Severity | None
    confidence: float
    status: InspectionStatus
    treatment_recommendation: str | None
    detection_details: dict[str, Any] | None
    created_at: datetime

    @field_validator("confidence", mode="before")
    @classmethod
    def _decimal_to_float(cls, value: object) -> object:
        return float(value) if isinstance(value, Decimal) else value


class InspectResponse(BaseModel):
    """Result of POST /inspect: the AI diagnosis plus the saved record."""

    diagnosis: DiagnosisResult
    inspection: InspectionRead
