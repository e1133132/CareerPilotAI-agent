from __future__ import annotations

import json


def summarizer(state) -> str:
    """
    Produce a final structured report from the state (no extra LLM call).
    """
    profile = state.get("candidate_profile") or {}
    matches = state.get("job_matches") or []
    gaps = state.get("skill_gaps") or {}
    plan = state.get("study_plan") or {}

    report = {
        "candidate_profile": profile,
        "recommended_jobs": matches,
        "skill_gaps": gaps,
        "study_plan": plan,
    }
    return "=== CAREERPILOT AI REPORT (JSON) ===\n\n" + json.dumps(report, indent=2, ensure_ascii=False)

