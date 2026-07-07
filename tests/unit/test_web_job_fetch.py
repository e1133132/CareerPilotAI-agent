from __future__ import annotations

from skills.job_retrieval.web_fetch import merge_job_listings, normalize_web_job_hit


def test_normalize_web_job_hit_shape() -> None:
    row = normalize_web_job_hit(
        {"title": "Data Analyst at ExampleCo", "link": "https://example.com/j", "snippet": "SQL Python role"},
        index=0,
    )
    assert row is not None
    assert row["source"] == "web"
    assert row["skills_required"]


def test_merge_job_listings_prefers_internal() -> None:
    internal = [{"id": "jd-1", "title": "Analyst", "source": "internal", "company": "CareerPilot"}]
    web = [{"id": "web-1", "title": "Analyst", "source": "web", "company": "External"}]
    merged = merge_job_listings(internal, web)
    assert len(merged) == 1
    assert merged[0]["source"] == "internal"

    merged2 = merge_job_listings(internal, [{"id": "w2", "title": "Other Role", "source": "web"}])
    assert len(merged2) == 2
