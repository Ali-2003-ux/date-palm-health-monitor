"""User model — accounts and role-based access control."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from backend.db.base import Base, enum_values


class UserRole(str, enum.Enum):
    """Application roles, from least to most privileged."""

    FARMER = "farmer"
    AGRONOMIST = "agronomist"
    ADMIN = "admin"


class User(Base):
    """A registered account: farmer, agronomist or platform admin."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=enum_values),
        default=UserRole.FARMER,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        """Store emails lower-cased so uniqueness is case-insensitive."""
        return value.strip().lower()

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
