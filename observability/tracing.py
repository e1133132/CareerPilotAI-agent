from __future__ import annotations

import logging
import os
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def configure_langsmith_env() -> dict[str, str | bool]:
    """
    Apply LangSmith tracing env vars for LangChain / LangGraph (see langsmith-trace skill).

    Preferred: LANGSMITH_TRACING + LANGSMITH_API_KEY + LANGSMITH_PROJECT
    Legacy fallbacks: LANGCHAIN_TRACING_V2 + LANGCHAIN_API_KEY + LANGCHAIN_PROJECT
    """
    tracing_on = _truthy(os.getenv("LANGSMITH_TRACING")) or _truthy(os.getenv("LANGCHAIN_TRACING_V2"))

    api_key = (
        (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or settings.LANGSMITH_API_KEY or "")
        .strip()
    )
    project = (
        os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or settings.LANGSMITH_PROJECT
        or "careerpilot-ai"
    )

    if tracing_on and api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_API_KEY"] = api_key
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGCHAIN_PROJECT"] = project
    else:
        tracing_on = False

    # Serverless / Cloud Run: flush traces before the request handler returns.
    if settings.LANGCHAIN_CALLBACKS_BACKGROUND is False:
        os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"

    workspace_id = (os.getenv("LANGSMITH_WORKSPACE_ID") or settings.LANGSMITH_WORKSPACE_ID or "").strip()
    if workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = workspace_id

    return {
        "langsmith_enabled": tracing_on and bool(api_key),
        "langsmith_project": project if tracing_on and api_key else "",
        "langsmith_callbacks_background": settings.LANGCHAIN_CALLBACKS_BACKGROUND,
    }


def maybe_wrap_openai(client: Any) -> Any:
    """Wrap a raw OpenAI client so direct API calls appear in LangSmith when tracing is on."""
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:
        return client


def setup_tracing() -> dict[str, str | bool]:
    """Call once at API startup (after load_dotenv)."""
    status = configure_langsmith_env()
    if status["langsmith_enabled"]:
        logger.info(
            "langsmith_tracing_enabled project=%s callbacks_background=%s",
            status["langsmith_project"],
            status["langsmith_callbacks_background"],
        )
    else:
        logger.info("langsmith_tracing_disabled")
    return status
