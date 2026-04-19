from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config import settings
from tools.learning_rag import (
    build_study_rag_query,
    format_rag_context_for_prompt,
    load_learning_resources,
    retrieve_learning_context,
)
from .llm_utils import extract_json_block, get_embed_fn, safe_json_loads
from tools.explainability import learning_rag_fallback_event, study_plan_rationale


AGENT_ID = "study_planning"
AGENT_NAME = "Study Planning Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_STUDY_PLANNING
TOOLS: list[str] = ["load_learning_resources", "retrieve_learning_context"]


def _default_learning_resources_path() -> str:
    """Absolute path to packaged data/learning_resources.jsonl (works regardless of cwd)."""
    return str(Path(__file__).resolve().parent.parent / "data" / "learning_resources.jsonl")


def _load_kb_rows() -> tuple[list[dict[str, Any]], str]:
    """
    Load learning_resources.jsonl. If LEARNING_RESOURCES_PATH is missing/empty/invalid, fall back to default.
    Returns (rows, path_used_for_debug).
    """
    default_path = _default_learning_resources_path()
    # Note: os.getenv("X", default) returns "" if env is set to empty string — that breaks loading.
    env_path = (os.getenv("LEARNING_RESOURCES_PATH") or "").strip()
    primary = env_path or default_path
    rows = load_learning_resources(primary)
    if rows:
        return rows, primary
    if primary != default_path:
        rows = load_learning_resources(default_path)
        if rows:
            return rows, default_path
    return [], primary


def _resources_from_rag_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Structured resources from retrieved KB rows (always present in API JSON when RAG runs)."""
    out: list[dict[str, Any]] = []
    for s in snippets:
        skills = s.get("skills") or []
        if isinstance(skills, str):
            skills = [skills]
        hints = s.get("resource_hints") or []
        if isinstance(hints, str):
            hints = [hints]
        content = (s.get("content") or "").strip()
        out.append(
            {
                "id": s.get("id"),
                "title": s.get("title") or "",
                "focus_skills": [str(x) for x in skills],
                "summary": content[:600] + ("…" if len(content) > 600 else ""),
                "resource_hints": [str(h) for h in hints],
                "relevance_score": s.get("score"),
                "match_method": s.get("score_method"),
            }
        )
    return out


def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    gaps = state.get("skill_gaps") or {}
    profile = state.get("candidate_profile") or {}

    # Fallback when langchain is not installed: generate a minimal deterministic plan.
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI  
    except ModuleNotFoundError:
        missing = gaps.get("missing_skills") or []
        skills = [m.get("skill") for m in missing if isinstance(m, dict) and m.get("skill")]
        skills = [str(s) for s in skills][:10]
        timeline_weeks = 6
        phases = [
            {
                "name": "Foundation",
                "weeks": [1, 2],
                "goals": ["Set up learning routine", "Cover core concepts"],
                "topics": skills[:3] if skills else ["Core fundamentals for the target role"],
                "practice": ["Daily exercises", "Rewrite resume bullet points with measurable impact"],
                "project": {
                    "title": "Mini Project 1",
                    "description": "Build a small portfolio piece focused on core skills.",
                    "deliverables": ["GitHub repo", "README", "Demo screenshots"],
                },
            },
            {
                "name": "Applied Skills",
                "weeks": [3, 4],
                "goals": ["Practice job-relevant tasks", "Strengthen weak areas"],
                "topics": skills[3:7] if skills else ["Role-specific practice topics"],
                "practice": ["Solve 5–10 role-specific exercises", "Mock interview questions"],
                "project": {
                    "title": "Mini Project 2",
                    "description": "Create an end-to-end project matching the job requirements.",
                    "deliverables": ["Project report", "Deployment (optional)", "Portfolio write-up"],
                },
            },
            {
                "name": "Interview & Portfolio",
                "weeks": [5, 6],
                "goals": ["Polish portfolio", "Prepare interviews"],
                "topics": ["Behavioral STAR stories", "System/role questions"],
                "practice": ["2 mock interviews", "Refine LinkedIn + resume"],
                "project": {
                    "title": "Capstone polish",
                    "description": "Finalize projects and documentation.",
                    "deliverables": ["Updated resume", "Portfolio page", "Interview notes"],
                },
            },
        ]

        sp = {
            "timeline_weeks": timeline_weeks,
            "phases": phases,
            "interview_prep": ["Prepare STAR stories", "Review top job description and map experience"],
            "portfolio_tips": ["Show measurable impact", "Add clear README and screenshots"],
            "resources": [],
            "notes": ["Fallback mode: generated without langchain (no RAG)."],
        }
        return {
            "study_plan": sp,
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Study plan generated (fallback mode)."}],
            "_step_explainability": {
                "summary": "Study plan from deterministic template (no LangChain / no RAG).",
                "rationale": study_plan_rationale(
                    timeline_weeks=timeline_weeks,
                    n_phases=len(phases),
                    n_snippets=0,
                    rag_method=None,
                    langchain_ok=False,
                ),
                "fallback_event": {
                    "component": "study_planning",
                    "from": "rag_llm",
                    "to": "deterministic_template",
                    "reason": "LangChain not installed; minimal plan without retrieval-grounded LLM.",
                },
            },
        }

    system = """You are the Study Planning Agent.

