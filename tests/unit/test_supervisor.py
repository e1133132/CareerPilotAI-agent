from __future__ import annotations

import agents.supervisor as sup


def test_should_skip_study_plan_when_no_gaps() -> None:
    state = {
        "skill_gaps": {"missing_skills": [], "target_job": {"title": "Analyst"}},
        "routing_decision": {},
    }
    skip, reason = sup.should_skip_study_plan(state)
    assert skip is True
    assert reason == "no_skill_gaps"


def test_should_not_skip_when_high_priority_gaps() -> None:
    state = {
        "skill_gaps": {
            "missing_skills": [{"skill": "Kubernetes", "priority": "high"}],
            "target_job": {"title": "SRE"},
        },
        "routing_decision": {"low_match": True},
    }
    skip, reason = sup.should_skip_study_plan(state)
    assert skip is False
    assert reason == ""


def test_low_match_skips_plan_without_high_gaps() -> None:
    state = {
        "skill_gaps": {
            "missing_skills": [{"skill": "Excel", "priority": "low"}],
            "target_job": {"title": "Analyst"},
        },
        "routing_decision": {"low_match": True},
    }
    skip, reason = sup.should_skip_study_plan(state)
    assert skip is True
    assert reason == "no_high_priority_gaps"


def test_resolve_target_job_from_session() -> None:
    state = {
        "job_matches": [
            {"id": "jd-001", "title": "A"},
            {"id": "jd-002", "title": "B"},
        ],
        "session_memory": {"selected_job_id": "jd-002"},
    }
    job = sup.resolve_target_job(state)
    assert job["title"] == "B"


def test_explain_job_match_mentions_overlap() -> None:
    job = {
        "title": "Data Analyst",
        "score": 0.82,
        "score_method": "qdrant_cosine",
        "skills_required": ["Python", "SQL", "Tableau"],
    }
    profile = {"skills": ["Python", "SQL"], "headline": "Analyst"}
    text = sup.explain_job_match(job, profile, ["Data Analyst"])
    assert "Python" in text
    assert "Tableau" in text


def test_orchestrator_skips_plan_at_gap() -> None:
    from agents.orchestrator import orchestrator

    state = {
        "stage": "gap",
        "skill_gaps": {"missing_skills": []},
        "routing_decision": {},
    }
    out = orchestrator(state)
    assert out["next_agent"] == "resume_optimizer"
    assert out["stage"] == "optimize"
    assert out["skip_study_plan"] is True


def test_orchestrator_optimize_skips_plan_routes_apply() -> None:
    from agents.orchestrator import orchestrator

    state = {"stage": "optimize", "skip_study_plan": True}
    out = orchestrator(state)
    assert out["next_agent"] == "apply_strategist"
    assert out["stage"] == "apply"


def test_orchestrator_optimize_to_plan_when_not_skipped() -> None:
    from agents.orchestrator import orchestrator

    state = {"stage": "optimize", "skip_study_plan": False}
    out = orchestrator(state)
    assert out["next_agent"] == "study_planning"
    assert out["stage"] == "plan"
