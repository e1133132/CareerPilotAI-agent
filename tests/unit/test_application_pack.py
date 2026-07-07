from __future__ import annotations

from skills.application_pack import build_application_pack, pack_to_markdown, pack_to_zip_bytes


def test_build_application_pack_merges_sections() -> None:
    state = {
        "candidate_profile": {
            "name": "Alex Chen",
            "headline": "Data analyst with SQL experience",
            "skills": ["Python", "SQL", "Tableau"],
            "experience": [{"role": "Analyst", "company": "Acme", "highlights": ["Built dashboards"]}],
        },
        "job_matches": [
            {
                "id": "jd-001",
                "title": "Data Analyst",
                "company": "Beta Corp",
                "score": 0.82,
                "skills_required": ["SQL", "Python"],
            }
        ],
        "session_memory": {"selected_job_id": "jd-001"},
        "resume_suggestions": {
            "summary_tip": "Lead with SQL impact metrics.",
            "experience_bullets": [
                {
                    "section": "Analyst @ Acme",
                    "original": "Built dashboards",
                    "suggested": "Built dashboards serving 50+ stakeholders.",
                    "rationale": "Add scale",
                }
            ],
            "ats_keywords": ["SQL", "Python"],
        },
        "apply_strategy": {
            "cover_letter_hooks": ["Highlight SQL dashboards for Data Analyst."],
            "follow_up_checklist": ["Apply this week."],
            "timing_advice": "Apply soon.",
        },
        "skill_gaps": {"missing_skills": [{"skill": "Tableau", "priority": "medium"}]},
    }
    pack = build_application_pack(state, run_id="run-test", job_id="jd-001")
    assert pack["job"]["title"] == "Data Analyst"
    assert pack["candidate"]["name"] == "Alex Chen"
    assert pack["resume_section"]["summary_tip"]
    assert "Alex Chen" in pack["cover_letter_draft"]
    assert "Apply this week" in pack["checklist"][0]
    assert "Tableau" in pack["skill_gaps_to_address"]


def test_pack_export_markdown_and_zip() -> None:
    pack = build_application_pack(
        {
            "candidate_profile": {"name": "Sam"},
            "job_matches": [{"id": "j1", "title": "Engineer", "company": "Co"}],
            "resume_suggestions": {"summary_tip": "Tip"},
        },
        run_id="r1",
    )
    md = pack_to_markdown(pack)
    assert "Application Pack" in md
    assert "Sam" in md
    blob = pack_to_zip_bytes(pack)
    assert len(blob) > 100
    assert blob[:2] == b"PK"
