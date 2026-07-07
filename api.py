from __future__ import annotations

from io import BytesIO
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pypdf import PdfReader  # type: ignore

from agents import orchestrator, participant, summarizer
from agents.supervisor import build_session_memory, evaluate_after_gap, merge_routing_decision
from config import settings
from agents.llm_utils import get_embed_fn
from security.input_guard import normalize_target_roles, validate_api_user_inputs
from security.output_filter import filter_report_text
from skills.vector_store import warmup_qdrant_indexes
from skills.explainability import build_explainability_block
from skills.user_memory import (
    derive_user_id,
    load_user_memory,
    merge_run_into_memory,
    save_user_memory,
)
from skills.application_pack import (
    build_application_pack,
    pack_to_markdown,
    pack_to_zip_bytes,
    zip_download_filename,
)
from skills.auth import authenticate_user, create_access_token, register_user, verify_access_token
from db import init_database
from workflow_graph import (
    build_report_text,
    get_graph_state,
    graph_finished,
    latest_step_message,
    patch_graph_state,
    run_graph_step,
    run_graph_until_phase1,
)

load_dotenv(override=True)


app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory run store (dev/prototype).
# For production + multiple workers, consider Redis or a persistent store.
_RUN_STORE: dict[str, dict[str, Any]] = {}
_RUN_LOCK = threading.Lock()


class SelectJobRequest(BaseModel):
    job_id: str = Field(min_length=1)


class RejectJobRequest(BaseModel):
    job_id: str = Field(min_length=1)


class UserMemoryPatch(BaseModel):
    preferred_target_roles: list[str] | None = None
    rejected_job_ids: list[str] | None = None
    saved_job_ids: list[str] | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


