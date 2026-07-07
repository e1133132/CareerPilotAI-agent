from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


@lru_cache(maxsize=8)
def load_jobs(dataset_path: str) -> list[dict[str, Any]]:
    """
    Loads jobs from a JSONL file with one object per line.
    Required keys (recommended): id, title, description, skills_required
    """
    p = Path(dataset_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Jobs dataset not found: {p}")

    jobs: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        jobs.append(json.loads(line))
    return jobs

