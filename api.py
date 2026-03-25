from __future__ import annotations

from io import BytesIO
import threading
import traceback
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader  # type: ignore

from agents import orchestrator, participant, summarizer
from config import settings
from agents.llm_utils import get_embed_fn
from tools.vector_store_qdrant import warmup_qdrant_indexes

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


@app.on_event("startup")
def _startup_warmup() -> None:
    """
    Best-effort: initialize Qdrant indexes early to reduce first-request latency.
    """
    warmup_qdrant_indexes(get_embed_fn())


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}") from e

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

    while steps < 20:
        steps += 1
        orch_out = orchestrator(state) or {}
        state.update(orch_out)

        next_agent = state.get("next_agent") or "human"
        if next_agent == "human":
            break

        part_out = participant(next_agent, state) or {}
        state.update(part_out)

    report_text = summarizer(state)
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

    # intake -> resume_analysis -> resume
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        state.update(participant(next_agent, state) or {})

    # resume -> job_matching -> match
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        state.update(participant(next_agent, state) or {})

    # match -> skill_gap -> gap
    orch_out = orchestrator(state) or {}
    state.update(orch_out)
    next_agent = state.get("next_agent") or "human"
    if next_agent != "human":
        state.update(participant(next_agent, state) or {})

    return state


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": settings.APP_NAME}


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

    roles = [r.strip() for r in (target_roles or "").split(",") if r.strip()]

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
        "report_text": result.get("report_text") or "",
        "full_state": state,
    }


def _finish_study_plan(run_id: str) -> None:
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)
        if not entry:
            return
        state = entry.get("state") or {}

    try:
        result = _run_pipeline(state)
        final_state = result.get("state") or {}
        report_text = result.get("report_text") or ""
        with _RUN_LOCK:
            if run_id in _RUN_STORE:
                _RUN_STORE[run_id].update(
                    {
                        "status": "done",
                        "state": final_state,
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
                        "error": str(e),
                        "trace": traceback.format_exc(limit=200),
                    }
                )


@app.post("/api/careerpilot/run_partial")
async def run_careerpilot_partial(
    background_tasks: BackgroundTasks,
    resume_file: UploadFile = File(...),
    target_roles: str = Form(default=""),
) -> dict:
    """
    Fast path: returns candidate_profile/job_matches/skill_gaps immediately,
    then computes study_plan in background.
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

    roles = [r.strip() for r in (target_roles or "").split(",") if r.strip()]
    initial_state = {
        "resume_text": resume_text,
        "resume_path": None,
        "target_roles": roles or None,
    }

    partial_state = _run_pipeline_until_gap(initial_state)

    run_id = uuid.uuid4().hex
    with _RUN_LOCK:
        _RUN_STORE[run_id] = {
            "status": "pending",
            "state": partial_state,
            "report_text": "",
            "error": None,
        }

    background_tasks.add_task(_finish_study_plan, run_id)

    return {
        "ok": True,
        "run_id": run_id,
        "plan_status": "pending",
        "candidate_profile": partial_state.get("candidate_profile"),
        "resume_evidence": partial_state.get("resume_evidence"),
        "recommended_jobs": partial_state.get("job_matches"),
        "skill_gaps": partial_state.get("skill_gaps"),
        "study_plan": None,
        "report_text": "",
    }


@app.get("/api/careerpilot/result/{run_id}")
def get_careerpilot_result(run_id: str) -> dict:
    with _RUN_LOCK:
        entry = _RUN_STORE.get(run_id)

    if not entry:
        raise HTTPException(status_code=404, detail="run_id not found")

    status = entry.get("status")
    state = entry.get("state") or {}

    return {
        "ok": True,
        "run_id": run_id,
        "plan_status": status,
        "candidate_profile": state.get("candidate_profile"),
        "resume_evidence": state.get("resume_evidence"),
        "recommended_jobs": state.get("job_matches"),
        "skill_gaps": state.get("skill_gaps"),
        "study_plan": state.get("study_plan"),
        "report_text": entry.get("report_text") or "",
        "error": entry.get("error"),
    }
