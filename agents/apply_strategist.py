from __future__ import annotations

import json
import os
from typing import Any

from config import settings
from .supervisor import resolve_target_job
from skills.user_memory import filter_jobs_by_memory


AGENT_ID = "apply_strategist"
AGENT_NAME = "Apply Strategist Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_APPLY_STRATEGIST
SERVICES: list[str] = []


def _readiness(score: float, gap_count: int) -> str:
    if score >= 0.75 and gap_count <= 1:
        return "high"
    if score >= 0.5 and gap_count <= 3:
        return "medium"
    return "low"


def _template_strategy(state: dict[str, Any]) -> dict[str, Any]:
    profile = state.get("candidate_profile") or {}
    matches = list(state.get("job_matches") or [])
    memory = state.get("user_memory") or {}
    matches = filter_jobs_by_memory(matches, memory)
    gaps = state.get("skill_gaps") or {}
    missing = gaps.get("missing_skills") or []
    gap_count = len(missing) if isinstance(missing, list) else 0
    target = resolve_target_job(state)
    skills = profile.get("skills") or []

    priority: list[dict[str, Any]] = []
    for idx, job in enumerate(matches[:5]):
        score = float(job.get("score") or 0)
        priority.append(
            {
                "rank": idx + 1,
                "job_id": str(job.get("id") or ""),
                "title": str(job.get("title") or ""),
                "company": str(job.get("company") or ""),
                "readiness": _readiness(score, gap_count if job.get("id") == target.get("id") else gap_count + 1),
                "reason": (
                    f"Match {int(score * 100)}% — align {', '.join(str(s) for s in skills[:3]) or 'profile'} "
                    f"with required {', '.join((job.get('skills_required') or [])[:3])}."
                ),
            }
        )

    selected_title = str(target.get("title") or priority[0]["title"] if priority else "")
    hooks = [
        f"Lead with your experience in {', '.join(str(s) for s in skills[:2]) or 'relevant projects'} for {selected_title}.",
        "Quantify one recent outcome (metric + impact) in the opening paragraph.",
    ]
    if gap_count:
        hooks.append(
            f"Address skill gaps proactively: mention learning plan for {missing[0].get('skill') if isinstance(missing[0], dict) else missing[0]}."
        )

    rejected = memory.get("rejected_job_ids") or []
    notes = []
    if rejected:
        notes.append(f"Deprioritized {len(rejected)} previously rejected job(s) in ranking.")

    return {
        "target_job": {"id": str(target.get("id") or ""), "title": selected_title},
        "priority_applications": priority,
        "cover_letter_hooks": hooks,
        "follow_up_checklist": [
            "Customize resume bullets for top 2 roles (see Resume Suggestions).",
            "Apply within 5–7 days while posting is fresh.",
            "Set a 7-day follow-up reminder if no response.",
            "Prepare 2 STAR stories mapped to top job requirements.",
        ],
        "timing_advice": "Apply to high-readiness roles first; batch medium-readiness applications after resume tweaks.",
        "notes": notes or ["Template strategy (no LLM)."],
    }


def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    if not settings.APPLY_STRATEGIST_ENABLED:
        payload = _template_strategy(state)
        return {
            "apply_strategy": payload,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Apply strategy (template)."}],
            "_step_explainability": {
                "summary": "Apply strategist disabled; returned rule-based priority list.",
                "rationale": "Ranked jobs by match score and gap readiness without LLM.",
            },
        }

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError:
        payload = _template_strategy(state)
        return {
            "apply_strategy": payload,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Apply strategy (fallback)."}],
            "_step_explainability": {
                "summary": "Template apply strategy (LangChain unavailable).",
                "rationale": "Used deterministic ranking and checklist.",
                "fallback_event": {
                    "component": "apply_strategist",
                    "from": "llm",
                    "to": "template",
                    "reason": "LangChain not installed.",
                },
            },
        }

    system = """You are the Apply Strategist Agent for CareerPilot AI.

Given job matches, skill gaps, resume context, and optional user memory:
- Rank top applications (max 5) with readiness (high/medium/low) and short reasons.
- Suggest 2-3 cover letter opening hooks (no full letter).
- Provide a practical follow-up checklist (4-6 items).
- Respect user_memory.rejected_job_ids — do not rank those as top priority.
- Do NOT guarantee interviews or offers.

Output ONLY JSON:
{
  "target_job": { "id": string, "title": string },
  "priority_applications": [
    { "rank": number, "job_id": string, "title": string, "company": string, "readiness": "high"|"medium"|"low", "reason": string }
  ],
  "cover_letter_hooks": [string],
  "follow_up_checklist": [string],
  "timing_advice": string,
  "notes": [string]
}
"""

    user_payload = {
        "candidate_profile": state.get("candidate_profile") or {},
        "job_matches": state.get("job_matches") or [],
        "skill_gaps": state.get("skill_gaps") or {},
        "resume_suggestions": state.get("resume_suggestions") or {},
        "user_memory": state.get("user_memory") or {},
        "session_memory": state.get("session_memory") or {},
    }
    user = json.dumps(user_payload, ensure_ascii=False)[: settings.APPLY_STRATEGIST_USER_MAX_CHARS]

    llm = ChatOpenAI(
        model=model,
        temperature=settings.OPENAI_TEMPERATURE,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
        api_key=settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    raw = str(resp.content).strip()

    from .llm_utils import extract_json_block, safe_json_loads

    payload: Any = safe_json_loads(raw)
    if payload is None:
        payload = safe_json_loads(extract_json_block(raw) or "")

    if not isinstance(payload, dict):
        payload = _template_strategy(state)

    return {
        "apply_strategy": payload,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Personalized application strategy generated.",
            }
        ],
        "_step_explainability": {
            "summary": f"Apply strategy for {len(payload.get('priority_applications') or [])} prioritized role(s).",
            "rationale": "LLM ranked applications using matches, gaps, and user memory signals.",
        },
    }
