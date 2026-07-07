#!/usr/bin/env python3
"""One-off helper: tag jobs.jsonl and learning_resources.jsonl as company-internal corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path

COMPANY = "CareerPilot"
ROOT = Path(__file__).resolve().parent.parent
JOBS_PATH = ROOT / "data" / "jobs.jsonl"
LR_PATH = ROOT / "data" / "learning_resources.jsonl"


def _strip_internal_prefix(title: str) -> str:
    t = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
    # Remove repeated internal ref suffixes e.g. "(JD-001) (JD-001)"
    t = re.sub(r"(?:\s*\([A-Z0-9-]+\))+$", "", t).strip()
    return t


def brand_jobs() -> None:
    lines: list[str] = []
    for i, line in enumerate(JOBS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        base_title = _strip_internal_prefix(str(row.get("title") or ""))
        req = str(row.get("internal_ref") or row.get("id") or f"REQ-{i:04d}").upper()
        row["company"] = COMPANY
        row["source"] = "internal"
        row["visibility"] = "private"
        row["internal_ref"] = req
        row["title"] = f"[{COMPANY} Internal] {base_title} ({req})"
        lines.append(json.dumps(row, ensure_ascii=False))
    JOBS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Branded {len(lines)} jobs as {COMPANY} internal")


def brand_learning() -> None:
    lines: list[str] = []
    for line in LR_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        base_title = _strip_internal_prefix(str(row.get("title") or ""))
        if not base_title.startswith(f"{COMPANY} L&D"):
            base_title = base_title.replace(f"[{COMPANY} L&D] ", "")
            base_title = re.sub(r"^\[[^\]]+\]\s*", "", base_title).strip()
        row["company"] = COMPANY
        row["source"] = "internal"
        row["visibility"] = "private"
        row["title"] = f"[{COMPANY} L&D] {base_title}"
        lines.append(json.dumps(row, ensure_ascii=False))
    LR_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Branded {len(lines)} learning resources as {COMPANY} internal")


if __name__ == "__main__":
    brand_jobs()
    brand_learning()
