"""
Reusable skills for CareerPilot AI.

Each subfolder is a self-contained capability package (SKILL.md + scripts + resources refs)
that multiple agents can import without duplicating logic.
"""

from skills.job_retrieval import load_jobs, rank_jobs_semantic
from skills.learning_rag import (
    build_study_rag_query,
    fetch_web_learning_resources,
    format_rag_context_for_prompt,
    load_learning_resources,
    merge_learning_resources,
    retrieve_learning_context,
)
from skills.resume_parsing import load_resume_text

__all__ = [
    "load_resume_text",
    "load_jobs",
    "rank_jobs_semantic",
    "build_study_rag_query",
    "format_rag_context_for_prompt",
    "load_learning_resources",
    "retrieve_learning_context",
    "fetch_web_learning_resources",
    "merge_learning_resources",
]