def _optional_bearer_token(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    if not settings.AUTH_ENABLED:
        return None
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        if settings.AUTH_REQUIRED:
            raise HTTPException(status_code=401, detail="Authorization Bearer token required")
        return None
    token = raw.split(" ", 1)[1].strip()
    try:
        return verify_access_token(token)
    except Exception as exc:
        if settings.AUTH_REQUIRED:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
        return None


def _resolve_user_id(
    *,
    resume_text: str,
    client_id: str | None,
    account: dict[str, Any] | None,
) -> tuple[str, str | None]:
    account_uid = str(account.get("user_id") or "") if account else None
    username = str(account.get("username") or "") if account else None
    user_id = derive_user_id(
        client_id=client_id or None,
        resume_text=resume_text,
        account_user_id=account_uid,
    )
    return user_id, username


def _statuses_from_state(state: dict[str, Any]) -> tuple[str, str, str]:
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


def _response_payload_from_state(
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
        "pipeline_driver": "langgraph" if settings.USE_LANGGRAPH_PIPELINE else "orchestrator",
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


def _background_warmup_qdrant() -> None:
    """
    Best-effort background warmup to avoid blocking container startup.
    """
    try:
        warmup_qdrant_indexes(get_embed_fn())
    except Exception:
        # Warmup is optional; ignore failures here and continue serving traffic.
        return


@app.on_event("startup")
def _startup_warmup() -> None:
    """
    Best-effort: init SQL tables + start Qdrant warmup asynchronously.
    """
    if settings.DATABASE_AUTO_CREATE_TABLES:
        init_database()
    threading.Thread(target=_background_warmup_qdrant, daemon=True).start()


def _output_keys_from_part_out(part_out: dict[str, Any]) -> list[str]:
    return sorted(
        k
        for k in part_out
        if k != "messages" and not str(k).startswith("_")
    )


def _append_trace_for_step(
    trace: list[dict[str, Any]],
    fallback_events: list[dict[str, Any]],
    *,
    stage: str,
    agent_id: str,
    part_out: dict[str, Any],
    t0: float,
    t1: float,
) -> None:
    step = part_out.pop("_step_explainability", None) or {}
    keys = _output_keys_from_part_out(part_out)
    trace.append(
        {
            "stage": stage,
            "agent": agent_id,
            "summary": step.get("summary")
            or (f"Updated: {', '.join(keys)}" if keys else "step complete"),
            "rationale": step.get("rationale") or "",
            "output_keys": keys,
            "duration_ms": round((t1 - t0) * 1000, 2),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    fe = step.get("fallback_event")
    if isinstance(fe, dict):
        fallback_events.append(fe)
    for extra in step.get("fallback_events") or []:
        if isinstance(extra, dict):
            fallback_events.append(extra)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}") from e
#CICD DEMO
    pages_text: list[str] = []
    for page in reader.pages:
        try:
            t = (page.extract_text() or "").strip() 
        except Exception:
            t = ""
        if t:
            pages_text.append(t)
    return "\n\n".join(pages_text).strip()


def _run_pipeline(state: dict) -> dict:
    steps = 0
    state = dict(state)
    state.setdefault("stage", "intake")
    state.setdefault("messages", [])

    trace: list[dict[str, Any]] = list(state.get("pipeline_trace") or [])
    fallback_events: list[dict[str, Any]] = list(state.get("fallback_events") or [])

    while steps < 20:
        steps += 1
        orch_out = orchestrator(state) or {}
        state.update(orch_out)

        next_agent = state.get("next_agent") or "human"
        if next_agent == "human":
            break

        stage = str(state.get("stage") or "")
        t0 = time.perf_counter()
        part_out = participant(next_agent, state) or {}
        t1 = time.perf_counter()
        _append_trace_for_step(
            trace,
            fallback_events,
            stage=stage,
            agent_id=next_agent,
            part_out=part_out,
            t0=t0,
            t1=t1,
        )
        state.update(part_out)

    state["pipeline_trace"] = trace
    state["fallback_events"] = fallback_events

    state["application_pack"] = build_application_pack(state, run_id=state.get("run_id"))

    report_text = filter_report_text(summarizer(state))
    return {"state": state, "report_text": report_text}


def _run_pipeline_until_gap(state: dict) -> dict:
    """
    Run the pipeline up to (and including) skill gap analysis.

    We intentionally stop before study_planning to make sure the API can respond fast.
    """
    # Make sure we have the baseline fields expected by orchestrator/agents.
    state = dict(state)
    state.setdefault("stage", "intake")
    state.setdefault("messages", [])

    trace: list[dict[str, Any]] = []
    fallback_events: list[dict[str, Any]] = []

    # intake -> resume_analysis -> resume
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        stage = str(state.get("stage") or "")
        t0 = time.perf_counter()
        part_out = participant(next_agent, state) or {}
        t1 = time.perf_counter()
        _append_trace_for_step(
            trace, fallback_events, stage=stage, agent_id=next_agent, part_out=part_out, t0=t0, t1=t1
        )
        state.update(part_out)

    # resume -> job_matching -> match
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        stage = str(state.get("stage") or "")
        t0 = time.perf_counter()
        part_out = participant(next_agent, state) or {}
        t1 = time.perf_counter()
        _append_trace_for_step(
            trace, fallback_events, stage=stage, agent_id=next_agent, part_out=part_out, t0=t0, t1=t1
        )
        state.update(part_out)

    # match -> skill_gap -> gap
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        stage = str(state.get("stage") or "")
        t0 = time.perf_counter()
        part_out = participant(next_agent, state) or {}
        t1 = time.perf_counter()
        _append_trace_for_step(
            trace, fallback_events, stage=stage, agent_id=next_agent, part_out=part_out, t0=t0, t1=t1
        )
        state.update(part_out)

    # gap -> supervisor decision (do not advance stage; background worker runs plan)
    gap_decision = evaluate_after_gap(state)
    state["routing_decision"] = merge_routing_decision(state, gap_decision)
    state["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))

    state["pipeline_trace"] = trace
    state["fallback_events"] = fallback_events

    return state


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": settings.APP_NAME}


@app.post("/api/auth/register")
def auth_register(body: RegisterRequest) -> dict:
    if not settings.AUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Auth is disabled")
    try:
        user = register_user(username=body.username, password=body.password, email=body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = create_access_token(user_id=user["user_id"], username=user["username"])
    return {"ok": True, "token": token, "user": user}


@app.post("/api/auth/login")
def auth_login(body: LoginRequest) -> dict:
    if not settings.AUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Auth is disabled")
    try:
        user = authenticate_user(username=body.username, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    token = create_access_token(user_id=user["user_id"], username=user["username"])
    return {"ok": True, "token": token, "user": user}


@app.get("/api/auth/me")
def auth_me(account: dict[str, Any] | None = Depends(_optional_bearer_token)) -> dict:
    if not account:
        raise HTTPException(status_code=401, detail="Not authenticated")
    mem = load_user_memory(str(account["user_id"]))
    return {"ok": True, "user": account, "user_memory": mem}


@app.post("/api/careerpilot/run")
async def run_careerpilot(
    resume_file: UploadFile = File(...),
    target_roles: str = Form(default=""),
) -> dict:
    if resume_file.filename and not resume_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf resume files are supported")

    raw_bytes = await resume_file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded resume_file is empty")

    resume_text = _extract_pdf_text(raw_bytes)
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. If it is scanned, OCR is required.",
        )

    roles = normalize_target_roles(target_roles)
    resume_text = validate_api_user_inputs(resume_text, roles)

    result = _run_pipeline(
        {
            "resume_text": resume_text,
            "resume_path": None,
            "target_roles": roles or None,
        }
    )
    state = result.get("state") or {}

    return {
        "ok": True,
        "candidate_profile": state.get("candidate_profile"),
        "resume_evidence": state.get("resume_evidence"),
        "recommended_jobs": state.get("job_matches"),
        "skill_gaps": state.get("skill_gaps"),
        "study_plan": state.get("study_plan"),
        "resume_suggestions": state.get("resume_suggestions"),
        "apply_strategy": state.get("apply_strategy"),
        "application_pack": state.get("application_pack"),
        "report_text": result.get("report_text") or "",
        "explainability": build_explainability_block(state),
        "full_state": state,
    }


def _finish_phase2_graph(run_id: str) -> None:
    """Background LangGraph: continue from checkpoint until finalize; update store after each step."""
    resume_status = "skipped"
    apply_status = "skipped"
    plan_status = "pending"

    try:
        while not graph_finished(get_graph_state(run_id)):
            state = run_graph_step(thread_id=run_id, initial=None)
            plan_status, resume_status, apply_status = _statuses_from_state(state)
            with _RUN_LOCK:
                if run_id in _RUN_STORE:
                    _RUN_STORE[run_id].update(
                        {
                            "status": plan_status,
                            "resume_status": resume_status,
                            "apply_status": apply_status,
                            "state": state,
                            "latest_step_message": latest_step_message(state),
                        }
                    )
            if graph_finished(state):
                break

        state = get_graph_state(run_id)
        plan_status, resume_status, apply_status = _statuses_from_state(state)

        user_id = state.get("user_id")
        if user_id:
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
            state["user_memory"] = mem

        report_text = build_report_text(state)

        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update(
                    {
                        "status": plan_status,
                        "resume_status": resume_status,
                        "apply_status": apply_status,
                        "state": state,
                        "report_text": report_text,
                        "latest_step_message": latest_step_message(state),
                        "error": None,
                    }
                )
    except Exception as e:
        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update(
                    {
                        "status": "error",
                        "resume_status": resume_status,
                        "apply_status": "error",
                        "error": str(e),
                        "trace": traceback.format_exc(limit=200),
                    }
                )


def _finish_phase2(run_id: str) -> None:
    """Background: resume optimizer → study plan (optional) → apply strategist → persist memory."""
    if settings.USE_LANGGRAPH_PIPELINE:
        _finish_phase2_graph(run_id)
        return
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)
        if not entry:
            return
        state = dict(entry.get("state") or {})

    resume_status = "skipped"
    apply_status = "skipped"

    try:
        trace: list[dict[str, Any]] = list(state.get("pipeline_trace") or [])
        fallback_events: list[dict[str, Any]] = list(state.get("fallback_events") or [])

        if settings.RESUME_OPTIMIZER_ENABLED:
            t0 = time.perf_counter()
            resume_out = participant("resume_optimizer", state) or {}
            t1 = time.perf_counter()
            _append_trace_for_step(
                trace, fallback_events, stage="optimize", agent_id="resume_optimizer",
                part_out=resume_out, t0=t0, t1=t1,
            )
            state.update(resume_out)
            resume_status = "done"

        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update({"state": state, "resume_status": resume_status})

        if not state.get("skip_study_plan"):
            t0 = time.perf_counter()
            plan_out = participant("study_planning", state) or {}
            t1 = time.perf_counter()
            _append_trace_for_step(
                trace, fallback_events, stage="plan", agent_id="study_planning",
                part_out=plan_out, t0=t0, t1=t1,
            )
            state.update(plan_out)
            plan_status = "done"
        else:
            plan_status = "skipped"

        if settings.APPLY_STRATEGIST_ENABLED:
            apply_status = "pending"
            with _RUN_LOCK:
                if run_id in _RUN_STORE:
                    _RUN_STORE[run_id].update({"apply_status": apply_status, "status": plan_status})

            t0 = time.perf_counter()
            apply_out = participant("apply_strategist", state) or {}
            t1 = time.perf_counter()
            _append_trace_for_step(
                trace, fallback_events, stage="apply", agent_id="apply_strategist",
                part_out=apply_out, t0=t0, t1=t1,
            )
            state.update(apply_out)
            apply_status = "done"
        else:
            apply_status = "skipped"

        pack = build_application_pack(state, run_id=run_id)
        state["application_pack"] = pack

        user_id = state.get("user_id")
        if user_id:
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
            state["user_memory"] = mem

        state["stage"] = "done"
        state["pipeline_trace"] = trace
        state["fallback_events"] = fallback_events
        report_text = filter_report_text(summarizer(state))

        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update(
                    {
                        "status": plan_status,
                        "resume_status": resume_status,
                        "apply_status": apply_status,
                        "state": state,
                        "report_text": report_text,
                        "error": None,
                    }
                )
    except Exception as e:
        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update(
                    {
                        "status": "error",
                        "resume_status": resume_status,
                        "apply_status": "error",
                        "error": str(e),
                        "trace": traceback.format_exc(limit=200),
                    }
                )


def _finish_study_plan(run_id: str) -> None:
    """Legacy hook: delegates to phase-2 background worker."""
    _finish_phase2(run_id)


def _recompute_skill_gaps(state: dict[str, Any]) -> dict[str, Any]:
    """Re-run skill gap for the currently selected job in session memory."""
    trace: list[dict[str, Any]] = list(state.get("pipeline_trace") or [])
    fallback_events: list[dict[str, Any]] = list(state.get("fallback_events") or [])

    stage = "gap"
    t0 = time.perf_counter()
    part_out = participant("skill_gap", state) or {}
    t1 = time.perf_counter()
    _append_trace_for_step(
        trace,
        fallback_events,
        stage=stage,
        agent_id="skill_gap",
        part_out=part_out,
        t0=t0,
        t1=t1,
    )

    updated = dict(state)
    updated.update(part_out)
    updated["stage"] = "gap"
    updated["pipeline_trace"] = trace
    updated["fallback_events"] = fallback_events

    gap_decision = evaluate_after_gap(updated)
    updated["routing_decision"] = merge_routing_decision(updated, gap_decision)
    updated["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))
    return updated


@app.post("/api/careerpilot/run_partial")
async def run_careerpilot_partial(
    background_tasks: BackgroundTasks,
    resume_file: UploadFile = File(...),
    target_roles: str = Form(default=""),
    client_id: str = Form(default=""),
    account: dict[str, Any] | None = Depends(_optional_bearer_token),
) -> dict:
    """
    Fast path: returns candidate_profile/job_matches/skill_gaps after phase-1 agents,
    then continues phase-2 via LangGraph interrupt steps (or legacy background worker).
    """
    if resume_file.filename and not resume_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf resume files are supported")

    raw_bytes = await resume_file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded resume_file is empty")

    resume_text = _extract_pdf_text(raw_bytes)
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. If it is scanned, OCR is required.",
        )

    roles = normalize_target_roles(target_roles)
    resume_text = validate_api_user_inputs(resume_text, roles)

    user_id, username = _resolve_user_id(resume_text=resume_text, client_id=client_id or None, account=account)
    user_memory = load_user_memory(user_id)

    run_id = uuid.uuid4().hex
    initial_state: dict[str, Any] = {
        "resume_text": resume_text,
        "resume_path": None,
        "target_roles": roles or None,
        "user_id": user_id,
        "user_memory": user_memory,
        "run_id": run_id,
        "stage": "intake",
        "messages": [],
        "pipeline_trace": [],
        "fallback_events": [],
    }
    if username:
        initial_state["account_username"] = username

    if settings.USE_LANGGRAPH_PIPELINE:
        partial_state = run_graph_until_phase1(thread_id=run_id, initial=initial_state)
        partial_state = patch_graph_state(
            thread_id=run_id,
            patch={
                "routing_decision": partial_state.get("routing_decision"),
                "skip_study_plan": partial_state.get("skip_study_plan"),
            },
        )
    else:
        partial_state = _run_pipeline_until_gap(initial_state)

    partial_state["session_memory"] = build_session_memory(
        run_id=run_id,
        target_roles=roles,
        job_matches=partial_state.get("job_matches") or [],
    )
    if settings.USE_LANGGRAPH_PIPELINE:
        partial_state = patch_graph_state(
            thread_id=run_id,
            patch={"session_memory": partial_state["session_memory"]},
        )

    skip_plan = bool(partial_state.get("skip_study_plan"))
    plan_status = "skipped" if skip_plan else "pending"
    resume_status = "pending" if settings.RESUME_OPTIMIZER_ENABLED else "skipped"
    apply_status = "pending" if settings.APPLY_STRATEGIST_ENABLED else "skipped"

    with _RUN_LOCK:
        _RUN_STORE[run_id] = {
            "status": plan_status,
            "resume_status": resume_status,
            "apply_status": apply_status,
            "state": partial_state,
            "report_text": "",
            "latest_step_message": latest_step_message(partial_state),
            "error": None,
        }

    background_tasks.add_task(_finish_phase2, run_id)

    return _response_payload_from_state(
        partial_state,
        run_id=run_id,
        plan_status=plan_status,
        resume_status=resume_status,
        apply_status=apply_status,
    )


@app.get("/api/careerpilot/result/{run_id}")
def get_careerpilot_result(run_id: str) -> dict:
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)

    if not entry:
        raise HTTPException(status_code=404, detail="run_id not found")

    status = entry.get("status")
    state = entry.get("state") or {}

    return _response_payload_from_state(
        state,
        run_id=run_id,
        plan_status=status,
        resume_status=entry.get("resume_status"),
        apply_status=entry.get("apply_status"),
        report_text=entry.get("report_text") or "",
        error=entry.get("error"),
    ) | {
        "latest_step_message": entry.get("latest_step_message") or latest_step_message(state),
    }


@app.get("/api/careerpilot/session/{run_id}/application_pack")
def get_application_pack(
    run_id: str,
    job_id: str | None = Query(default=None),
    format: str = Query(default="json"),
) -> Any:
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "markdown", "zip"):
        raise HTTPException(status_code=400, detail="format must be json, markdown, or zip")

    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)

    if not entry:
        raise HTTPException(status_code=404, detail="run_id not found")

    state = dict(entry.get("state") or {})
    resume_status = str(entry.get("resume_status") or "")
    if resume_status == "pending":
        raise HTTPException(status_code=409, detail="Resume suggestions still generating")

    pack = build_application_pack(state, run_id=run_id, job_id=job_id)
    state["application_pack"] = pack
    with _RUN_LOCK:
        if run_id in _RUN_STORE:
            _RUN_STORE[run_id]["state"] = state

    if fmt == "json":
        return {"ok": True, "run_id": run_id, "application_pack": pack}

    if fmt == "markdown":
        body = pack_to_markdown(pack)
        fname = zip_download_filename(pack).replace(".zip", ".md")
        return Response(
            content=body.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    zip_bytes = pack_to_zip_bytes(pack)
    fname = zip_download_filename(pack)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/careerpilot/users/{user_id}/memory")
def get_user_memory(user_id: str) -> dict:
    mem = load_user_memory(user_id)
    return {"ok": True, "user_id": user_id, "user_memory": mem}


@app.patch("/api/careerpilot/users/{user_id}/memory")
def patch_user_memory(user_id: str, body: UserMemoryPatch) -> dict:
    mem = load_user_memory(user_id)
    if body.preferred_target_roles is not None:
        mem["preferred_target_roles"] = body.preferred_target_roles
    if body.rejected_job_ids is not None:
        mem["rejected_job_ids"] = body.rejected_job_ids
    if body.saved_job_ids is not None:
        mem["saved_job_ids"] = body.saved_job_ids
    mem = save_user_memory(mem)
    return {"ok": True, "user_id": user_id, "user_memory": mem}


@app.post("/api/careerpilot/session/{run_id}/reject_job")
async def reject_job_for_session(run_id: str, body: RejectJobRequest) -> dict:
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)

    if not entry:
        raise HTTPException(status_code=404, detail="run_id not found")

    state = dict(entry.get("state") or {})
    user_id = str(state.get("user_id") or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="No user_id on this run")

    mem = load_user_memory(user_id)
    rejected = list(mem.get("rejected_job_ids") or [])
    job_id = body.job_id.strip()
    if job_id not in rejected:
        rejected.append(job_id)
    mem["rejected_job_ids"] = rejected
    mem = save_user_memory(mem)
    state["user_memory"] = mem

    with _RUN_LOCK:
        _RUN_STORE[run_id]["state"] = state

    return _response_payload_from_state(
        state,
        run_id=run_id,
        plan_status=entry.get("status"),
        resume_status=entry.get("resume_status"),
        apply_status=entry.get("apply_status"),
        report_text=entry.get("report_text") or "",
    )


@app.post("/api/careerpilot/session/{run_id}/select_job")
async def select_job_for_session(
    run_id: str,
    body: SelectJobRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)

    if not entry:
        raise HTTPException(status_code=404, detail="run_id not found")

    state = dict(entry.get("state") or {})
    matches = state.get("job_matches") or []
    job_id = body.job_id.strip()
    selected = next((j for j in matches if str(j.get("id") or "") == job_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail="job_id not found in this run")

    session = dict(state.get("session_memory") or {})
    session["selected_job_id"] = job_id
    session["selected_job_title"] = str(selected.get("title") or "")
    session["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state["session_memory"] = session

    updated_state = _recompute_skill_gaps(state)
    skip_plan = bool(updated_state.get("skip_study_plan"))
    new_status = entry.get("status")

    if skip_plan:
        new_status = "skipped"
        updated_state["study_plan"] = None
    elif new_status in ("skipped", "done") and not skip_plan:
        new_status = "pending"
        updated_state["study_plan"] = None

    with _RUN_LOCK:
        _RUN_STORE[run_id] = {
            "status": new_status,
            "resume_status": "pending" if settings.RESUME_OPTIMIZER_ENABLED else entry.get("resume_status", "skipped"),
            "apply_status": "pending" if settings.APPLY_STRATEGIST_ENABLED else entry.get("apply_status", "skipped"),
            "state": updated_state,
            "report_text": entry.get("report_text") or "" if new_status == "done" else "",
            "error": None,
        }

    background_tasks.add_task(_finish_phase2, run_id)

    return _response_payload_from_state(
        updated_state,
        run_id=run_id,
        plan_status=new_status,
        resume_status="pending" if settings.RESUME_OPTIMIZER_ENABLED else entry.get("resume_status"),
        apply_status="pending" if settings.APPLY_STRATEGIST_ENABLED else entry.get("apply_status"),
        report_text=entry.get("report_text") or "" if new_status == "done" else "",
    )
