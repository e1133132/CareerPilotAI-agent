from __future__ import annotations

import pytest

from config import settings


@pytest.fixture(autouse=True)
def _disable_langgraph_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration tests mock the legacy orchestrator path; keep LangGraph off."""
    monkeypatch.setattr(settings, "USE_LANGGRAPH_PIPELINE", False)
