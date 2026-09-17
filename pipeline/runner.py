from __future__ import annotations

import time
import traceback
import uuid
from typing import Any

from langsmith import traceable

from agents import participant
from agents.supervisor import build_session_memory, evaluate_after_gap, merge_routing_decision
from config import settings
from pipeline.session import run_store
from pipeline.trace import append_trace_for_step
from skills.explainability import build_explainability_block
from skills.user_memory import load_user_memory, merge_run_into_memory, save_user_memory
from workflow_graph import (
    build_report_text,
    get_graph_state,
    graph_finished,
    latest_step_message,
    patch_graph_state,
    run_graph_step,
    run_graph_until_done,
    run_graph_until_phase1,
)


def statuses_from_state(state: dict[str, Any]) -> tuple[str, str, str]:
    skip_plan = bool(state.get("skip_study_plan"))
    trace = state.get("pipeline_trace") or []
    agents = {str(t.get("agent") or "") for t in trace if isinstance(t, dict)}

    if graph_finished(state):
        plan_status = "skipped" if skip_plan else "done"
        resume_status = "skipped" if not settings.RESUME_OPTIMIZER_ENABLED else "done"
        apply_status = "skipped" if not settings.APPLY_STRATEGIST_ENABLED else "done"
        return plan_status, resume_status, apply_status

    plan_status = "skipped" if skip_plan else "pending"
    resume_status = "skipped"
    apply_status = "skipped"
    if not settings.RESUME_OPTIMIZER_ENABLED:
        resume_status = "skipped"
    elif "resume_optimizer" in agents:
        resume_status = "done"
    else:
        resume_status = "pending"

    if skip_plan:
        plan_status = "skipped"
    elif "study_planning" in agents:
        plan_status = "done"
    elif "resume_optimizer" in agents or not settings.RESUME_OPTIMIZER_ENABLED:
        plan_status = "pending"

    if not settings.APPLY_STRATEGIST_ENABLED:
        apply_status = "skipped"
    elif "apply_strategist" in agents:
        apply_status = "done"
    elif plan_status in ("done", "skipped"):
        apply_status = "pending"

    return plan_status, resume_status, apply_status


def response_payload_from_state(
    state: dict[str, Any],
    *,
    run_id: str | None = None,
    plan_status: str | None = None,
    resume_status: str | None = None,
    apply_status: str | None = None,
    report_text: str = "",
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "candidate_profile": state.get("candidate_profile"),
        "resume_evidence": state.get("resume_evidence"),
        "recommended_jobs": state.get("job_matches"),
        "skill_gaps": state.get("skill_gaps"),
        "study_plan": state.get("study_plan"),
        "resume_suggestions": state.get("resume_suggestions"),
        "apply_strategy": state.get("apply_strategy"),
        "application_pack": state.get("application_pack"),
        "user_memory": state.get("user_memory"),
        "user_id": state.get("user_id"),
        "report_text": report_text,
        "routing_decision": state.get("routing_decision"),
        "session_memory": state.get("session_memory"),
        "skip_study_plan": bool(state.get("skip_study_plan")),
        "explainability": build_explainability_block(state),
        "latest_step_message": latest_step_message(state),
        "completed_steps": len(state.get("pipeline_trace") or []),
    }
    if run_id is not None:
        payload["run_id"] = run_id
    if plan_status is not None:
        payload["plan_status"] = plan_status
    if resume_status is not None:
        payload["resume_status"] = resume_status
    if apply_status is not None:
        payload["apply_status"] = apply_status
    if error is not None:
        payload["error"] = error
    return payload


