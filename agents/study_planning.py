from __future__ import annotations

import json

from config import settings
from .llm_utils import extract_json_block, safe_json_loads


AGENT_ID = "study_planning"
AGENT_NAME = "Study Planning Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_STUDY_PLANNING
TOOLS: list[str] = []


def run(state: dict, *, model: str = DEFAULT_MODEL) -> dict:
    gaps = state.get("skill_gaps") or {}
    profile = state.get("candidate_profile") or {}

    # Fallback when langchain is not installed: generate a minimal deterministic plan.
    try:
        from langchain.schema import HumanMessage, SystemMessage  # type: ignore
        from langchain_openai import ChatOpenAI  # type: ignore
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

        return {
            "study_plan": {
                "timeline_weeks": timeline_weeks,
                "phases": phases,
                "interview_prep": ["Prepare STAR stories", "Review top job description and map experience"],
                "portfolio_tips": ["Show measurable impact", "Add clear README and screenshots"],
                "notes": ["Fallback mode: generated without langchain."],
            },
            "messages": [{"role": "assistant", "name": AGENT_NAME, "content": "Study plan generated (fallback mode)."}],
        }

    system = """You are the Study Planning Agent.

Create a structured learning roadmap to close prioritized skill gaps.
Responsibilities:
- Generate a structured learning plan.
- Recommend learning topics and project ideas.
- Estimate a suggested learning timeline.

Requirements:
- Provide a timeline (weeks) with phases.
- For each phase: topics, practice tasks, and a mini project.
- Recommend free/low-cost learning resources by type (docs/course/video), not specific paid links.
- Make it actionable and realistic for a job seeker.

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
  "portfolio_tips": [string]
}
"""

    user = json.dumps({"candidate_profile": profile, "skill_gaps": gaps}, ensure_ascii=False)
    llm = ChatOpenAI(model=model, temperature=settings.OPENAI_TEMPERATURE)
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user[:20000])])
    raw = str(resp.content).strip()

    payload = safe_json_loads(raw)
    if payload is None:
        jb = extract_json_block(raw)
        payload = safe_json_loads(jb or "") or {"raw": raw}

    return {
        "study_plan": payload,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": "Personalized study plan generated.",
            }
        ],
    }

