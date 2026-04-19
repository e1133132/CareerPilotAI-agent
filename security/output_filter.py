"""
Post-process LLM-visible text before it reaches users or downstream state.

- Heuristic normalization and high-confidence unsafe-pattern redaction (no API call).
- Optional OpenAI Moderation API for unsafe categories (same API key as chat).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx

from config import settings
from utils import debug

# Static job rankings from dataset: skip all string filtering (avoid false positives on JD text).
_SKIP_SUBTREE_KEYS = frozenset({"job_matches"})

# Reflected jailbreak / meta-instruction leakage in model output (high precision).
_OUTPUT_META_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in (
        r"(?m)^\s*ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"\bI\s+must\s+not\s+follow\s+(my\s+)?original\s+instructions\b",
        r"\bas\s+a\s+language\s+model\b.*\b(?:ignore|override|disregard)\b",
    )
)

# Stereotyping in hiring advice (backup when moderation is off; small set to limit false positives).
_STEREOTYPE_HINT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:because|since)\s+(?:they\s+are|he\s+is|she\s+is)\s+(?:a\s+)?(?:bad|poor|weak)\s+fit\s+due\s+to\s+(?:race|gender|ethnic|national|religion)",
        r"\b(?:don'?t|do\s+not)\s+hire\s+(?:people|anyone)\s+from\s+(?:africa|asia|women|men)\b",
    )
)

_REPLACEMENT_BLOCKED = "[Removed by output safety filter.]"


def _strip_control_chars(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if unicodedata.category(ch) == "Cc" and ch not in ("\t", "\n", "\r"):
            continue
        out.append(ch)
    return "".join(out)


def _heuristic_block_or_clean(s: str) -> tuple[str, bool]:
    """
    Returns (text, blocked). If blocked, replace with _REPLACEMENT_BLOCKED.
    """
    if not s:
        return s, False
    scan = s
    max_scan = settings.OUTPUT_FILTER_HEURISTIC_MAX_SCAN_CHARS
    if len(scan) > max_scan:
        scan = scan[:max_scan]
    t = unicodedata.normalize("NFKC", _strip_control_chars(scan))
    for pat in _OUTPUT_META_PATTERNS:
        if pat.search(t):
            return "", True
    for pat in _STEREOTYPE_HINT_PATTERNS:
        if pat.search(t):
            return "", True
    full = unicodedata.normalize("NFKC", _strip_control_chars(s))
    if len(full) > 200 and len(set(full)) < 8:
        return "", True
    return unicodedata.normalize("NFKC", _strip_control_chars(s)), False


def _moderate_chunks(strings: list[str]) -> list[bool]:
    """Return True per string if moderation says content is unsafe."""
    if not strings:
        return []
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        debug("OUTPUT_FILTER moderation skipped: no OPENAI_API_KEY", "output_filter")
        return [False] * len(strings)

    url = "https://api.openai.com/v1/moderations"
    payload: dict[str, Any] = {"input": strings}

    try:
        with httpx.Client(timeout=min(30.0, settings.OPENAI_REQUEST_TIMEOUT_SECONDS + 10)) as client:
            r = client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        debug(f"moderation request failed: {e}", "output_filter")
        if settings.OUTPUT_FILTER_OPENAI_FAIL_OPEN:
            return [False] * len(strings)
        return [True] * len(strings)

    results = data.get("results") or []
    out = [bool(item.get("flagged")) for item in results]

    if len(out) != len(strings):
        debug("moderation results length mismatch; fail-open", "output_filter")
        if settings.OUTPUT_FILTER_OPENAI_FAIL_OPEN:
            return [False] * len(strings)
        return [True] * len(strings)
    return out


def _collect_strings(obj: Any, *, path: str, acc: list[tuple[str, str]]) -> None:
    if isinstance(obj, str):
        acc.append((path, obj))
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            _collect_strings(v, path=f"{path}[{i}]" if path else f"[{i}]", acc=acc)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _SKIP_SUBTREE_KEYS:
                continue
            p = f"{path}.{k}" if path else str(k)
            _collect_strings(v, path=p, acc=acc)
        return


def _apply_string_map(obj: Any, path: str, mapping: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return mapping.get(path, obj)
    if isinstance(obj, list):
        return [_apply_string_map(v, f"{path}[{i}]" if path else f"[{i}]", mapping) for i, v in enumerate(obj)]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _SKIP_SUBTREE_KEYS:
                out[k] = v
                continue
            p = f"{path}.{k}" if path else str(k)
            out[k] = _apply_string_map(v, p, mapping)
        return out
    return obj


def filter_agent_output(part_out: dict[str, Any], *, agent_id: str = "") -> dict[str, Any]:
    """
    Sanitize agent return payload (returns new structure with filtered strings).

    Entire subtree `job_matches` is left unchanged (dataset-sourced JD text).
    """
    if not settings.OUTPUT_FILTER_ENABLED:
        return part_out
    if not part_out:
        return part_out

    pairs: list[tuple[str, str]] = []
    _collect_strings(part_out, path="", acc=pairs)

    replacements: dict[str, str] = {}
    mod_pair_indices: list[int] = []

    for i, (path, s) in enumerate(pairs):
        cleaned, blocked = _heuristic_block_or_clean(s)
        if blocked:
            replacements[path] = _REPLACEMENT_BLOCKED
            continue
        replacements[path] = cleaned
        if settings.OUTPUT_FILTER_OPENAI_MODERATION and len(cleaned) <= settings.OUTPUT_FILTER_MAX_STRING_CHARS:
            mod_pair_indices.append(i)

    if settings.OUTPUT_FILTER_OPENAI_MODERATION and mod_pair_indices:
        to_send = [replacements[pairs[i][0]] for i in mod_pair_indices]
        flagged_all: list[bool] = []
        batch = settings.OUTPUT_FILTER_MODERATION_BATCH_SIZE
        for start in range(0, len(to_send), batch):
            flagged_all.extend(_moderate_chunks(to_send[start : start + batch]))
        for j, is_bad in enumerate(flagged_all):
            if is_bad:
                path = pairs[mod_pair_indices[j]][0]
                replacements[path] = _REPLACEMENT_BLOCKED

    out = _apply_string_map(part_out, "", replacements)
    debug(f"output_filter agent={agent_id} strings={len(pairs)}", "output_filter")
    return out


def filter_report_text(report: str) -> str:
    """Last-resort pass on the final report string."""
    if not settings.OUTPUT_FILTER_ENABLED or not report:
        return report
    cleaned, blocked = _heuristic_block_or_clean(report)
    if blocked:
        return _REPLACEMENT_BLOCKED
    if settings.OUTPUT_FILTER_OPENAI_MODERATION:
        sample = cleaned[: settings.OUTPUT_FILTER_MAX_STRING_CHARS]
        flags = _moderate_chunks([sample])
        if flags and flags[0]:
            return _REPLACEMENT_BLOCKED
    return cleaned
