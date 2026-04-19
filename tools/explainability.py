"""
Explainability helpers: user-facing rationales derived from existing structured outputs (no extra LLM calls).
"""

from __future__ import annotations

from typing import Any


def default_limitations() -> list[str]:
    return [
        "Recommendations depend on extractable resume text, the configured job and learning datasets, and model variability.",
        "Job ranking may use vector search (Qdrant) when available, or keyword overlap as a fallback.",
    ]


def resume_rationale_from_outputs(profile: dict[str, Any], evidence: dict[str, Any]) -> str:
    skills = profile.get("skills") or []
    n_skills = len(skills) if isinstance(skills, list) else 0
    exp = profile.get("experience") or []
    n_exp = len(exp) if isinstance(exp, list) else 0
    edu = profile.get("education") or []
    n_edu = len(edu) if isinstance(edu, list) else 0
    ev_sk = evidence.get("skills") or []
    n_ev = len(ev_sk) if isinstance(ev_sk, list) else 0
    return (
        f"We built your profile from the resume: {n_skills} skills listed, {n_exp} experience entries, "
        f"{n_edu} education entries, with {n_ev} skill-evidence links where snippets were available."
    )


def job_matching_rationale(
    ranked: list[dict[str, Any]],
    target_roles: list[str] | None,
    score_method: str | None,
) -> str:
    n = len(ranked)
    roles = ", ".join(target_roles or []) or "your headline and skills"
    method = score_method or "unknown"
    top_titles = [str(j.get("title") or "") for j in ranked[:3]]
    preview = "; ".join(t for t in top_titles if t) or "(no titles)"
    return (
        f"We ranked {n} jobs using {method} against a query built from {roles}. "
        f"Top matches include: {preview}."
    )


def skill_gap_rationale(gaps: dict[str, Any], rule_based: bool) -> str:
    tj = gaps.get("target_job") or {}
    title = str(tj.get("title") or "the top matched job")
    missing = gaps.get("missing_skills") or []
    n_miss = len(missing) if isinstance(missing, list) else 0
    mode = "rule-based comparison of required vs. resume skills" if rule_based else "LLM comparison of your profile to the job"
    return (
        f"We compared your skills to {title} using {mode}, and identified {n_miss} prioritized gap(s) with short reasons per skill."
    )


def study_plan_rationale(
    *,
    timeline_weeks: int | None,
    n_phases: int,
    n_snippets: int,
    rag_method: str | None,
    langchain_ok: bool,
) -> str:
    if not langchain_ok:
        return (
            "We generated a compact multi-week template from your gap list because advanced planning dependencies were unavailable."
        )
    tw = timeline_weeks or 0
    rm = rag_method or "none"
    return (
        f"We grounded the plan in {n_snippets} retrieved learning snippet(s) ({rm}) and structured it into "
        f"{n_phases} phase(s) over about {tw} week(s), aligned to your gaps and profile."
    )


def job_retrieval_fallback_event(score_method: str | None) -> dict[str, Any] | None:
    if score_method in ("keyword", "keyword_fallback"):
        return {
            "component": "job_matching",
            "from": "qdrant",
            "to": "keyword",
            "reason": "Vector index unavailable or returned no hits; jobs ranked by keyword overlap.",
        }
    if score_method == "embedding_cosine":
        return {
            "component": "job_matching",
            "from": "qdrant",
            "to": "local_embedding",
            "reason": "Local cosine similarity path used (ALLOW_LOCAL_EMBEDDING_FALLBACK) instead of Qdrant.",
        }
    return None


def build_explainability_block(state: dict[str, Any]) -> dict[str, Any]:
    """Assemble API `explainability` object from final workflow state."""
    return {
        "pipeline_trace": state.get("pipeline_trace") or [],
        "fallback_events": state.get("fallback_events") or [],
        "limitations": default_limitations(),
    }


def learning_rag_fallback_event(score_method: str | None) -> dict[str, Any] | None:
    if score_method in ("keyword", "keyword_fallback"):
        return {
            "component": "learning_rag",
            "from": "qdrant",
            "to": "keyword",
            "reason": "Vector index unavailable or returned no hits; learning snippets ranked by keyword overlap.",
        }
    if score_method == "embedding_cosine":
        return {
            "component": "learning_rag",
            "from": "qdrant",
            "to": "local_embedding",
            "reason": "Local embedding similarity used for learning resources instead of Qdrant.",
        }
    return None
