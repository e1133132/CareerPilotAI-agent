from __future__ import annotations

import agents.apply_strategist as ap
from skills.user_memory import derive_user_id, load_user_memory, merge_run_into_memory, save_user_memory


def test_derive_user_id_stable() -> None:
    a = derive_user_id(client_id="demo-user")
    b = derive_user_id(client_id="demo-user")
    assert a == b
    assert len(a) == 16


def test_apply_strategist_template(monkeypatch) -> None:
    monkeypatch.setattr(ap.settings, "APPLY_STRATEGIST_ENABLED", False)
    state = {
        "candidate_profile": {"skills": ["Python", "SQL"], "headline": "Analyst"},
        "job_matches": [
            {"id": "jd-001", "title": "Data Analyst", "company": "Acme", "score": 0.82, "skills_required": ["SQL", "Python"]},
            {"id": "jd-002", "title": "ML Engineer", "score": 0.55, "skills_required": ["Python", "ML"]},
        ],
        "skill_gaps": {"missing_skills": [{"skill": "Tableau", "priority": "medium"}]},
        "session_memory": {"selected_job_id": "jd-001"},
        "user_memory": {"rejected_job_ids": []},
    }
    out = ap.run(state)
    strategy = out["apply_strategy"]
    assert strategy["priority_applications"]
    assert strategy["cover_letter_hooks"]
    assert strategy["follow_up_checklist"]


def test_user_memory_persist_and_merge(sql_db) -> None:
    uid = "testuser123"
    mem = load_user_memory(uid)
    mem = merge_run_into_memory(
        mem,
        run_id="run1",
        target_roles=["Data Analyst"],
        job_matches=[{"id": "jd-001", "title": "Analyst"}],
        session_memory={"selected_job_id": "jd-001"},
        apply_strategy={"priority_applications": [{"job_id": "jd-001"}]},
    )
    saved = save_user_memory(mem)
    loaded = load_user_memory(uid)
    assert loaded["preferred_target_roles"] == ["Data Analyst"]
    assert loaded["run_history"][-1]["run_id"] == "run1"
    assert saved["user_id"] == uid
