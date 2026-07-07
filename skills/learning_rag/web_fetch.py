"""
Fetch learning resources from the web via LangChain DuckDuckGo search adapter (service layer).

Results are normalized to the same schema as learning_resources.jsonl so they can
be merged with local rows and passed into retrieve_learning_context (RAG).
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from typing import Any

from config import settings


def _slug_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _infer_resource_hints(url: str, snippet: str) -> list[str]:
    u = (url or "").lower()
    text = f"{u} {snippet}".lower()
    hints: list[str] = []
    if any(x in text for x in ("youtube.com", "youtu.be", "vimeo", "video")):
        hints.append("video")
    if any(x in text for x in ("coursera", "udemy", "edx", "course", "tutorial")):
        hints.append("course")
    if any(x in text for x in ("docs.", "documentation", "readthedocs", "developer.", "mdn")):
        hints.append("documentation")
    if "github.com" in text:
        hints.append("practice")
    if not hints:
        hints.append("web")
    return hints


def normalize_web_search_hit(
    hit: dict[str, Any],
    *,
    gap_skills: list[str] | None = None,
    index: int = 0,
) -> dict[str, Any] | None:
    """Map a LangChain search hit to learning_resources.jsonl row shape."""
    title = str(hit.get("title") or hit.get("name") or "").strip()
    url = str(hit.get("link") or hit.get("url") or hit.get("href") or "").strip()
    snippet = str(hit.get("snippet") or hit.get("body") or hit.get("content") or "").strip()

    if not title and not snippet:
        return None
    if not title:
        title = snippet[:80] + ("…" if len(snippet) > 80 else "")

    seed = url or title
    skills = [str(s).strip() for s in (gap_skills or []) if str(s).strip()][:8]
    content_parts = [snippet]
    if url:
        content_parts.append(f"Source URL: {url}")
    content = "\n".join(p for p in content_parts if p).strip()

    return {
        "id": _slug_id("web", seed or f"idx-{index}"),
        "title": title,
        "skills": skills,
        "content": content,
        "resource_hints": _infer_resource_hints(url, snippet),
        "source": "web",
        "url": url or None,
    }


def _parse_search_results(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass
        # Fallback: "title - snippet" lines
        rows: list[dict[str, Any]] = []
        for i, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            rows.append({"title": line[:120], "snippet": line, "link": ""})
        return rows
    return []


def _build_search_query(rag_query: str, gap_skills: list[str] | None) -> str:
    skills = ", ".join(str(s) for s in (gap_skills or [])[:5])
    base = (rag_query or "").strip() or "career skills learning"
    suffix = " free tutorial course documentation"
    if skills:
        return f"{base} learn {skills}{suffix}"
    return f"{base}{suffix}"


def fetch_web_learning_resources(
    rag_query: str,
    *,
    gap_skills: list[str] | None = None,
    max_results: int | None = None,
) -> list[dict[str, Any]]:
    """
    Use LangChain DuckDuckGoSearchResults to find learning resources on the web.

    Returns normalized rows compatible with learning_resources.jsonl.
    On failure or when disabled, returns [] (caller keeps local jsonl only).
    """
    if not settings.STUDY_PLAN_WEB_SEARCH_ENABLED:
        return []

    limit = max_results if max_results is not None else settings.STUDY_PLAN_WEB_SEARCH_MAX_RESULTS
    limit = max(1, min(int(limit), 10))

    try:
        from langchain_community.tools import DuckDuckGoSearchResults
    except ModuleNotFoundError:
        warnings.warn(
            "STUDY_PLAN_WEB_SEARCH_ENABLED but langchain-community is not installed; skipping web fetch.",
            stacklevel=1,
        )
        return []

    search_query = _build_search_query(rag_query, gap_skills)
    try:
        search_client = DuckDuckGoSearchResults(num_results=limit, output_format="list")
        raw = search_client.invoke(search_query)
    except Exception as exc:
        warnings.warn(f"Web learning search failed ({exc}); using local jsonl only.", stacklevel=1)
        return []

    hits = _parse_search_results(raw)
    out: list[dict[str, Any]] = []
    for i, hit in enumerate(hits[:limit]):
        row = normalize_web_search_hit(hit, gap_skills=gap_skills, index=i)
        if row:
            out.append(row)
    return out


def _norm_key(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower()).strip()


def merge_learning_resources(
    local_rows: list[dict[str, Any]],
    web_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge local jsonl rows with web rows; dedupe by URL then normalized title."""
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    def _append(item: dict[str, Any]) -> None:
        url = str(item.get("url") or "").strip().lower()
        title_key = _norm_key(str(item.get("title") or ""))
        if url:
            if url in seen_urls:
                return
            seen_urls.add(url)
        if title_key:
            if title_key in seen_titles:
                return
            seen_titles.add(title_key)
        merged.append(item)

    for row in local_rows:
        local = dict(row)
        local.setdefault("source", "local")
        _append(local)
    for row in web_rows:
        _append(dict(row))
    return merged
