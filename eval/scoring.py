from __future__ import annotations

from typing import Any


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _skill_set_from_profile(profile: dict[str, Any] | list[Any] | None) -> set[str]:
    """Normalize skills from candidate_profile.skills (str or {skill: ...})."""
    if isinstance(profile, list):
        skills = profile
    elif isinstance(profile, dict):
        skills = profile.get("skills") or []
    else:
        skills = []
    out: set[str] = set()
    for item in skills:
        if isinstance(item, dict):
            out.add(_norm(str(item.get("skill") or "")))
        elif isinstance(item, str):
            out.add(_norm(item))
    return {s for s in out if s}


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    return str(value)


def missing_skills_recall(output: dict[str, Any], reference: dict[str, Any]) -> float:
    """Fraction of reference required_missing_skills found in output.missing_skills."""
    expected = reference.get("required_missing_skills") or []
    if not expected:
        missing = output.get("missing_skills") or []
        return 1.0 if len(missing) == 0 else 0.0

    actual = {
        _norm(m.get("skill"))
        for m in (output.get("missing_skills") or [])
        if isinstance(m, dict)
    }
    hits = sum(1 for skill in expected if _norm(skill) in actual)
    return hits / len(expected)


def forbidden_text_absent(output: dict[str, Any], reference: dict[str, Any]) -> bool:
    blocked = [str(x).lower() for x in (reference.get("forbidden_in_output") or []) if str(x).strip()]
    if not blocked:
        return True
    text = str(output).lower()
    return not any(token in text for token in blocked)


def field_accuracy(output: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Skill-gap field metrics (kept for backward compatibility)."""
    recall = missing_skills_recall(output, reference)
    fair_ok = forbidden_text_absent(output, reference)
    return {
        "missing_skills_recall": round(recall, 4),
        "forbidden_text_absent": fair_ok,
        "field_pass": recall >= 1.0 and fair_ok,
        "primary_metric": "missing_skills_recall",
        "primary_value": round(recall, 4),
    }


def skills_recall(profile: dict[str, Any] | None, reference: dict[str, Any]) -> float:
    """Fraction of reference required_skills found in candidate_profile.skills."""
    required = reference.get("required_skills") or []
    if not required:
        return 1.0
    actual = _skill_set_from_profile(profile)
    hits = sum(1 for skill in required if _norm(skill) in actual)
    return hits / len(required)


def hit_at_k(
    job_matches: list[dict[str, Any]] | None,
    reference: dict[str, Any],
) -> float:
    """
    1.0 if every must_include_title_substring appears in at least one of top-k titles.
    Empty required list => 1.0.
    """
    required = [str(x) for x in (reference.get("must_include_title_substrings") or []) if str(x).strip()]
    if not required:
        return 1.0
    k = int(reference.get("top_k") or 5)
    ranked = list(job_matches or [])[: max(1, k)]
    titles = " | ".join(_norm(str(j.get("title") or "")) for j in ranked if isinstance(j, dict))
    hits = sum(1 for sub in required if _norm(sub) in titles)
    return hits / len(required)


def plan_skill_coverage(study_plan: dict[str, Any] | None, reference: dict[str, Any]) -> float:
    """Fraction of required_covered_skills appearing anywhere in study_plan text."""
    required = reference.get("required_covered_skills") or []
    if not required:
        return 1.0
    blob = _norm(_flatten_text(study_plan or {}))
    hits = sum(1 for skill in required if _norm(skill) in blob)
    return hits / len(required)


def score_case(agent: str, output: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Dispatch field metrics by agent. Always includes field_pass + primary_*."""
    agent_name = (agent or "").strip()
    fair_ok = forbidden_text_absent(output, reference)

    if agent_name == "skill_gap":
        scores = field_accuracy(output, reference)
        return scores

    if agent_name == "resume_analysis":
        recall = skills_recall(output if isinstance(output, dict) else {}, reference)
        return {
            "skills_recall": round(recall, 4),
            "forbidden_text_absent": fair_ok,
            "field_pass": recall >= 1.0 and fair_ok,
            "primary_metric": "skills_recall",
            "primary_value": round(recall, 4),
        }

    if agent_name == "job_matching":
        matches = output.get("job_matches") if isinstance(output, dict) else None
        if matches is None and isinstance(output, list):
            matches = output
        hit = hit_at_k(matches if isinstance(matches, list) else [], reference)
        return {
            "hit_at_k": round(hit, 4),
            "forbidden_text_absent": fair_ok,
            "field_pass": hit >= 1.0 and fair_ok,
            "primary_metric": "hit_at_k",
            "primary_value": round(hit, 4),
        }

    if agent_name == "study_planning":
        plan = output.get("study_plan") if isinstance(output, dict) and "study_plan" in output else output
        coverage = plan_skill_coverage(plan if isinstance(plan, dict) else {}, reference)
        return {
            "plan_skill_coverage": round(coverage, 4),
            "forbidden_text_absent": fair_ok,
            "field_pass": coverage >= 1.0 and fair_ok,
            "primary_metric": "plan_skill_coverage",
            "primary_value": round(coverage, 4),
        }

    raise ValueError(f"No scorer registered for agent: {agent_name}")
