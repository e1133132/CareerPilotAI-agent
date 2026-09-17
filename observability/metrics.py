from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class MetricsStore:
    """In-process counters for API latency, LLM tokens, and tool calls (Cloud Run friendly)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests_total = 0
        self._request_durations_ms: list[float] = []
        self._requests_by_path: dict[str, int] = defaultdict(int)
        self._requests_by_status: dict[str, int] = defaultdict(int)
        self._llm_calls = 0
        self._llm_errors = 0
        self._llm_tokens_prompt = 0
        self._llm_tokens_completion = 0
        self._llm_tokens_total = 0
        self._llm_by_agent: dict[str, int] = defaultdict(int)
        self._tool_calls = 0
        self._tool_success = 0
        self._tool_failure = 0
        self._tool_by_name: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})
        self._started_at = time.time()

    def record_request(self, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._requests_total += 1
            self._requests_by_path[path] += 1
            self._requests_by_status[str(status_code)] += 1
            self._request_durations_ms.append(duration_ms)
            if len(self._request_durations_ms) > 5000:
                self._request_durations_ms = self._request_durations_ms[-2500:]

    def record_llm_usage(
        self,
        *,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: float | None = None,
        error: bool = False,
    ) -> None:
        with self._lock:
            if error:
                self._llm_errors += 1
            else:
                self._llm_calls += 1
            self._llm_tokens_prompt += max(0, prompt_tokens)
            self._llm_tokens_completion += max(0, completion_tokens)
            self._llm_tokens_total += max(0, total_tokens)
            key = f"{agent}:{model}"
            self._llm_by_agent[key] += 1

    def record_tool_call(self, tool_name: str, success: bool, duration_ms: float | None = None) -> None:
        with self._lock:
            self._tool_calls += 1
            bucket = self._tool_by_name[tool_name]
            if success:
                self._tool_success += 1
                bucket["success"] += 1
            else:
                self._tool_failure += 1
                bucket["failure"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = list(self._request_durations_ms)
            tool_rate = (
                round(self._tool_success / self._tool_calls, 4) if self._tool_calls else None
            )
            return {
                "uptime_seconds": round(time.time() - self._started_at, 2),
                "requests": {
                    "total": self._requests_total,
                    "by_path": dict(self._requests_by_path),
                    "by_status": dict(self._requests_by_status),
                    "latency_ms_avg": round(sum(durations) / len(durations), 2) if durations else None,
                    "latency_ms_p95": _percentile(durations, 95),
                },
                "llm": {
                    "calls": self._llm_calls,
                    "errors": self._llm_errors,
                    "tokens_prompt": self._llm_tokens_prompt,
                    "tokens_completion": self._llm_tokens_completion,
                    "tokens_total": self._llm_tokens_total,
                    "calls_by_agent_model": dict(self._llm_by_agent),
                },
                "tools": {
                    "calls": self._tool_calls,
                    "success": self._tool_success,
                    "failure": self._tool_failure,
                    "success_rate": tool_rate,
                    "by_tool": {k: dict(v) for k, v in self._tool_by_name.items()},
                },
            }


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * pct / 100))
    return round(ordered[idx], 2)


metrics_store = MetricsStore()
