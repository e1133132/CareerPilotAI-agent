from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings
from .llm_utils import create_chat_openai, extract_json_block, safe_json_loads

AGENT_ID = "evaluator"
DEFAULT_MODEL = settings.OPENAI_MODEL_EVALUATOR

_RUBRICS_DIR = Path(__file__).resolve().parent.parent / "eval" / "rubrics"


def load_rubric(agent_type: str) -> str:
    path = _RUBRICS_DIR / f"{agent_type}_rubric.md"
    if not path.is_file():
        raise FileNotFoundError(f"Rubric not found: {path}")
    return path.read_text(encoding="utf-8")


def run_judge(
    *,
    agent_type: str,
    input_payload: dict[str, Any],
    candidate_output: dict[str, Any],
    reference: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    LLM-as-judge: score a single agent output against a rubric (+ optional reference).
    Returns structured verdict JSON from the judge model.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    rubric = load_rubric(agent_type)
    system = f"""You are an independent evaluator for CareerPilot AI. You do NOT rewrite the candidate output.
Score strictly using the rubric below. Use reference labels only when provided.

RUBRIC:
{rubric}
"""

    user = json.dumps(
        {
            "agent_under_test": agent_type,
            "input": input_payload,
            "candidate_output": candidate_output,
            "reference": reference or {},
        },
        ensure_ascii=False,
    )

    llm = create_chat_openai(
        AGENT_ID,
        model=model,
        temperature=0,
        request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    raw = str(resp.content).strip()
    payload = safe_json_loads(raw)
    if payload is None:
        payload = safe_json_loads(extract_json_block(raw) or "") or {"raw": raw, "pass": False}
    if not isinstance(payload, dict):
        payload = {"pass": False, "raw": raw}
    return payload
