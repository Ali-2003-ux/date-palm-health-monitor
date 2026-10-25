"""Alembic migration environment.

The database URL comes from the application settings (`.env`), so the
Alembic CLI and the FastAPI app always target the same database. Override
per-invocation with the DATABASE_URL environment variable, e.g.:

    # apply to another database
    DATABASE_URL=postgresql+psycopg2://user:pass@host/db alembic upgrade head

    # generate SQL script without a server connection
    DATABASE_URL=postgresql+psycopg2://user:pass@host/db alembic upgrade head --sql
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the project root importable regardless of the invocation directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import models  # noqa: F401  (imports register all tables)
from backend.core.config import get_settings
from backend.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `%%` escaping is required — configparser interpolates `%` signs, and
# URL-encoded passwords contain them.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection (`--sql` mode)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
