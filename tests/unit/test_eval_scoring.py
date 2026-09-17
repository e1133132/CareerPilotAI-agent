from __future__ import annotations

from eval.scoring import (
    field_accuracy,
    hit_at_k,
    missing_skills_recall,
    plan_skill_coverage,
    score_case,
    skills_recall,
)


def test_missing_skills_recall_full() -> None:
    output = {"missing_skills": [{"skill": "Docker"}, {"skill": "AWS"}]}
    reference = {"required_missing_skills": ["Docker", "AWS"]}
    assert missing_skills_recall(output, reference) == 1.0


def test_missing_skills_recall_partial() -> None:
    output = {"missing_skills": [{"skill": "Docker"}]}
    reference = {"required_missing_skills": ["Docker", "Kubernetes"]}
    assert missing_skills_recall(output, reference) == 0.5


def test_no_gaps_expected() -> None:
    output = {"missing_skills": []}
    reference = {"required_missing_skills": []}
    scores = field_accuracy(output, reference)
    assert scores["field_pass"] is True


def test_forbidden_text() -> None:
    output = {"missing_skills": [{"skill": "Docker", "reason": "due to gender"}]}
    reference = {"required_missing_skills": ["Docker"], "forbidden_in_output": ["gender"]}
    scores = field_accuracy(output, reference)
    assert scores["forbidden_text_absent"] is False
    assert scores["field_pass"] is False


def test_skills_recall_from_profile() -> None:
    profile = {"skills": ["Python", "SQL", "Git"]}
    reference = {"required_skills": ["Python", "SQL"]}
    assert skills_recall(profile, reference) == 1.0
    assert skills_recall(profile, {"required_skills": ["Python", "Docker"]}) == 0.5


def test_skills_recall_dict_skills() -> None:
    profile = {"skills": [{"skill": "React"}, {"skill": "TypeScript"}]}
    assert skills_recall(profile, {"required_skills": ["React"]}) == 1.0


def test_hit_at_k() -> None:
    matches = [
        {"title": "[CareerPilot Internal] Backend Developer (Python) (JD-004)"},
        {"title": "[CareerPilot Internal] Data Engineer (Junior) (JD-006)"},
    ]
    reference = {"must_include_title_substrings": ["Backend Developer"], "top_k": 5}
    assert hit_at_k(matches, reference) == 1.0
    assert hit_at_k(matches, {"must_include_title_substrings": ["Frontend"], "top_k": 5}) == 0.0


def test_plan_skill_coverage() -> None:
    plan = {
        "phases": [
            {"title": "Learn Docker basics", "description": "Containers and images"},
            {"title": "AWS fundamentals", "description": "IAM and EC2"},
        ]
    }
    assert plan_skill_coverage(plan, {"required_covered_skills": ["Docker", "AWS"]}) == 1.0
    assert plan_skill_coverage(plan, {"required_covered_skills": ["Docker", "Kubernetes"]}) == 0.5


def test_score_case_dispatcher() -> None:
    sg = score_case(
        "skill_gap",
        {"missing_skills": [{"skill": "Docker"}]},
        {"required_missing_skills": ["Docker"]},
    )
    assert sg["field_pass"] is True
    assert sg["primary_metric"] == "missing_skills_recall"

    ra = score_case(
        "resume_analysis",
        {"skills": ["Python", "SQL"]},
        {"required_skills": ["Python"]},
    )
    assert ra["field_pass"] is True
    assert ra["primary_metric"] == "skills_recall"

    jm = score_case(
        "job_matching",
        {"job_matches": [{"title": "Frontend Developer (React)"}]},
        {"must_include_title_substrings": ["Frontend Developer"]},
    )
    assert jm["field_pass"] is True
    assert jm["primary_metric"] == "hit_at_k"

    sp = score_case(
        "study_planning",
        {"phases": [{"title": "React hooks practice"}]},
        {"required_covered_skills": ["React"]},
    )
    assert sp["field_pass"] is True
    assert sp["primary_metric"] == "plan_skill_coverage"
