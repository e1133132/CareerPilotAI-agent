from __future__ import annotations

from fastapi.testclient import TestClient

import api


client = TestClient(api.app)


def test_health_endpoint() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "service" in data


def test_run_endpoint_requires_file() -> None:
    resp = client.post("/api/careerpilot/run", data={"target_roles": "Data Analyst"})
    assert resp.status_code == 422


def test_run_endpoint_success_with_mocked_pipeline(monkeypatch) -> None:
    def _fake_extract_pdf_text(_: bytes) -> str:
        return "Python SQL React"

    def _fake_run_pipeline(_: dict) -> dict:
        return {
            "state": {
                "candidate_profile": {"name": "Test User", "skills": ["Python", "SQL"]},
                "resume_evidence": {"skills": []},
                "job_matches": [{"id": "jd-001", "title": "Junior Data Analyst"}],
                "skill_gaps": {"missing_skills": [{"skill": "Docker"}]},
                "study_plan": {"timeline_weeks": 6, "phases": []},
            },
            "report_text": "ok",
        }

    monkeypatch.setattr(api, "_extract_pdf_text", _fake_extract_pdf_text)
    monkeypatch.setattr(api, "_run_pipeline", _fake_run_pipeline)

    files = {"resume_file": ("resume.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    data = {"target_roles": "Data Analyst,Backend Developer"}
    resp = client.post("/api/careerpilot/run", files=files, data=data)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["candidate_profile"]["name"] == "Test User"
    assert payload["recommended_jobs"][0]["id"] == "jd-001"
    assert payload["study_plan"]["timeline_weeks"] == 6


def test_run_partial_endpoint_returns_run_id(monkeypatch) -> None:
    # Make sure resume extraction is fast/deterministic in tests.
    def _fake_extract_pdf_text(_: bytes) -> str:
        return "Python SQL React"

    # Only run up to gap: return partial state immediately.
    def _fake_run_pipeline_until_gap(_: dict) -> dict:
        return {
            "stage": "gap",
            "messages": [],
            "candidate_profile": {"name": "Test User", "skills": ["Python", "SQL"]},
            "resume_evidence": {"skills": []},
            "job_matches": [{"id": "jd-001", "title": "Junior Data Analyst"}],
            "skill_gaps": {"missing_skills": [{"skill": "Docker"}]},
        }

    monkeypatch.setattr(api, "_extract_pdf_text", _fake_extract_pdf_text)
    monkeypatch.setattr(api, "_run_pipeline_until_gap", _fake_run_pipeline_until_gap)

    files = {"resume_file": ("resume.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    data = {"target_roles": "Data Analyst"}
    resp = client.post("/api/careerpilot/run_partial", files=files, data=data)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert "run_id" in payload
    assert payload["plan_status"] == "pending"
    assert payload["recommended_jobs"][0]["id"] == "jd-001"
