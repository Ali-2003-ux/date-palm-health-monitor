"""Palm tree schemas (registration + responses)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Latitude = Annotated[Decimal, Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180, max_digits=9, decimal_places=6)]


class PalmTreeCreate(BaseModel):
    """GPS-tagged palm registration."""

    tree_code: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
    latitude: Latitude
    longitude: Longitude
    field_name: str | None = Field(default=None, max_length=120)
    variety: str | None = Field(default=None, max_length=80)
    planted_on: date | None = None
    location_metadata: dict[str, Any] | None = None

    @field_validator("planted_on")
    @classmethod
    def _not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("planted_on cannot be in the future")
        return value


class PalmTreeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    tree_code: str
    latitude: Decimal
    longitude: Decimal
    field_name: str | None
    variety: str | None
    planted_on: date | None
    location_metadata: dict[str, Any] | None
    created_at: datetime


class PalmTreeReadWithStats(PalmTreeRead):
    """Palm plus its latest inspection verdict (for the dashboard list)."""

    total_inspections: int = 0
    latest_status: str | None = None
    latest_disease: str | None = None
