from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        ax = float(a[i])
        bx = float(b[i])
        dot += ax * bx
        na += ax * ax
        nb += bx * bx
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0
    return dot / denom


def _keyword_score(query: str, text: str) -> float:
    q = set(query.lower().split())
    t = text.lower()
    if not q:
        return 0.0
    hits = sum(1 for w in q if len(w) > 2 and w in t)
    return hits / max(1, len([w for w in q if len(w) > 2]))


def load_learning_resources(dataset_path: str | Path) -> list[dict[str, Any]]:
    p = Path(dataset_path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _item_text(item: dict[str, Any]) -> str:
    skills = item.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    sk = ", ".join(str(s) for s in skills)
    title = str(item.get("title") or "")
    content = str(item.get("content") or "")
    hints = item.get("resource_hints") or []
    if isinstance(hints, str):
        hints = [hints]
    h = ", ".join(str(x) for x in hints)
    return f"{title}\n{content}\nSkills: {sk}\nHints: {h}"


def build_study_rag_query(profile: dict[str, Any], gaps: dict[str, Any]) -> str:
    headline = str(profile.get("headline") or "").strip()
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    skill_str = ", ".join(str(s) for s in skills[:30])

    missing = gaps.get("missing_skills") or []
    miss_list: list[str] = []
    for m in missing:
        if isinstance(m, dict) and m.get("skill"):
            miss_list.append(str(m["skill"]))
        elif isinstance(m, str):
            miss_list.append(m)

    tj = gaps.get("target_job") or {}
    role = str(tj.get("title") or "").strip()

    parts = [headline, role, "Skills:", skill_str, "Gaps:", ", ".join(miss_list[:20])]
    q = " ".join(p for p in parts if p and p != "Skills:" and p != "Gaps:").strip()
    if not q:
        q = "career skills learning roadmap"
    return q


def retrieve_learning_context(
    *,
    query: str,
    resources: list[dict[str, Any]],
    embed_fn: Any,
    top_k: int = 5,
    dataset_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve top-k learning resource snippets by embedding similarity, else keyword overlap.
    Each item should have at least: id, title, content; optional skills, resource_hints.
    """
    top_k = max(1, int(top_k))
    if not resources:
        return []

    # Prefer Qdrant persisted vector search when available.
    try:
        from .vector_store_qdrant import search_learning_resources

        qdrant_hits = search_learning_resources(
            query=query,
            top_k=top_k,
            embed_fn=embed_fn,
            dataset_path=dataset_path,
        )
        if qdrant_hits:
            return qdrant_hits
    except Exception as e:
        import warnings

        warnings.warn(f"Qdrant learning search failed, using local embedding path: {e}", stacklevel=1)

    if embed_fn is None:
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in resources:
            text = _item_text(item)
            s = _keyword_score(query, text)
            scored.append((float(s), item))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, item in scored[:top_k]:
            row = {**item, "score": s, "score_method": "keyword"}
            out.append(row)
        return out

    try:
        qv = [float(x) for x in (embed_fn(query) or [])]
        scored = []
        for item in resources:
            text = _item_text(item)
            jv = [float(x) for x in (embed_fn(text) or [])]
            scored.append((_cosine(qv, jv), item))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, item in scored[:top_k]:
            row = {**item, "score": float(s), "score_method": "embedding_cosine"}
            out.append(row)
        return out
    except Exception:
        scored = []
        for item in resources:
            text = _item_text(item)
            s = _keyword_score(query, text)
            scored.append((float(s), item))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, item in scored[:top_k]:
            row = {**item, "score": float(s), "score_method": "keyword_fallback"}
            out.append(row)
        return out


def format_rag_context_for_prompt(snippets: list[dict[str, Any]]) -> str:
    if not snippets:
        return "(No external learning snippets retrieved; rely on candidate profile and skill gaps.)"

    blocks: list[str] = []
    for i, s in enumerate(snippets, 1):
        sid = s.get("id", f"snippet-{i}")
        title = s.get("title") or ""
        skills = s.get("skills") or []
        if isinstance(skills, str):
            skills = [skills]
        hints = s.get("resource_hints") or []
        if isinstance(hints, str):
            hints = [hints]
        content = (s.get("content") or "").strip()
        hint_line = ", ".join(str(h) for h in hints) if hints else ""
        blocks.append(
            f"--- Snippet [{i}] id={sid} score={s.get('score', 0):.4f} ({s.get('score_method', '')}) ---\n"
            f"Title: {title}\n"
            f"Related skills: {', '.join(str(x) for x in skills)}\n"
            f"Content:\n{content}\n"
            f"Suggested resource types / hints: {hint_line}"
        )
    return "\n\n".join(blocks)
