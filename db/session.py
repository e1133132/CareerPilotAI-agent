from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def database_enabled() -> bool:
    return bool((settings.DATABASE_URL or "").strip())


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = (settings.DATABASE_URL or "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("mysql"):
            kwargs["connect_args"] = {"charset": "utf8mb4"}
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def reset_database_engine() -> None:
    """Dispose engine (for tests or config changes)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_database() -> None:
    if not database_enabled():
        return
    from db.models import Base

    Base.metadata.create_all(bind=get_engine())


@contextmanager
def db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
