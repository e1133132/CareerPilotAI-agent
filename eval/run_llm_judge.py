#!/usr/bin/env python3
"""
Backward-compatible CLI for skill_gap LLM-judge eval.

Prefer:
  PYTHONPATH=. python eval/run_systematic.py --cases eval/cases --skip-judge
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.run_systematic import main as systematic_main  # noqa: E402


def main() -> int:
    # Preserve historical defaults when invoked with no args.
    if len(sys.argv) == 1:
        sys.argv.extend(
            [
                "--cases",
                str(_ROOT / "eval" / "cases" / "skill_gap_cases.jsonl"),
                "--output",
                str(_ROOT / "eval" / "results" / "skill_gap_judge.jsonl"),
            ]
        )
    return systematic_main()


if __name__ == "__main__":
    raise SystemExit(main())
