from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from config import settings
from utils import debug

from .jobs_dataset import load_jobs
from .learning_rag import _item_text, load_learning_resources


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_jobs_path() -> Path:
    return _project_root() / "data" / "jobs.jsonl"


def _default_learning_path() -> Path:
    return _project_root() / "data" / "learning_resources.jsonl"


def _meta_path() -> Path:
    raw = (settings.QDRANT_INDEX_META_PATH or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (_project_root() / p)
    return _project_root() / "data" / ".qdrant_index_meta.json"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_meta() -> dict[str, Any]:
    p = _meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_meta(meta: dict[str, Any]) -> None:
    p = _meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _docker_compose_up_qdrant() -> bool:
    if not settings.QDRANT_AUTO_START:
        return False

    cmds = [
        ["docker", "compose", "up", "-d", "qdrant"],
        ["docker-compose", "up", "-d", "qdrant"],
    ]
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_project_root()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=40,
                check=False,
            )
            if proc.returncode == 0:
                debug(f"qdrant auto-start succeeded via: {' '.join(cmd)}", "QDRANT")
                return True
        except Exception:
            continue
    return False


def _qdrant_client():
    try:
        from qdrant_client import QdrantClient
    except Exception:
        return None
    return QdrantClient(url=settings.QDRANT_URL, timeout=settings.QDRANT_TIMEOUT_SECONDS)


def qdrant_enabled() -> bool:
    return bool(settings.QDRANT_ENABLED)


def ensure_qdrant_ready() -> bool:
    if not qdrant_enabled():
        return False

    client = _qdrant_client()
    if client is None:
        debug("qdrant-client not installed", "QDRANT")
        return False

    def _healthy() -> bool:
        try:
            client.get_collections()
            return True
        except Exception:
            return False

    if _healthy():
        return True

    started = _docker_compose_up_qdrant()
    if not started:
        return False

    for _ in range(max(1, settings.QDRANT_READY_RETRIES)):
        if _healthy():
            return True
        time.sleep(max(0.2, settings.QDRANT_READY_SLEEP_SECONDS))
    return False


def _collection_exists(client: Any, name: str) -> bool:
    try:
        coll = client.get_collection(name)
        return bool(coll)
    except Exception:
        return False


def _ensure_collection(client: Any, *, name: str, vector_size: int) -> bool:
    try:
        from qdrant_client.http import models
    except Exception:
        return False

    if _collection_exists(client, name):
        if not settings.QDRANT_RECREATE_COLLECTIONS:
            return True
        client.delete_collection(collection_name=name)

    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(
            size=int(vector_size),
            distance=models.Distance.COSINE,
        ),
    )
    return True


def _jobs_text(job: dict[str, Any]) -> str:
    return (
        f"{job.get('title','')}\n"
        f"{job.get('description','')}\n"
        f"Skills: {', '.join(job.get('skills_required', []) or [])}"
    )


def ensure_jobs_indexed(embed_fn: Callable[[str], list[float]] | None) -> bool:
    if not qdrant_enabled() or embed_fn is None:
        return False
    if not ensure_qdrant_ready():
        return False

    client = _qdrant_client()
    if client is None:
        return False

    jobs_path = _default_jobs_path()
    jobs = load_jobs(str(jobs_path))
    if not jobs:
        return False

    data_hash = _file_sha256(jobs_path)
    model_name = settings.OPENAI_EMBEDDING_MODEL
    meta = _load_meta()
    jobs_meta = meta.get("jobs_index") or {}

    # Skip re-index when source hash/model are unchanged.
    if (
        jobs_meta.get("file_hash") == data_hash
        and jobs_meta.get("model") == model_name
        and jobs_meta.get("count") == len(jobs)
        and _collection_exists(client, settings.QDRANT_COLLECTION_JOBS)
    ):
        return True

    texts = [_jobs_text(j) for j in jobs]
    vectors = [embed_fn(t) for t in texts]
    vector_size = len(vectors[0]) if vectors and vectors[0] else 0
    if vector_size <= 0:
        return False

    _ensure_collection(client, name=settings.QDRANT_COLLECTION_JOBS, vector_size=vector_size)

    try:
        from qdrant_client.http import models
    except Exception:
        return False

    points = []
    for i, (job, vec) in enumerate(zip(jobs, vectors), 1):
        payload = dict(job)
        payload["_source"] = "jobs"
        points.append(models.PointStruct(id=i, vector=vec, payload=payload))

    client.upsert(collection_name=settings.QDRANT_COLLECTION_JOBS, points=points)

    meta["jobs_index"] = {
        "file": str(jobs_path),
        "file_hash": data_hash,
        "model": model_name,
        "count": len(jobs),
        "updated_at": int(time.time()),
    }
    _save_meta(meta)
    return True


