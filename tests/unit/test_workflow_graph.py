from __future__ import annotations

from workflow_graph import latest_step_message, phase1_complete


def test_latest_step_message_from_trace() -> None:
    state = {
        "pipeline_trace": [
            {"agent": "resume_analysis", "stage": "intake", "summary": "Parsed resume skills"},
            {"agent": "skill_gap", "stage": "gap", "summary": "Identified 3 skill gaps"},
        ]
    }
    assert latest_step_message(state) == "Identified 3 skill gaps"


def test_phase1_complete_after_skill_gap() -> None:
    state = {
        "pipeline_trace": [
            {"agent": "resume_analysis", "stage": "intake"},
            {"agent": "job_matching", "stage": "match"},
            {"agent": "skill_gap", "stage": "gap"},
        ]
    }
    assert phase1_complete(state) is True

    assert phase1_complete({"pipeline_trace": [{"agent": "job_matching", "stage": "match"}]}) is False
