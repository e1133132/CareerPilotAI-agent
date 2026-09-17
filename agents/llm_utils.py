from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable

from config import settings
from observability.tracing import maybe_wrap_openai

logger = logging.getLogger(__name__)


def safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def extract_json_block(text: str) -> str | None:
    m = re.search(r"```json\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\{[\s\S]*\})", text)
    if m:
        return m.group(1).strip()
    return None


def create_chat_openai(agent_name: str, **kwargs: Any) -> Any:
    """ChatOpenAI with observability callbacks (token usage + LangSmith when enabled)."""
    from langchain_openai import ChatOpenAI

    from observability.callbacks import get_llm_callbacks

    extra_callbacks = list(kwargs.pop("callbacks", None) or [])
    callbacks = get_llm_callbacks(agent_name) + extra_callbacks
    return ChatOpenAI(**kwargs, callbacks=callbacks)


def get_embed_fn() -> Callable[[str], list[float]] | None:
    """
    Returns a callable that embeds text via OpenAI if API key exists, otherwise None.
    """
    if not (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        return None
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    client = maybe_wrap_openai(OpenAI())

    def embed(text: str) -> list[float]:
        start = time.perf_counter()
        try:
            resp = client.embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=text)
            from observability.metrics import metrics_store

            usage = getattr(resp, "usage", None)
            total = int(getattr(usage, "total_tokens", 0) or 0) if usage else 0
            metrics_store.record_llm_usage(
                agent="embedding",
                model=settings.OPENAI_EMBEDDING_MODEL,
                prompt_tokens=total,
                completion_tokens=0,
                total_tokens=total,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            return resp.data[0].embedding
        except Exception as exc:
            from observability.metrics import metrics_store

            metrics_store.record_llm_usage(
                agent="embedding",
                model=settings.OPENAI_EMBEDDING_MODEL,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                error=True,
            )
            logger.warning("embedding_failed error=%s", exc)
            raise

    return embed

