"""
Fetch public job listings from the web via LangChain DuckDuckGo search adapter (service layer).

Normalized to the same schema as jobs.jsonl for merge + rank with internal corpus.
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
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append({"title": line[:160], "snippet": line, "link": ""})
        return rows
    return []


def _infer_skills_from_text(text: str) -> list[str]:
    known = [
        "Python", "SQL", "JavaScript", "TypeScript", "React", "Java", "AWS", "Docker",
        "Kubernetes", "Machine learning", "Excel", "Communication", "Git", "APIs",
        "Linux", "Testing", "Agile", "Statistics", "Tableau", "Power BI",
    ]
    lower = text.lower()
    found = [s for s in known if s.lower() in lower]
    return found[:8] or ["Communication", "Problem solving"]


def normalize_web_job_hit(hit: dict[str, Any], *, index: int = 0) -> dict[str, Any] | None:
    title = str(hit.get("title") or hit.get("name") or "").strip()
    url = str(hit.get("link") or hit.get("url") or hit.get("href") or "").strip()
    snippet = str(hit.get("snippet") or hit.get("body") or hit.get("content") or "").strip()
    if not title and not snippet:
        return None
    if not title:
        title = snippet[:100] + ("…" if len(snippet) > 100 else "")

    seed = url or title
    skills = _infer_skills_from_text(f"{title} {snippet}")
    company = "External (web)"
    for sep in (" at ", " @ ", " | "):
        if sep in title:
            parts = title.split(sep, 1)
            if len(parts) == 2 and len(parts[1].strip()) < 80:
                company = parts[1].strip()
                break

    desc_parts = [snippet] if snippet else [title]
    if url:
        desc_parts.append(f"Listing URL: {url}")
    description = "\n".join(desc_parts).strip()

    return {
        "id": _slug_id("web-job", seed or f"idx-{index}"),
        "title": title,
        "company": company,
        "description": description,
        "skills_required": skills,
        "source": "web",
        "url": url or None,
    }


def _build_job_search_query(query: str, target_roles: list[str] | None) -> str:
    roles = ", ".join(str(r) for r in (target_roles or [])[:3])
    base = (query or roles or "entry level jobs").strip()
    if roles and roles.lower() not in base.lower():
        base = f"{base} {roles}"
    return f"{base} job opening hiring careers"


def fetch_web_job_listings(
    query: str,
    *,
    target_roles: list[str] | None = None,
    max_results: int | None = None,
) -> list[dict[str, Any]]:
    if not settings.JOB_WEB_SEARCH_ENABLED:
        return []

    limit = max_results if max_results is not None else settings.JOB_WEB_SEARCH_MAX_RESULTS
    limit = max(1, min(int(limit), 10))

    try:
        from langchain_community.tools import DuckDuckGoSearchResults
    except ModuleNotFoundError:
        warnings.warn(
            "JOB_WEB_SEARCH_ENABLED but langchain-community is not installed; skipping web jobs.",
            stacklevel=1,
        )
        return []

    search_query = _build_job_search_query(query, target_roles)
    try:
        search_client = DuckDuckGoSearchResults(num_results=limit, output_format="list")
        raw = search_client.invoke(search_query)
    except Exception as exc:
        warnings.warn(f"Web job search failed ({exc}); using internal corpus only.", stacklevel=1)
        return []

    hits = _parse_search_results(raw)
    out: list[dict[str, Any]] = []
    for i, hit in enumerate(hits[:limit]):
        row = normalize_web_job_hit(hit, index=i)
        if row:
            out.append(row)
    return out


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower()).strip()


def merge_job_listings(
    internal_jobs: list[dict[str, Any]],
    web_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge internal (company) jobs with web listings; internal rows keep priority order."""
    merged: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    def _append(item: dict[str, Any]) -> None:
        key = _norm_title(str(item.get("title") or ""))
        if not key or key in seen_titles:
            return
        seen_titles.add(key)
        row = dict(item)
        row.setdefault("source", "internal")
        merged.append(row)

    for row in internal_jobs:
        internal = dict(row)
        internal.setdefault("source", "internal")
        internal.setdefault("company", settings.INTERNAL_COMPANY_NAME)
        _append(internal)
    for row in web_jobs:
        _append(dict(row))
    return merged
