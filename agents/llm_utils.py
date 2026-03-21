from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from config import settings

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

    client = OpenAI()

    def embed(text: str) -> list[float]:
        resp = client.embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=text)
        return resp.data[0].embedding

    return embed

