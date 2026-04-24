from __future__ import annotations

from typing import Any

import agents.job_matching as jm
import pytest


def _make_jobs(n: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"jd-{i:03d}",
            "title": f"Role {i}",
            "description": f"Description {i}",
            "skills_required": ["Python", "SQL"],
        }
        for i in range(1, n + 1)
    ]


def test_run_returns_top5_and_contract_fields(monkeypatch) -> None:
    jobs = _make_jobs(8)
    captured: dict[str, Any] = {}

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured["query"] = query
        captured["top_k"] = top_k
        ranked = []
        for idx, j in enumerate(jobs[:top_k]):
            ranked.append({**j, "score": 1.0 - (idx * 0.1), "score_method": "qdrant_cosine"})
        return ranked

    monkeypatch.setattr(jm, "load_jobs", lambda _path: jobs)
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    state = {"candidate_profile": {"headline": "Data Analyst", "skills": ["Python", "SQL"]}, "target_roles": ["Analyst"]}
    out = jm.run(state)

    assert len(out["job_matches"]) == 5
    assert captured["top_k"] == 5
    assert all("score" in j and "score_method" in j for j in out["job_matches"])
    assert out["messages"][0]["name"] == jm.AGENT_NAME
    assert "_step_explainability" in out
    step = out["_step_explainability"]
    assert "summary" in step and "rationale" in step


def test_run_builds_query_from_headline_targets_skills(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured["query"] = query
        return [{**jobs[0], "score": 0.9, "score_method": "qdrant_cosine"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(2))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    state = {
        "candidate_profile": {"headline": "Backend Engineer", "skills": ["Python", "Docker"]},
        "target_roles": ["Platform Engineer", "SRE"],
    }
    jm.run(state)

    assert captured["query"] == "Backend Engineer Platform Engineer SRE Skills: Python, Docker"


def test_run_uses_entry_level_default_when_query_empty(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured["query"] = query
        return [{**jobs[0], "score": 0.1, "score_method": "keyword"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(1))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    jm.run({})
    assert captured["query"] == "Skills:"


def test_explainability_includes_fallback_event_for_keyword(monkeypatch) -> None:
    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        return [{**jobs[0], "score": 0.2, "score_method": "keyword"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(1))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    out = jm.run({"candidate_profile": {"headline": "Data Analyst", "skills": ["SQL"]}})
    fe = out["_step_explainability"].get("fallback_event")
    assert fe is not None
    assert fe["component"] == "job_matching"
    assert fe["to"] == "keyword"


def test_no_fallback_event_for_qdrant_cosine(monkeypatch) -> None:
    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        return [{**jobs[0], "score": 0.8, "score_method": "qdrant_cosine"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(1))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    out = jm.run({"candidate_profile": {"headline": "Data Engineer", "skills": ["Python"]}})
    assert "fallback_event" not in out["_step_explainability"]


def test_bias_sensitive_terms_do_not_control_query_or_ranking_inputs(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured["query"] = query
        return [{**jobs[0], "score": 0.9, "score_method": "qdrant_cosine"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(1))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    state = {
        "candidate_profile": {
            "headline": "Data Analyst",
            "skills": ["Python", "SQL"],
            "gender": "female",
            "ethnicity": "Malay",
            "age": "22",
        },
        "target_roles": ["BI Analyst"],
    }
    jm.run(state)

    query = captured["query"].lower()
    assert "female" not in query
    assert "malay" not in query
    assert "22" not in query
    assert query == "data analyst bi analyst skills: python, sql"


def test_bias_role_equivalence_with_same_professional_signals(monkeypatch) -> None:
    captured_queries: list[str] = []

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured_queries.append(query)
        return [{**jobs[0], "score": 0.95, "score_method": "qdrant_cosine"}]

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(2))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    state_a = {
        "candidate_profile": {"headline": "Data Analyst", "skills": ["Python", "SQL"], "gender": "female"},
        "target_roles": ["Data Analyst"],
    }
    state_b = {
        "candidate_profile": {"headline": "Data Analyst", "skills": ["Python", "SQL"], "gender": "male"},
        "target_roles": ["Data Analyst"],
    }

    out_a = jm.run(state_a)
    out_b = jm.run(state_b)

    assert captured_queries[0] == captured_queries[1]
    assert out_a["job_matches"] == out_b["job_matches"]


def _topk_jaccard(matches_a: list[dict[str, Any]], matches_b: list[dict[str, Any]]) -> float:
    ids_a = {str(m.get("id")) for m in matches_a}
    ids_b = {str(m.get("id")) for m in matches_b}
    if not ids_a and not ids_b:
        return 1.0
    union = ids_a | ids_b
    inter = ids_a & ids_b
    return len(inter) / max(1, len(union))


@pytest.mark.parametrize(
    "variant_a,variant_b",
    [
        (
            {"name": "Aisha Tan", "pronouns": "she/her", "age": "22"},
            {"name": "Brandon Lim", "pronouns": "he/him", "age": "47"},
        ),
        (
            {"name": "Nur Iman", "gender": "female", "age": "29"},
            {"name": "John Lee", "gender": "male", "age": "29"},
        ),
        (
            {"name": "Mei Lin", "pronouns": "they/them", "age": "31"},
            {"name": "David Ong", "pronouns": "he/him", "age": "31"},
        ),
        (
            {"name": "Siti A.", "gender": "woman", "age": "55"},
            {"name": "Ryan K.", "gender": "man", "age": "23"},
        ),
        (
            {"name": "Farah", "pronouns": "she/her", "age": "40"},
            {"name": "Alex", "pronouns": "he/him", "age": "40"},
        ),
    ],
)
def test_counterfactual_bias_invariance_across_sensitive_variants(monkeypatch, variant_a, variant_b) -> None:
    captured_queries: list[str] = []

    def _fake_rank_jobs_semantic(*, query: str, jobs: list[dict[str, Any]], embed_fn, top_k: int = 5):
        captured_queries.append(query)
        ranked = []
        for idx, j in enumerate(jobs[:top_k]):
            ranked.append({**j, "score": 1.0 - (idx * 0.05), "score_method": "qdrant_cosine"})
        return ranked

    monkeypatch.setattr(jm, "load_jobs", lambda _path: _make_jobs(8))
    monkeypatch.setattr(jm, "rank_jobs_semantic", _fake_rank_jobs_semantic)
    monkeypatch.setattr(jm, "get_embed_fn", lambda: None)

    base_profile = {"headline": "Data Analyst", "skills": ["Python", "SQL"]}
    roles = ["Data Analyst", "BI Analyst"]

    state_a = {"candidate_profile": {**base_profile, **variant_a}, "target_roles": roles}
    state_b = {"candidate_profile": {**base_profile, **variant_b}, "target_roles": roles}

    out_a = jm.run(state_a)
    out_b = jm.run(state_b)

    # Same professional signals => same retrieval query.
    assert captured_queries[0] == captured_queries[1]

    # Counterfactual fairness checks on ranking outputs.
    assert out_a["job_matches"][0]["id"] == out_b["job_matches"][0]["id"]
    assert _topk_jaccard(out_a["job_matches"], out_b["job_matches"]) >= 0.8
