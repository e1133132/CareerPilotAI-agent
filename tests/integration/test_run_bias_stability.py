from __future__ import annotations

from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


def test_run_bias_counterfactual_is_stable(monkeypatch) -> None:
    def _fake_extract_pdf_text(raw_bytes: bytes) -> str:
        return raw_bytes.decode("utf-8")

    def _fake_run_pipeline(state: dict) -> dict:
        resume_text = (state.get("resume_text") or "").lower()
        skills = []
        if "python" in resume_text:
            skills.append("Python")
        if "sql" in resume_text:
            skills.append("SQL")

        required = ["Python", "SQL", "Docker"]
        missing = [s for s in required if s not in skills]
        final_state = {
            "candidate_profile": {"name": "Test User", "skills": skills},
            "resume_evidence": {"skills": []},
            "job_matches": [{"id": "jd-001", "title": "Backend Engineer", "skills_required": required}],
            "skill_gaps": {
                "target_job": {"id": "jd-001", "title": "Backend Engineer"},
                "matched_strengths": [s for s in skills if s in required],
                "missing_skills": [
                    {
                        "skill": s,
                        "priority": "high",
                        "reason": "Listed in job requirements but not found in resume skills.",
                    }
                    for s in missing
                ],
                "notes": [],
            },
            "study_plan": {
                "timeline_weeks": 6,
                "phases": [{"name": "Foundation", "weeks": [1, 2], "topics": missing, "practice": ["Daily practice"]}],
                "resources": [],
                "notes": [],
            },
        }
        return {"state": final_state, "report_text": "ok"}

    monkeypatch.setattr(api, "_extract_pdf_text", _fake_extract_pdf_text)
    monkeypatch.setattr(api, "_run_pipeline", _fake_run_pipeline)

    base_resume_text = "Python SQL projects and internship experience."
    sensitive_variant = (
        "Python SQL projects and internship experience. "
        "Gender: female, Ethnicity: Malay, Age: 21."
    )

    files_a = {"resume_file": ("resume.pdf", base_resume_text.encode("utf-8"), "application/pdf")}
    files_b = {"resume_file": ("resume.pdf", sensitive_variant.encode("utf-8"), "application/pdf")}
    data = {"target_roles": "Backend Developer"}

    resp_a = client.post("/api/careerpilot/run", files=files_a, data=data)
    resp_b = client.post("/api/careerpilot/run", files=files_b, data=data)

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    payload_a = resp_a.json()
    payload_b = resp_b.json()

    assert payload_a["candidate_profile"]["skills"] == payload_b["candidate_profile"]["skills"]
    assert payload_a["recommended_jobs"] == payload_b["recommended_jobs"]
    assert payload_a["skill_gaps"] == payload_b["skill_gaps"]
    assert payload_a["study_plan"] == payload_b["study_plan"]
