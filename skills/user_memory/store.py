from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from db.session import database_enabled, db_session


def _memory_dir() -> Path:
    path = Path(settings.USER_MEMORY_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def derive_user_id(
    *,
    client_id: str | None = None,
    resume_text: str | None = None,
    account_user_id: str | None = None,
) -> str:
    """Resolve memory key: logged-in account id takes precedence."""
    if account_user_id and str(account_user_id).strip():
        return str(account_user_id).strip()[:64]
    if client_id and client_id.strip():
        safe = client_id.strip()[:120]
        return hashlib.sha256(safe.encode("utf-8")).hexdigest()[:16]
    text = (resume_text or "").strip()[:2000]
    if not text:
        return "anonymous"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _empty_memory(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "preferred_target_roles": [],
        "rejected_job_ids": [],
        "saved_job_ids": [],
        "run_history": [],
        "updated_at": None,
    }


def _memory_path(user_id: str) -> Path:
    safe = "".join(c for c in user_id if c.isalnum() or c in ("-", "_"))[:64] or "anonymous"
    return _memory_dir() / f"{safe}.json"


def load_user_memory(user_id: str) -> dict[str, Any]:
    if database_enabled():
        return _load_user_memory_db(user_id)
    return _load_user_memory_json(user_id)


def _load_user_memory_json(user_id: str) -> dict[str, Any]:
    path = _memory_path(user_id)
    if not path.exists():
        return _empty_memory(user_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("user_id", user_id)
            return data
    except Exception:
        pass
    return _empty_memory(user_id)


def _load_user_memory_db(user_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from db.models import UserMemoryRow

    with db_session() as session:
        row = session.execute(select(UserMemoryRow).where(UserMemoryRow.user_id == user_id)).scalar_one_or_none()
        if not row:
            return _empty_memory(user_id)
        return {
            "user_id": row.user_id,
            "preferred_target_roles": list(row.preferred_target_roles or []),
            "rejected_job_ids": list(row.rejected_job_ids or []),
            "saved_job_ids": list(row.saved_job_ids or []),
            "run_history": list(row.run_history or []),
            "updated_at": row.updated_at.isoformat().replace("+00:00", "Z") if row.updated_at else None,
        }


def save_user_memory(record: dict[str, Any]) -> dict[str, Any]:
    if database_enabled():
        return _save_user_memory_db(record)
    return _save_user_memory_json(record)


def _save_user_memory_json(record: dict[str, Any]) -> dict[str, Any]:
    user_id = str(record.get("user_id") or "anonymous")
    record = dict(record)
    record["user_id"] = user_id
    record["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = _memory_path(user_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _save_user_memory_db(record: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import select

    from db.models import UserMemoryRow

    user_id = str(record.get("user_id") or "anonymous")
    now = datetime.now(timezone.utc)
    payload = {
        "preferred_target_roles": list(record.get("preferred_target_roles") or []),
        "rejected_job_ids": list(record.get("rejected_job_ids") or []),
        "saved_job_ids": list(record.get("saved_job_ids") or []),
        "run_history": list(record.get("run_history") or []),
    }
    with db_session() as session:
        row = session.execute(select(UserMemoryRow).where(UserMemoryRow.user_id == user_id)).scalar_one_or_none()
        if row is None:
            row = UserMemoryRow(user_id=user_id, **payload, updated_at=now)
            session.add(row)
        else:
            row.preferred_target_roles = payload["preferred_target_roles"]
            row.rejected_job_ids = payload["rejected_job_ids"]
            row.saved_job_ids = payload["saved_job_ids"]
            row.run_history = payload["run_history"]
            row.updated_at = now
    saved = _empty_memory(user_id)
    saved.update(payload)
    saved["updated_at"] = now.isoformat().replace("+00:00", "Z")
    return saved


def merge_run_into_memory(
    memory: dict[str, Any],
    *,
    run_id: str,
    target_roles: list[str] | None,
    job_matches: list[dict[str, Any]],
    session_memory: dict[str, Any] | None,
    apply_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update long-term memory after a completed run."""
    mem = dict(memory)
    mem.setdefault("preferred_target_roles", [])
    mem.setdefault("rejected_job_ids", [])
    mem.setdefault("saved_job_ids", [])
    mem.setdefault("run_history", [])

    for role in target_roles or []:
        r = str(role).strip()
        if r and r not in mem["preferred_target_roles"]:
            mem["preferred_target_roles"].append(r)

    selected_id = str((session_memory or {}).get("selected_job_id") or "")
    top_id = str(job_matches[0].get("id") or "") if job_matches else ""
    mem["run_history"].append(
        {
            "run_id": run_id,
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "selected_job_id": selected_id or top_id,
            "top_job_id": top_id,
            "apply_top_priority": (
                (apply_strategy or {}).get("priority_applications") or [{}]
            )[0].get("job_id")
            if apply_strategy
            else None,
        }
    )
    mem["run_history"] = mem["run_history"][-settings.USER_MEMORY_MAX_RUN_HISTORY :]
    return mem


def filter_jobs_by_memory(jobs: list[dict[str, Any]], memory: dict[str, Any]) -> list[dict[str, Any]]:
    """Deprioritize (not remove) jobs the user previously rejected."""
    rejected = {str(x) for x in (memory.get("rejected_job_ids") or [])}
    if not rejected:
        return jobs
    kept = [j for j in jobs if str(j.get("id") or "") not in rejected]
    demoted = [j for j in jobs if str(j.get("id") or "") in rejected]
    return kept + demoted