def ensure_learning_indexed(
    embed_fn: Callable[[str], list[float]] | None,
    *,
    dataset_path: str | None = None,
) -> bool:
    if not qdrant_enabled() or embed_fn is None:
        return False
    if not ensure_qdrant_ready():
        return False

    client = _qdrant_client()
    if client is None:
        return False

    path = Path(dataset_path).resolve() if dataset_path else _default_learning_path()
    rows = load_learning_resources(path)
    if not rows:
        return False

    data_hash = _file_sha256(path)
    model_name = settings.OPENAI_EMBEDDING_MODEL
    meta = _load_meta()
    rag_meta = meta.get("learning_index") or {}
    if (
        rag_meta.get("file_hash") == data_hash
        and rag_meta.get("model") == model_name
        and rag_meta.get("count") == len(rows)
        and _collection_exists(client, settings.QDRANT_COLLECTION_LEARNING)
    ):
        return True

    texts = [_item_text(r) for r in rows]
    vectors = [embed_fn(t) for t in texts]
    vector_size = len(vectors[0]) if vectors and vectors[0] else 0
    if vector_size <= 0:
        return False

    _ensure_collection(client, name=settings.QDRANT_COLLECTION_LEARNING, vector_size=vector_size)

    try:
        from qdrant_client.http import models
    except Exception:
        return False

    points = []
    for i, (row, vec) in enumerate(zip(rows, vectors), 1):
        payload = dict(row)
        payload["_source"] = "learning_resources"
        points.append(models.PointStruct(id=i, vector=vec, payload=payload))

    client.upsert(collection_name=settings.QDRANT_COLLECTION_LEARNING, points=points)

    meta["learning_index"] = {
        "file": str(path),
        "file_hash": data_hash,
        "model": model_name,
        "count": len(rows),
        "updated_at": int(time.time()),
    }
    _save_meta(meta)
    return True


def search_jobs(
    *,
    query: str,
    top_k: int,
    embed_fn: Callable[[str], list[float]] | None,
) -> list[dict[str, Any]]:
    if not qdrant_enabled() or embed_fn is None:
        return []
    if not ensure_jobs_indexed(embed_fn):
        debug("jobs index not ready; skipping Qdrant search", "QDRANT")
        return []

    client = _qdrant_client()
    if client is None:
        debug("qdrant-client unavailable; skipping Qdrant search", "QDRANT")
        return []
    qv = embed_fn(query)
    # qdrant-client 2.x: use query_points; .search() was removed.
    resp = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_JOBS,
        query=qv,
        limit=max(1, int(top_k)),
        with_payload=True,
    )
    out: list[dict[str, Any]] = []
    for h in resp.points or []:
        payload = dict(h.payload or {})
        payload["score"] = float(h.score)
        payload["score_method"] = "qdrant_cosine"
        out.append(payload)
    return out


def search_learning_resources(
    *,
    query: str,
    top_k: int,
    embed_fn: Callable[[str], list[float]] | None,
    dataset_path: str | None = None,
) -> list[dict[str, Any]]:
    if not qdrant_enabled() or embed_fn is None:
        return []
    if not ensure_learning_indexed(embed_fn, dataset_path=dataset_path):
        debug("learning index not ready; skipping Qdrant search", "QDRANT")
        return []

    client = _qdrant_client()
    if client is None:
        debug("qdrant-client unavailable; skipping Qdrant search", "QDRANT")
        return []
    qv = embed_fn(query)
    resp = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_LEARNING,
        query=qv,
        limit=max(1, int(top_k)),
        with_payload=True,
    )
    out: list[dict[str, Any]] = []
    for h in resp.points or []:
        payload = dict(h.payload or {})
        payload["score"] = float(h.score)
        payload["score_method"] = "qdrant_cosine"
        out.append(payload)
    return out


def warmup_qdrant_indexes(embed_fn: Callable[[str], list[float]] | None) -> None:
    """
    Best-effort warmup to avoid first-request indexing latency.
    """
    if not qdrant_enabled() or embed_fn is None:
        return
    try:
        ensure_jobs_indexed(embed_fn)
    except Exception as e:
        debug(f"jobs index warmup skipped: {e}", "QDRANT")

    try:
        override_path = (os.getenv("LEARNING_RESOURCES_PATH") or "").strip() or None
        ensure_learning_indexed(embed_fn, dataset_path=override_path)
    except Exception as e:
        debug(f"learning index warmup skipped: {e}", "QDRANT")
