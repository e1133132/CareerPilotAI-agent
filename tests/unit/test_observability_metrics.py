from __future__ import annotations

from observability.metrics import metrics_store


def test_metrics_request_and_llm() -> None:
    metrics_store.record_request("/api/test", 200, 42.5)
    metrics_store.record_llm_usage(
        agent="resume_analysis",
        model="gpt-5-nano",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    metrics_store.record_tool_call("search_local_learning_kb", success=True, duration_ms=12.0)
    metrics_store.record_tool_call("search_web_learning", success=False, duration_ms=5.0)

    snap = metrics_store.snapshot()
    assert snap["requests"]["total"] >= 1
    assert snap["llm"]["tokens_total"] >= 150
    assert snap["tools"]["calls"] >= 2
    assert snap["tools"]["failure"] >= 1
