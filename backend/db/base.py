"""Declarative base and shared model conventions.

Every ORM model inherits from `Base`. The naming convention gives all
constraints deterministic names, which keeps Alembic auto-generated
migrations stable across runs.
"""

import enum

from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

#: Portable JSON that upgrades to JSONB (indexable) on PostgreSQL.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def enum_values(enums: type[enum.Enum]) -> list[str]:
    """`values_callable` for Enum columns: store `.value` strings (e.g. "farmer")."""
    return [member.value for member in enums]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
