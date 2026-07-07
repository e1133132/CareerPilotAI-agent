from __future__ import annotations

from skills.learning_rag.web_fetch import (
    merge_learning_resources,
    normalize_web_search_hit,
)


def test_normalize_web_search_hit_maps_langchain_shape() -> None:
    row = normalize_web_search_hit(
        {
            "title": "SQL Tutorial",
            "link": "https://example.com/sql",
            "snippet": "Learn SQL basics with exercises.",
        },
        gap_skills=["SQL"],
        index=0,
    )
    assert row is not None
    assert row["title"] == "SQL Tutorial"
    assert row["source"] == "web"
    assert row["url"] == "https://example.com/sql"
    assert "SQL" in row["skills"]
    assert "Source URL:" in row["content"]


def test_merge_learning_resources_dedupes_by_url() -> None:
    local = [{"id": "lr-1", "title": "Local SQL", "content": "local", "skills": ["SQL"]}]
    web = [
        {
            "id": "web-1",
            "title": "Web SQL",
            "content": "web",
            "skills": ["SQL"],
            "source": "web",
            "url": "https://example.com/a",
        },
        {
            "id": "web-2",
            "title": "Web SQL duplicate",
            "content": "dup",
            "skills": ["SQL"],
            "source": "web",
            "url": "https://example.com/a",
        },
    ]
    merged = merge_learning_resources(local, web)
    assert len(merged) == 2
    assert merged[0]["source"] == "local"
    assert merged[1]["source"] == "web"
