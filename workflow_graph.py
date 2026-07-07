"""
LangGraph workflow for the API pipeline.

Uses interrupt_after=['participant'] so each agent step can flush state to clients
before the next orchestrator/participant cycle continues.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents import orchestrator, participant, summarizer
from agents.supervisor import evaluate_after_gap, merge_routing_decision
from config import settings
from skills.application_pack import build_application_pack
from state import State


def _output_keys_from_part_out(part_out: dict[str, Any]) -> list[str]:
    return sorted(k for k in part_out if k != "messages" and not str(k).startswith("_"))


def _append_trace_for_step(
    state: dict[str, Any],
    *,
    stage: str,
    agent_id: str,
    part_out: dict[str, Any],
    t0: float,
    t1: float,
) -> None:
    step = dict(part_out.pop("_step_explainability", None) or {})
    keys = _output_keys_from_part_out(part_out)
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


def orchestrator_node(state: State) -> dict[str, Any]:
    return orchestrator(dict(state)) or {}


def participant_node(state: State) -> dict[str, Any]:
    next_agent = str(state.get("next_agent") or "resume_analysis")
    stage = str(state.get("stage") or "")
    t0 = time.perf_counter()
    part_out = participant(next_agent, dict(state)) or {}
    t1 = time.perf_counter()

    merged = dict(state)
    _append_trace_for_step(merged, stage=stage, agent_id=next_agent, part_out=part_out, t0=t0, t1=t1)
    merged.update(part_out)
    return {**part_out, "pipeline_trace": merged.get("pipeline_trace"), "fallback_events": merged.get("fallback_events")}


def finalize_node(state: State) -> dict[str, Any]:
    merged = dict(state)
    if merged.get("stage") == "gap" and not merged.get("routing_decision"):
        gap_decision = evaluate_after_gap(merged)
        merged["routing_decision"] = merge_routing_decision(merged, gap_decision)
        merged["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))

    run_id = str(merged.get("run_id") or "")
    merged["application_pack"] = build_application_pack(merged, run_id=run_id or None)
    merged["stage"] = "done"
    merged["next_agent"] = "human"
    return {
        "application_pack": merged.get("application_pack"),
        "stage": "done",
        "next_agent": "human",
        "routing_decision": merged.get("routing_decision"),
        "skip_study_plan": merged.get("skip_study_plan"),
    }


def _route_after_orchestrator(state: State) -> Literal["participant", "finalize"]:
    next_agent = state.get("next_agent") or "human"
    if next_agent == "human":
        return "finalize"
    return "participant"


@lru_cache(maxsize=1)
def get_api_graph():
    builder = StateGraph(State)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("participant", participant_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {"participant": "participant", "finalize": "finalize"},
    )
    builder.add_edge("participant", "orchestrator")
    builder.add_edge("finalize", END)

    checkpointer = MemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["participant"],
    )


def graph_config(*, thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def get_graph_state(thread_id: str) -> dict[str, Any]:
    graph = get_api_graph()
    snap = graph.get_state(graph_config(thread_id=thread_id))
    if snap and snap.values:
        return dict(snap.values)
    return {}


def latest_step_message(state: dict[str, Any]) -> str:
    trace = state.get("pipeline_trace") or []
    if trace:
        last = trace[-1]
        summary = str(last.get("summary") or "").strip()
        agent = str(last.get("agent") or "").strip()
        if summary:
            return summary
        if agent:
            return f"{agent} completed"
    messages = state.get("messages") or []
    if messages:
        return str(messages[-1].get("content") or "")
    return ""


def phase1_complete(state: dict[str, Any]) -> bool:
    trace = state.get("pipeline_trace") or []
    if not trace:
        return False
    last = trace[-1]
    return last.get("agent") == "skill_gap" and last.get("stage") == "gap"


def apply_supervisor_after_gap(state: dict[str, Any]) -> dict[str, Any]:
    merged = dict(state)
    gap_decision = evaluate_after_gap(merged)
    merged["routing_decision"] = merge_routing_decision(merged, gap_decision)
    merged["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))
    return merged


def graph_finished(state: dict[str, Any]) -> bool:
    if str(state.get("stage") or "") == "done":
        return True
    return bool(state.get("application_pack"))


def run_graph_step(*, thread_id: str, initial: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke one graph segment until the next interrupt (after participant) or END."""
    graph = get_api_graph()
    cfg = graph_config(thread_id=thread_id)
    graph.invoke(initial, cfg)
    return get_graph_state(thread_id)


def run_graph_until_phase1(*, thread_id: str, initial: dict[str, Any]) -> dict[str, Any]:
    state = get_graph_state(thread_id)
    if not state:
        state = run_graph_step(thread_id=thread_id, initial=initial)
    while not phase1_complete(state):
        state = run_graph_step(thread_id=thread_id, initial=None)
        if not (state.get("pipeline_trace") or []):
            break
        if graph_finished(state):
            break
    return apply_supervisor_after_gap(state)


def run_graph_until_done(*, thread_id: str) -> dict[str, Any]:
    state = get_graph_state(thread_id)
    while not graph_finished(state):
        prev_len = len(state.get("pipeline_trace") or [])
        state = run_graph_step(thread_id=thread_id, initial=None)
        if graph_finished(state):
            break
        if len(state.get("pipeline_trace") or []) == prev_len and str(state.get("stage") or "") == "done":
            break
    return state


def patch_graph_state(*, thread_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    graph = get_api_graph()
    graph.update_state(graph_config(thread_id=thread_id), patch)
    return get_graph_state(thread_id)


def build_report_text(state: dict[str, Any]) -> str:
    from security.output_filter import filter_report_text

    return filter_report_text(summarizer(state))
