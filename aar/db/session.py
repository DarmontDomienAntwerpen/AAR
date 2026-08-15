"""SQLAlchemy engine/session plumbing.

Deliberately framework-agnostic: every function accepts an optional explicit
`engine`, so tests can pass an isolated in-memory SQLite engine instead of
touching the process-wide singleton used by the running Streamlit app. This
keeps the test suite free of shared/global database state.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from aar.config.settings import get_settings

_engine: Engine | None = None


class Base(DeclarativeBase):
    pass


def get_engine(db_url: str | None = None, echo: bool = False) -> Engine:
    """Return an engine. With no args, returns the lazily-created process-wide
    singleton bound to the configured SQLite file. Pass `db_url` to get an
    independent engine (used by tests)."""
    global _engine
    if db_url is not None:
        return create_engine(db_url, echo=echo, connect_args={"check_same_thread": False})
    if _engine is None:
        settings = get_settings()
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            settings.db_url, echo=echo, connect_args={"check_same_thread": False}
        )
    return _engine


def init_db(engine: Engine | None = None) -> None:
    """Create all tables that don't exist yet. Safe to call repeatedly."""
    import aar.models  # noqa: F401  (registers all model classes on Base.metadata)

    engine = engine or get_engine()
    Base.metadata.create_all(engine)


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False, autoflush=False)


def get_session(engine: Engine | None = None) -> Session:
    return get_sessionmaker(engine)()


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Context manager: commits on success, rolls back and re-raises on error."""
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
