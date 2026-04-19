from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from fastapi import HTTPException

from config import settings

from .llm_injection_guard import combined_user_text_for_llm_guard, llm_input_is_unsafe


_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in (
        r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
        r"disregard\s+(all\s+|the\s+)?(previous|prior)\s+(instructions|rules)",
        r"forget\s+(all\s+|your\s+)?(previous|prior)\s+(instructions|rules)",
        r"override\s+(your\s+|the\s+)?(system|developer|instructions|rules)",
        r"you\s+are\s+now\s+(a|an|the|in)\s+",
        r"\bdeveloper\s+mode\b",
        r"\bjailbreak\b",
        r"\[\s*INST\s*\]",
        r"<\s*IMPERSONATE",
        r"###\s*system\b",
        r"(?m)^\s*(system|assistant)\s*:\s*(ignore|forget|override)",
        r"(?m)^\s*\[(system|admin|root)\]",
    )
)


def _strip_control_chars(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if unicodedata.category(ch) == "Cc" and ch not in ("\t", "\n", "\r"):
            continue
        out.append(ch)
    return "".join(out)


def truncate_resume_text(text: str) -> str:
    """Hard cap resume size at API boundary (also truncated later per-agent)."""
    max_chars = settings.API_RESUME_TEXT_MAX_CHARS
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def prompt_injection_hit_count(text: str) -> int:
    """Count heuristic matches (not a guarantee; complements model-side instructions)."""
    if not (text or "").strip():
        return 0
    hits = 0
    for pat in _PROMPT_INJECTION_PATTERNS:
        if pat.search(text):
            hits += 1
    return hits


def _heuristic_reject_if_injection(text: str) -> None:
    hits = prompt_injection_hit_count(text)
    if hits >= settings.INPUT_GUARD_PROMPT_INJECTION_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail="Input was rejected by automated safety checks. Remove meta-instructions or unusual control text and try again.",
        )


def validate_no_prompt_injection(text: str, *, _field: str = "") -> None:
    """Regex/heuristic gate only (no LLM). Prefer validate_api_user_inputs from HTTP handlers."""
    if not settings.INPUT_GUARD_ENABLED:
        return
    _heuristic_reject_if_injection(text)


def validate_api_user_inputs(resume_text: str, roles: list[str]) -> str:
    """
    Full pipeline: truncate résumé, heuristic checks, optional LLM semantic classifier.

    Returns truncated résumé text for downstream use.
    """
    resume_text = truncate_resume_text(resume_text)
    if not settings.INPUT_GUARD_ENABLED:
        return resume_text

    _heuristic_reject_if_injection(resume_text)
    combined_roles = ", ".join(roles)
    if combined_roles:
        _heuristic_reject_if_injection(combined_roles)

    if settings.INPUT_GUARD_LLM_ENABLED:
        blob = combined_user_text_for_llm_guard(resume_text, roles)
        if blob and llm_input_is_unsafe(blob):
            raise HTTPException(
                status_code=400,
                detail="Input was rejected by semantic safety checks. Remove instructions directed at the AI and try again.",
            )

    return resume_text


def normalize_target_roles(raw: str | None) -> list[str]:
    """Parse comma-separated roles: trim, drop empties, cap count/length, strip risky control chars."""
    if not raw or not str(raw).strip():
        return []
    parts = [p.strip() for p in str(raw).split(",")]
    cleaned: list[str] = []
    for p in parts:
        if not p:
            continue
        p = _strip_control_chars(p).strip()
        if not p:
            continue
        if len(p) > settings.TARGET_ROLE_MAX_CHARS:
            p = p[: settings.TARGET_ROLE_MAX_CHARS]
        cleaned.append(p)
        if len(cleaned) >= settings.TARGET_ROLES_MAX_COUNT:
            break
    return cleaned


def validate_roles_list(roles: Iterable[str]) -> None:
    combined = ", ".join(roles)
    validate_no_prompt_injection(combined, _field="target_roles")
