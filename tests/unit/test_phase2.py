from __future__ import annotations

import agents.resume_optimizer as ro
import agents.supervisor as sup
from skills.learning_rag import needs_external_resources


def test_needs_external_resources_high_gap() -> None:
    gaps = {"missing_skills": [{"skill": "Kubernetes", "priority": "high"}]}
    need, reason = needs_external_resources(gaps)
    assert need is True
    assert reason == "high_priority_gaps"


def test_needs_external_resources_skips_trivial() -> None:
    gaps = {"missing_skills": [{"skill": "Excel", "priority": "low"}]}
    need, reason = needs_external_resources(gaps)
    assert need is False
    assert reason == "gaps_trivial"


def test_resume_optimizer_template_fallback(monkeypatch) -> None:
    monkeypatch.setattr(ro.settings, "RESUME_OPTIMIZER_ENABLED", True)

    def _fake_import(name, *args, **kwargs):
        if name in ("langchain_core.messages", "langchain_openai"):
            raise ModuleNotFoundError(name)
        return __import__(name, *args, **kwargs)

    import builtins

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    state = {
        "candidate_profile": {
            "skills": ["Python"],
            "experience": [{"role": "Engineer", "company": "Acme", "highlights": ["Built APIs"]}],
        },
        "job_matches": [{"id": "j1", "title": "Backend Dev", "skills_required": ["Python", "Docker"]}],
        "session_memory": {"selected_job_id": "j1"},
    }
    out = ro.run(state)
    suggestions = out["resume_suggestions"]
    assert suggestions["target_job"]["title"] == "Backend Dev"
    assert suggestions["experience_bullets"]
    assert "Docker" in suggestions["ats_keywords"]


def test_resume_optimizer_no_job() -> None:
    out = ro.run({"candidate_profile": {}, "job_matches": []})
    assert "No target job" in out["resume_suggestions"]["notes"][0]
