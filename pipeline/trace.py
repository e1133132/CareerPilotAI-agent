from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def output_keys_from_part_out(part_out: dict[str, Any]) -> list[str]:
    return sorted(k for k in part_out if k != "messages" and not str(k).startswith("_"))


def append_trace_for_step(
    state: dict[str, Any],
    *,
    stage: str,
    agent_id: str,
    part_out: dict[str, Any],
    t0: float,
    t1: float,
) -> None:
    """Record one agent step into pipeline_trace / fallback_events on state."""
    step = dict(part_out.pop("_step_explainability", None) or {})
    keys = output_keys_from_part_out(part_out)
    trace = list(state.get("pipeline_trace") or [])
    fallback_events = list(state.get("fallback_events") or [])
    trace.append(
        {
            "stage": stage,
            "agent": agent_id,
            "summary": step.get("summary") or (f"Updated: {', '.join(keys)}" if keys else "step complete"),
            "rationale": step.get("rationale") or "",
            "output_keys": keys,
            "duration_ms": round((t1 - t0) * 1000, 2),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    state["pipeline_trace"] = trace
    fe = step.get("fallback_event")
    if isinstance(fe, dict):
        fallback_events.append(fe)
    for extra in step.get("fallback_events") or []:
        if isinstance(extra, dict):
            fallback_events.append(extra)
    state["fallback_events"] = fallback_events
    logger.info(
        "pipeline_step agent=%s stage=%s duration_ms=%s",
        agent_id,
        stage,
        round((t1 - t0) * 1000, 2),
        extra={"agent": agent_id, "duration_ms": round((t1 - t0) * 1000, 2)},
    )
