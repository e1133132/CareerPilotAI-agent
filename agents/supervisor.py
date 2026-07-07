from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import settings


def _normalize_skill(value: str) -> str:
    return str(value or "").strip().lower()


def resolve_target_job(state: dict[str, Any]) -> dict[str, Any]:
    """Pick the job used for gap analysis from session memory or top match."""
    matches = state.get("job_matches") or []
    if not matches:
        return {}

    session = state.get("session_memory") or {}
    selected_id = str(session.get("selected_job_id") or "").strip()
    if selected_id:
        for job in matches:
            if str(job.get("id") or "") == selected_id:
                return job
    return matches[0]


def build_session_memory(
    *,
    run_id: str,
    target_roles: list[str] | None,
    job_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    top = job_matches[0] if job_matches else {}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "run_id": run_id,
        "target_roles": list(target_roles or []),
        "selected_job_id": str(top.get("id") or ""),
        "selected_job_title": str(top.get("title") or ""),
        "created_at": now,
        "updated_at": now,
    }


def explain_job_match(job: dict[str, Any], profile: dict[str, Any], target_roles: list[str] | None) -> str:
    """Fast template explainer for why a job was ranked (no extra LLM call)."""
    cand_skills = {_normalize_skill(s) for s in (profile.get("skills") or []) if str(s).strip()}
    req_skills = [str(s) for s in (job.get("skills_required") or []) if str(s).strip()]

    matched = [s for s in req_skills if _normalize_skill(s) in cand_skills]
    missing = [s for s in req_skills if _normalize_skill(s) not in cand_skills]

    score_pct = int(round(float(job.get("score") or 0) * 100))
    method = str(job.get("score_method") or "semantic")
    title = str(job.get("title") or "this role")
    roles_hint = ", ".join(target_roles or []) or str(profile.get("headline") or "your profile")

    parts = [
        f"Ranked {score_pct}% via {method} against {roles_hint}.",
    ]
    if matched:
        parts.append(f"Overlapping skills: {', '.join(matched[:6])}.")
    if missing:
        parts.append(f"Gap areas to address: {', '.join(missing[:5])}.")
    else:
        parts.append("Your listed skills cover the core requirements.")
    parts.append(f"{title} aligns with your target direction and current skill signals.")
    return " ".join(parts)


def evaluate_after_match(state: dict[str, Any]) -> dict[str, Any]:
    matches = state.get("job_matches") or []
    top_score = float(matches[0].get("score") or 0) if matches else 0.0
    threshold = settings.SUPERVISOR_LOW_MATCH_THRESHOLD
    low_match = bool(matches) and top_score < threshold

    notes: list[str] = []
    if not matches:
        notes.append("No jobs were retrieved; consider broadening target roles.")
    elif low_match:
        notes.append(
            f"Top match score ({top_score:.2f}) is below {threshold:.2f}. "
            "Refine target roles or strengthen resume keywords before relying on the study plan."
        )

    return {
        "stage": "match",
        "low_match": low_match,
        "top_score": round(top_score, 4),
        "match_threshold": threshold,
        "notes": notes,
    }


def _has_high_priority_gaps(gaps: dict[str, Any]) -> bool:
    missing = gaps.get("missing_skills") or []
    for item in missing:
        if isinstance(item, dict) and str(item.get("priority") or "").lower() == "high":
            return True
    return False


def should_skip_study_plan(state: dict[str, Any]) -> tuple[bool, str]:
    if state.get("skip_study_plan"):
        return True, "supervisor_flag"

    gaps = state.get("skill_gaps") or {}
    missing = gaps.get("missing_skills") or []
    if not missing:
        return True, "no_skill_gaps"

    if settings.SUPERVISOR_SKIP_PLAN_ON_NO_HIGH_GAPS and not _has_high_priority_gaps(gaps):
        return True, "no_high_priority_gaps"

    routing = state.get("routing_decision") or {}
    if routing.get("low_match") and not _has_high_priority_gaps(gaps):
        return True, "low_match_weak_gaps"

    return False, ""


def evaluate_after_gap(state: dict[str, Any]) -> dict[str, Any]:
    skip, reason = should_skip_study_plan(state)
    notes: list[str] = []
    if skip:
        if reason == "no_skill_gaps":
            notes.append("Study plan skipped: no material skill gaps vs. the selected job.")
        elif reason == "no_high_priority_gaps":
            notes.append("Study plan skipped: only low/medium gaps detected.")
        elif reason == "low_match_weak_gaps":
            notes.append("Study plan skipped: weak job match and no high-priority gaps.")
        else:
            notes.append("Study plan skipped by supervisor.")

    return {
        "stage": "gap",
        "skip_study_plan": skip,
        "skip_reason": reason,
        "notes": notes,
    }


def merge_routing_decision(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    current = dict(state.get("routing_decision") or {})
    current.update(patch)
    return current
