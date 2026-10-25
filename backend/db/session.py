"""Engine and session management for SQLAlchemy.

`get_db` is the FastAPI dependency; tests override it with a session
bound to an in-memory SQLite engine.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Create the engine lazily from application settings."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            echo=settings.DB_ECHO_LOG,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
        )
        logger.info("Database engine created for %s", settings.POSTGRES_DB)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Session factory bound to the shared engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """Yield a database session; roll back on unhandled errors."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Dispose the engine (called on application shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed")


def reset_for_tests() -> None:
    """Force re-creation of the engine (test isolation helper)."""
    dispose_engine()
