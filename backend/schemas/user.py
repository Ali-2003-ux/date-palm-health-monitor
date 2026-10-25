"""User and token schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models import UserRole

Password = Annotated[str, Field(min_length=8, max_length=72)]


class UserCreate(BaseModel):
    """Registration payload (role is always FARMER; admins are created
    via scripts/create_admin.py)."""

    email: EmailStr
    password: Password
    full_name: Annotated[str, Field(min_length=2, max_length=120)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
