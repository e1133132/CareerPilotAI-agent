from __future__ import annotations

import os
from typing import Any

from skills import load_jobs, rank_jobs_semantic
from skills.job_retrieval import fetch_web_job_listings, merge_job_listings
from skills.user_memory import filter_jobs_by_memory
from config import settings

from .llm_utils import get_embed_fn
from .supervisor import explain_job_match
from skills.explainability import job_matching_rationale, job_retrieval_fallback_event


AGENT_ID = "job_matching"
AGENT_NAME = "Job Matching Agent"
DEFAULT_MODEL = settings.OPENAI_MODEL_JOB_MATCHING
SERVICES = [
    "load_jobs",
    "fetch_web_job_listings",
    "merge_job_listings",
    "rank_jobs_semantic",
]


def run(state: dict) -> dict:
    profile = state.get("candidate_profile") or {}

    dataset_path = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.jsonl")
    dataset_path = os.path.abspath(dataset_path)
    jobs = load_jobs(dataset_path)
    for j in jobs:
        j.setdefault("source", "internal")
        j.setdefault("company", settings.INTERNAL_COMPANY_NAME)

    skills = profile.get("skills") or []
    headline = profile.get("headline") or ""
    targets = state.get("target_roles") or []
    memory = state.get("user_memory") or {}
    if not targets and memory.get("preferred_target_roles"):
        targets = list(memory.get("preferred_target_roles") or [])[:5]

    # Fairness: do not use sensitive attributes (we do not store them in profile).
    query = " ".join([headline, " ".join(targets), "Skills:", ", ".join(skills)]).strip()
    if not query:
        query = "entry level role"

    web_jobs: list[dict[str, Any]] = []
    if settings.JOB_WEB_SEARCH_ENABLED:
        web_jobs = fetch_web_job_listings(query, target_roles=targets or None)

    corpus = merge_job_listings(jobs, web_jobs) if web_jobs else jobs

    ranked: list[dict[str, Any]] = rank_jobs_semantic(
        query=query,
        jobs=corpus,
        embed_fn=get_embed_fn(),
        top_k=5,
    )
    ranked = filter_jobs_by_memory(ranked, memory)

    for idx, job in enumerate(ranked):
        if idx < 3:
            job["match_explanation"] = explain_job_match(job, profile, targets)

    sm = ranked[0].get("score_method") if ranked else None
    internal_n = sum(1 for j in ranked if str(j.get("source") or "internal") == "internal")
    web_n = len(ranked) - internal_n
    step: dict[str, Any] = {
        "summary": (
            f"Ranked {len(ranked)} jobs ({internal_n} internal {settings.INTERNAL_COMPANY_NAME}, "
            f"{web_n} web) by semantic/keyword scoring."
        ),
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

