from __future__ import annotations

import json

from config import settings
from .llm_utils import extract_json_block, safe_json_loads
from tools.explainability import skill_gap_rationale


AGENT_ID = "skill_gap"
AGENT_NAME = "Skill Gap Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_SKILL_GAP
TOOLS: list[str] = []


def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    profile = state.get("candidate_profile") or {}
    evidence = state.get("resume_evidence") or {}
    matches = state.get("job_matches") or []
    top_job = matches[0] if matches else {}

    # Fallback when langchain is not installed: do a simple rule-based gap analysis.
    try:
        from langchain.schema import HumanMessage, SystemMessage  # type: ignore
        from langchain_openai import ChatOpenAI  # type: ignore
    except ModuleNotFoundError:
        cand_skills = set((profile.get("skills") or []))
        req_skills = set((top_job.get("skills_required") or []))
        missing = sorted([s for s in req_skills if s not in cand_skills])
        matched = sorted([s for s in cand_skills if s in req_skills])

        missing_items = [{"skill": s, "priority": "high", "reason": "Listed in job requirements but not found in resume skills."} for s in missing]
        payload = {
            "target_job": {"id": str(top_job.get("id") or ""), "title": str(top_job.get("title") or "")},
            "matched_strengths": matched,
            "missing_skills": missing_items,
            "notes": ["Fallback mode: rule-based comparison (langchain not installed)."],
        }
        return {
            "skill_gaps": payload,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Skill gaps identified (fallback mode)."}],
            "_step_explainability": {
                "summary": "Skill gaps from rule-based resume vs. top job requirements.",
                "rationale": skill_gap_rationale(payload, rule_based=True),
                "fallback_event": {
                    "component": "skill_gap",
                    "from": "llm",
                    "to": "rule_based",
                    "reason": "LangChain not installed; compared resume skills to top job requirements.",
                },
            },
        }

    system = """You are the Skill Gap Agent.

Given:
- candidate profile (skills/education/experience)
- resume evidence for skills (snippets)
- top recommended job (title/description/skills_required)

Tasks:
- Compare candidate skills against job required skills.
- Identify missing skills and weak areas.
- Prioritize gaps by impact (high/medium/low) and explain why.
- Keep it explainable: reference the evidence snippets that support current skills.
- Avoid sensitive attributes.

Output ONLY JSON:
{
  "target_job": { "id": string, "title": string },
  "matched_strengths": [string],
  "missing_skills": [ { "skill": string, "priority": "high"|"medium"|"low", "reason": string } ],
  "notes": [string]
}
"""

    user = json.dumps(
        {"candidate_profile": profile, "resume_evidence": evidence, "target_job": top_job},
        ensure_ascii=False,
    )
    llm = ChatOpenAI(
        model=model,
        temperature=settings.OPENAI_TEMPERATURE,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    resp = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=user[: settings.SKILL_GAP_USER_MAX_CHARS])]
    )
    raw = str(resp.content).strip()

    payload = safe_json_loads(raw)
    if payload is None:
        jb = extract_json_block(raw)
        payload = safe_json_loads(jb or "") or {"raw": raw}

    return {
        "skill_gaps": payload,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Skill gaps identified for the top job match.",
            }
        ],
        "_step_explainability": {
            "summary": "Skill gaps from LLM comparison of profile, evidence, and target job.",
            "rationale": skill_gap_rationale(payload if isinstance(payload, dict) else {}, rule_based=False),
        },
    }

