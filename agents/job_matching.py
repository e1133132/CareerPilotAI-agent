from __future__ import annotations

import os
from typing import Any

from tools import load_jobs, rank_jobs_semantic
from config import settings

from .llm_utils import get_embed_fn
from tools.explainability import job_matching_rationale, job_retrieval_fallback_event


AGENT_ID = "job_matching"
AGENT_NAME = "Job Matching Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_JOB_MATCHING
TOOLS = ["load_jobs", "rank_jobs_semantic"]


def run(state: dict) -> dict:
    profile = state.get("candidate_profile") or {}

    dataset_path = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.jsonl")
    dataset_path = os.path.abspath(dataset_path)
    jobs = load_jobs(dataset_path)

    skills = profile.get("skills") or []
    headline = profile.get("headline") or ""
    targets = state.get("target_roles") or []

    # Fairness: do not use sensitive attributes (we do not store them in profile).
    query = " ".join([headline, " ".join(targets), "Skills:", ", ".join(skills)]).strip()
    if not query:
        query = "entry level role"

    ranked: list[dict[str, Any]] = rank_jobs_semantic(
        query=query,
        jobs=jobs,
        embed_fn=get_embed_fn(),
        top_k=5,
    )

    sm = ranked[0].get("score_method") if ranked else None
    step: dict[str, Any] = {
        "summary": f"Ranked {len(ranked)} jobs by semantic/keyword scoring.",
        "rationale": job_matching_rationale(ranked, targets, str(sm) if sm is not None else None),
    }
    fe = job_retrieval_fallback_event(str(sm) if sm is not None else None)
    if fe:
        step["fallback_event"] = fe

    return {
        "job_matches": ranked,
        "messages": [
            {
                "role": "assistant",
                "name": AGENT_NAME,
                "content": f"Matched and ranked {len(ranked)} jobs.",
            }
        ],
        "_step_explainability": step,
    }