Create a structured learning roadmap to close prioritized skill gaps.
You may receive RETRIEVED_LEARNING_CONTEXT: curated snippets from a local knowledge base (RAG).
When present, ground the plan in those snippets: align phase topics and practice with the skills and hints described.
Do not invent URLs; resource hints should stay at the type level (docs / video / free course) consistent with snippets.

Responsibilities:
- Generate a structured learning plan.
- Recommend learning topics and project ideas.
- Estimate a suggested learning timeline.

Requirements:
- Provide a timeline (weeks) with phases.
- For each phase: topics, practice tasks, and a mini project.
- Recommend free/low-cost learning resources by type (docs/course/video), not specific paid links.
- Make it actionable and realistic for a job seeker.
- Include a "resources" array: for each item, name the resource focus, types (documentation / video / course / practice), related skills, and short notes — aligned with RETRIEVED_LEARNING_CONTEXT when present. Do not invent URLs.

Output ONLY JSON:
{
  "timeline_weeks": number,
  "phases": [
    {
      "name": string,
      "weeks": [number, number],
      "goals": [string],
      "topics": [string],
      "practice": [string],
      "project": { "title": string, "description": string, "deliverables": [string] }
    }
  ],
  "interview_prep": [string],
  "portfolio_tips": [string],
  "resources": [
    {
      "title": string,
      "focus_skills": [string],
      "resource_types": [string],
      "notes": string
    }
  ]
}
"""

    resources, rag_path_used = _load_kb_rows()
    rag_query = build_study_rag_query(profile, gaps)
    snippets = retrieve_learning_context(
        query=rag_query,
        resources=resources,
        embed_fn=get_embed_fn(),
        top_k=settings.STUDY_PLAN_RAG_TOP_K,
        dataset_path=rag_path_used,
    )
    rag_block = format_rag_context_for_prompt(snippets)

    payload_json = json.dumps({"candidate_profile": profile, "skill_gaps": gaps}, ensure_ascii=False)
    user = (
        "RETRIEVED_LEARNING_CONTEXT (RAG — use to ground the plan):\n\n"
        f"{rag_block}\n\n"
        "CANDIDATE_AND_GAPS_JSON:\n"
        f"{payload_json}"
    )[: settings.STUDY_PLANNING_USER_MAX_CHARS]

    llm = ChatOpenAI(
        model=model,
        temperature=settings.OPENAI_TEMPERATURE,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    raw = str(resp.content).strip()

    payload: Any = safe_json_loads(raw)
    if payload is None:
        jb = extract_json_block(raw)
        payload = safe_json_loads(jb or "") or {"raw": raw}

    rag_resources = _resources_from_rag_snippets(snippets)
    rag_method = str(snippets[0].get("score_method")) if snippets else None
    _sp_ex: dict[str, Any] = {}
    fe_rag = learning_rag_fallback_event(rag_method)
    if fe_rag:
        _sp_ex["fallback_event"] = fe_rag

    if isinstance(payload, dict):
        payload["rag_query"] = rag_query
        payload["rag_corpus_path"] = rag_path_used
        payload["rag_corpus_size"] = len(resources)
        # Always expose retrieved KB rows as structured "resources" (RAG).
        llm_res = payload.pop("resources", None)
        payload["resources"] = rag_resources
        # Optional: LLM-written suggestions (same schema-ish); keep separate to avoid losing RAG rows.
        if isinstance(llm_res, list) and llm_res:
            payload["resource_suggestions"] = llm_res
        if len(resources) == 0:
            payload["rag_note"] = (
                "Learning corpus not loaded (file missing or path wrong). "
                "Use default career_pilot_ai/data/learning_resources.jsonl or set LEARNING_RESOURCES_PATH to a valid file. "
                "If .env has LEARNING_RESOURCES_PATH= with no path, remove it or set a real path."
            )
    phases_n = 0
    tw: int | None = None
    if isinstance(payload, dict):
        tw = payload.get("timeline_weeks")
        if isinstance(tw, int):
            pass
        elif tw is not None:
            try:
                tw = int(tw)
            except (TypeError, ValueError):
                tw = None
        ph = payload.get("phases")
        phases_n = len(ph) if isinstance(ph, list) else 0

    _sp_ex["summary"] = "Study plan from LLM grounded in retrieved learning snippets when available."
    _sp_ex["rationale"] = study_plan_rationale(
        timeline_weeks=tw,
        n_phases=phases_n,
        n_snippets=len(snippets),
        rag_method=rag_method,
        langchain_ok=True,
    )

    return {
        "study_plan": payload,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Personalized study plan generated (RAG-grounded when snippets available).",
            }
        ],
        "_step_explainability": _sp_ex,
    }

