from __future__ import annotations

from typing import Any

import math


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


def _keyword_score(query: str, job: dict[str, Any]) -> float:
    q = set(query.lower().split())
    text = f"{job.get('title','')} {job.get('description','')}".lower()
    if not q:
        return 0.0
    hits = sum(1 for w in q if w in text)
    return hits / max(1, len(q))


def rank_jobs_semantic(
    *,
    query: str,
    jobs: list[dict[str, Any]],
    embed_fn: Any | None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Ranks jobs by semantic similarity when embeddings are available.
    Falls back to a simple keyword overlap score when embeddings fail/unavailable.
    """
    top_k = max(1, int(top_k))
    if not jobs:
        return []

    # Prefer Qdrant persisted vector search when available.
    try:
        from .vector_store_qdrant import search_jobs as qdrant_search_jobs

        qdrant_hits = qdrant_search_jobs(query=query, top_k=top_k, embed_fn=embed_fn)
        if qdrant_hits:
            return qdrant_hits
    except Exception as e:
        import warnings

        warnings.warn(f"Qdrant job search failed, using local embedding path: {e}", stacklevel=1)

    if embed_fn is None:
        scored = [(float(_keyword_score(query, j)), j) for j in jobs]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {**j, "score": s, "score_method": "keyword"}
            for s, j in scored[:top_k]
        ]

    try:
        qv = [float(x) for x in (embed_fn(query) or [])]
        scored = []
        for j in jobs:
            text = f"{j.get('title','')}\n{j.get('description','')}\nSkills: {', '.join(j.get('skills_required', []) or [])}"
            jv = [float(x) for x in (embed_fn(text) or [])]
            scored.append((_cosine(qv, jv), j))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {**j, "score": float(s), "score_method": "embedding_cosine"}
            for s, j in scored[:top_k]
        ]
    except Exception:
        scored = [(float(_keyword_score(query, j)), j) for j in jobs]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {**j, "score": s, "score_method": "keyword_fallback"}
            for s, j in scored[:top_k]
        ]

