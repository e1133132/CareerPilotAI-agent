from __future__ import annotations

import pytest

from config import settings


@pytest.fixture(autouse=True)
def _integration_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep integration tests unauthenticated and off Cloud SQL unix sockets."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False)
    monkeypatch.setattr(settings, "DATABASE_URL", "")