def _persist_user_memory(*, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
    user_id = state.get("user_id")
    if not user_id:
        return state
    mem = load_user_memory(str(user_id))
    mem = merge_run_into_memory(
        mem,
        run_id=run_id,
        target_roles=state.get("target_roles"),
        job_matches=state.get("job_matches") or [],
        session_memory=state.get("session_memory"),
        apply_strategy=state.get("apply_strategy"),
    )
    mem = save_user_memory(mem)
    state = dict(state)
    state["user_memory"] = mem
    return state


@traceable(run_type="chain", name="start_partial_run")
def start_partial_run(*, initial_state: dict[str, Any]) -> tuple[str, dict[str, Any], str, str, str]:
    """
    Run phase-1 agents via LangGraph, register a RunSession, return run metadata.
    Phase-2 continues in finish_run_background().
    """
    run_id = str(initial_state.get("run_id") or uuid.uuid4().hex)
    initial_state = dict(initial_state)
    initial_state["run_id"] = run_id

    partial_state = run_graph_until_phase1(thread_id=run_id, initial=initial_state)
    partial_state = patch_graph_state(
        thread_id=run_id,
        patch={
            "routing_decision": partial_state.get("routing_decision"),
            "skip_study_plan": partial_state.get("skip_study_plan"),
        },
    )

    roles = initial_state.get("target_roles")
    partial_state["session_memory"] = build_session_memory(
        run_id=run_id,
        target_roles=roles if isinstance(roles, list) else None,
        job_matches=partial_state.get("job_matches") or [],
    )
    partial_state = patch_graph_state(
        thread_id=run_id,
        patch={"session_memory": partial_state["session_memory"]},
    )

    skip_plan = bool(partial_state.get("skip_study_plan"))
    plan_status = "skipped" if skip_plan else "pending"
    resume_status = "pending" if settings.RESUME_OPTIMIZER_ENABLED else "skipped"
    apply_status = "pending" if settings.APPLY_STRATEGIST_ENABLED else "skipped"

    run_store.create(
        run_id=run_id,
        state=partial_state,
        plan_status=plan_status,
        resume_status=resume_status,
        apply_status=apply_status,
        latest_step_message=latest_step_message(partial_state),
    )
    return run_id, partial_state, plan_status, resume_status, apply_status


@traceable(run_type="chain", name="finish_run_background")
def finish_run_background(run_id: str) -> None:
    """Continue LangGraph from checkpoint until finalize; sync RunSession after each step."""
    from observability.context import reset_run_id, set_run_id

    run_token = set_run_id(run_id)
    resume_status = "skipped"
    apply_status = "skipped"
    plan_status = "pending"

    try:
        while not graph_finished(get_graph_state(run_id)):
            state = run_graph_step(thread_id=run_id, initial=None)
            plan_status, resume_status, apply_status = statuses_from_state(state)
            run_store.update(
                run_id,
                status=plan_status,
                resume_status=resume_status,
                apply_status=apply_status,
                state=state,
                latest_step_message=latest_step_message(state),
            )
            if graph_finished(state):
                break

        state = get_graph_state(run_id)
        plan_status, resume_status, apply_status = statuses_from_state(state)
        state = _persist_user_memory(run_id=run_id, state=state)
        report_text = build_report_text(state)

        run_store.update(
            run_id,
            status=plan_status,
            resume_status=resume_status,
            apply_status=apply_status,
            state=state,
            report_text=report_text,
            latest_step_message=latest_step_message(state),
            error=None,
            trace=None,
        )
    except Exception as exc:
        run_store.update(
            run_id,
            status="error",
            resume_status=resume_status,
            apply_status="error",
            error=str(exc),
            trace=traceback.format_exc(limit=200),
        )
    finally:
        reset_run_id(run_token)


@traceable(run_type="chain", name="careerpilot_run_sync")
def run_sync(*, initial_state: dict[str, Any]) -> dict[str, Any]:
    """Run the full pipeline synchronously (used by POST /run)."""
    run_id = uuid.uuid4().hex
    initial_state = dict(initial_state)
    initial_state.setdefault("run_id", run_id)
    initial_state.setdefault("stage", "intake")
    initial_state.setdefault("messages", [])
    initial_state.setdefault("pipeline_trace", [])
    initial_state.setdefault("fallback_events", [])

    run_graph_step(thread_id=run_id, initial=initial_state)
    state = run_graph_until_done(thread_id=run_id)
    state = _persist_user_memory(run_id=run_id, state=state)
    report_text = build_report_text(state)
    return {"state": state, "report_text": report_text}


def recompute_skill_gaps(state: dict[str, Any]) -> dict[str, Any]:
    """Re-run skill gap for the selected job; sync LangGraph checkpoint when run_id is set."""
    updated = dict(state)
    merged = dict(updated)
    t0 = time.perf_counter()
    part_out = dict(participant("skill_gap", updated) or {})
    t1 = time.perf_counter()
    append_trace_for_step(
        merged,
        stage="gap",
        agent_id="skill_gap",
        part_out=part_out,
        t0=t0,
        t1=t1,
    )
    updated.update(part_out)
    updated["pipeline_trace"] = merged["pipeline_trace"]
    updated["fallback_events"] = merged["fallback_events"]
    updated["stage"] = "gap"

    gap_decision = evaluate_after_gap(updated)
    updated["routing_decision"] = merge_routing_decision(updated, gap_decision)
    updated["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))

    run_id = str(updated.get("run_id") or "")
    if run_id:
        updated = patch_graph_state(thread_id=run_id, patch=updated)
    return updated
