from __future__ import annotations

import os

from observability.tracing import configure_langsmith_env


def test_configure_langsmith_env_prefers_langsmith_vars(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-project")

    status = configure_langsmith_env()

    assert status["langsmith_enabled"] is True
    assert status["langsmith_project"] == "test-project"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_test_key"


def test_configure_langsmith_env_legacy_fallback(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_legacy_key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "legacy-project")

    status = configure_langsmith_env()

    assert status["langsmith_enabled"] is True
    assert status["langsmith_project"] == "legacy-project"


def test_configure_langsmith_env_disabled_without_key(monkeypatch) -> None:
    from config import settings

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setattr(settings, "LANGSMITH_API_KEY", "")

    status = configure_langsmith_env()

    assert status["langsmith_enabled"] is False
