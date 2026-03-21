from __future__ import annotations

import json
from pathlib import Path


def load_jobs(dataset_path: str) -> list[dict]:
    """
    Loads jobs from a JSONL file with one object per line.
    Required keys (recommended): id, title, description, skills_required
    """
    p = Path(dataset_path)
    if not p.exists():
        raise FileNotFoundError(f"Jobs dataset not found: {p}")

    jobs: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        jobs.append(json.loads(line))
    return jobs

