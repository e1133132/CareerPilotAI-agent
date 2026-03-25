from __future__ import annotations

from io import BytesIO

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
