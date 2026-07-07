from __future__ import annotations

import json
import os
from typing import Any

from config import settings
from .llm_utils import extract_json_block, safe_json_loads
from .supervisor import resolve_target_job
from skills.explainability import resume_rationale_from_outputs


AGENT_ID = "resume_optimizer"
AGENT_NAME = "Resume Optimizer Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_RESUME_OPTIMIZER
SERVICES: list[str] = []


def _template_suggestions(profile: dict[str, Any], target_job: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable."""
    req = [str(s) for s in (target_job.get("skills_required") or []) if str(s).strip()]
    cand = {str(s).lower() for s in (profile.get("skills") or []) if str(s).strip()}
    missing = [s for s in req if s.lower() not in cand][:5]

    experience = profile.get("experience") or []
    bullets: list[dict[str, Any]] = []
    for exp in experience[:3]:
        role = str(exp.get("role") or "Role")
        company = str(exp.get("company") or "Company")
        highlights = exp.get("highlights") or []
        original = highlights[0] if highlights else f"Contributed as {role} at {company}."
        bullets.append(
            {
                "section": f"{role} @ {company}",
                "original": original,
                "suggested": (
                    f"{original} Quantify impact with metrics where possible and mirror keywords: "
                    f"{', '.join(req[:4]) or 'role-relevant terms'}."
                ),
                "rationale": "Template rewrite emphasizing measurable outcomes and JD keywords.",
            }
        )

    return {
        "target_job": {
            "id": str(target_job.get("id") or ""),
            "title": str(target_job.get("title") or ""),
        },
        "summary_tip": (
            "Lead with role-aligned headline and 2–3 quantified wins. "
            f"Surface missing keywords naturally: {', '.join(missing) or 'none detected'}."
        ),
        "experience_bullets": bullets,
        "ats_keywords": req[:8],
        "notes": ["Fallback mode: template suggestions without LLM."],
    }


def _reflect_and_fix(payload: dict[str, Any], profile: dict[str, Any], *, model: str) -> dict[str, Any]:
    """One lightweight reflect pass: reject fabricated employers/roles."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError:
        return payload

    known_companies = {
        str(e.get("company") or "").strip().lower()
        for e in (profile.get("experience") or [])
        if isinstance(e, dict)
    }
    known_roles = {
        str(e.get("role") or "").strip().lower()
        for e in (profile.get("experience") or [])
        if isinstance(e, dict)
    }

    system = """You are a resume quality reviewer. Check optimized bullets for hallucinations.
Rules:
- Employers and roles in suggestions MUST appear in the candidate profile experience list.
- Do NOT invent certifications, employers, or metrics not implied by originals.
- If a bullet invents facts, rewrite it to stay grounded or drop it.
Output ONLY JSON:
{
  "approved": boolean,
  "experience_bullets": [ { "section": string, "original": string, "suggested": string, "rationale": string } ],
  "summary_tip": string,
  "ats_keywords": [string],
  "notes": [string]
}
"""

    user = json.dumps(
        {
            "candidate_experience": profile.get("experience") or [],
            "draft": payload,
            "known_companies": sorted(known_companies),
            "known_roles": sorted(known_roles),
        },
        ensure_ascii=False,
    )

    llm = ChatOpenAI(
        model=model,
        temperature=0,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
        api_key=settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    raw = str(resp.content).strip()
    reviewed = safe_json_loads(raw)
    if reviewed is None:
        reviewed = safe_json_loads(extract_json_block(raw) or "")

    if not isinstance(reviewed, dict):
        return payload

    if reviewed.get("approved") is False:
        payload["notes"] = (payload.get("notes") or []) + ["Reflect pass flagged issues; kept revised bullets."]

    for key in ("experience_bullets", "summary_tip", "ats_keywords", "notes"):
        if reviewed.get(key) is not None:
            payload[key] = reviewed[key]
    return payload


def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    profile = state.get("candidate_profile") or {}
    evidence = state.get("resume_evidence") or {}
    target_job = resolve_target_job(state)

    if not target_job:
        return {
            "resume_suggestions": {
                "target_job": {"id": "", "title": ""},
                "summary_tip": "Select a target job to generate tailored resume suggestions.",
                "experience_bullets": [],
                "ats_keywords": [],
                "notes": ["No target job available."],
            },
            "messages": [
                {
                    "role": "assistant",
                    "name": AGENT_NAME,
                    "content": "Resume optimization skipped (no target job).",
                }
            ],
            "_step_explainability": {
                "summary": "Resume optimizer skipped — no job match selected.",
                "rationale": "Provide job matches before generating resume rewrite suggestions.",
            },
        }

    if not settings.RESUME_OPTIMIZER_ENABLED:
        payload = _template_suggestions(profile, target_job)
        return {
            "resume_suggestions": payload,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Template resume tips generated."}],
            "_step_explainability": {
                "summary": "Resume optimizer disabled; returned template suggestions.",
                "rationale": resume_rationale_from_outputs(profile, evidence),
            },
        }

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ModuleNotFoundError:
        payload = _template_suggestions(profile, target_job)
        return {
            "resume_suggestions": payload,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Resume suggestions (fallback)."}],
            "_step_explainability": {
                "summary": "Template resume suggestions (LangChain unavailable).",
                "rationale": resume_rationale_from_outputs(profile, evidence),
                "fallback_event": {
                    "component": "resume_optimizer",
                    "from": "llm",
                    "to": "template",
                    "reason": "LangChain not installed.",
                },
            },
        }

    system = """You are the Resume Optimizer Agent for CareerPilot AI.

Given candidate profile, resume evidence, and a target job:
- Rewrite up to 3 experience bullets to align with the job (ATS keywords, quantified impact).
- Provide a concise summary/headline tip.
- List ATS keywords to weave in (from job requirements + profile overlap).
- NEVER invent employers, roles, degrees, or metrics not supported by the profile/evidence.
- Keep suggestions actionable and concise.

Output ONLY JSON:
{
  "target_job": { "id": string, "title": string },
  "summary_tip": string,
  "experience_bullets": [
    { "section": string, "original": string, "suggested": string, "rationale": string }
  ],
  "ats_keywords": [string],
  "notes": [string]
}
"""

    user = json.dumps(
        {
            "candidate_profile": profile,
            "resume_evidence": evidence,
            "target_job": target_job,
            "skill_gaps": state.get("skill_gaps") or {},
        },
        ensure_ascii=False,
    )

    llm = ChatOpenAI(
        model=model,
        temperature=settings.OPENAI_TEMPERATURE,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
        api_key=settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=user[: settings.RESUME_OPTIMIZER_USER_MAX_CHARS]),
        ]
    )
    raw = str(resp.content).strip()
    payload: Any = safe_json_loads(raw)
    if payload is None:
        payload = safe_json_loads(extract_json_block(raw) or "")

    if not isinstance(payload, dict):
        payload = _template_suggestions(profile, target_job)

    payload.setdefault("target_job", {"id": target_job.get("id"), "title": target_job.get("title")})
    payload = _reflect_and_fix(payload, profile, model=model)

    return {
        "resume_suggestions": payload,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Resume rewrite suggestions generated with one reflect pass.",
            }
        ],
        "_step_explainability": {
            "summary": f"Resume suggestions for {target_job.get('title', 'target job')} with reflect QA.",
            "rationale": (
                "Rewrote bullets toward JD keywords using profile evidence; reflect pass checked for hallucinations."
            ),
        },
    }
