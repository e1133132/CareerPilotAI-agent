from __future__ import annotations

import pytest

from config import settings
from db import init_database, reset_database_engine


@pytest.fixture
def sql_db(tmp_path, monkeypatch):
    """SQLite file DB for unit tests (same SQLAlchemy code path as MySQL)."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    reset_database_engine()
    init_database()
    yield db_path
    reset_database_engine()
