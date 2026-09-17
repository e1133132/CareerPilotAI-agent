#!/usr/bin/env python3
"""
Systematic multi-agent eval: labeled cases + field metrics (+ optional LLM judge).

Usage (from career_pilot_ai/):
  PYTHONPATH=. python eval/run_systematic.py --cases eval/cases --skip-judge
  PYTHONPATH=. python eval/run_systematic.py --cases eval/cases/skill_gap_cases.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv(override=True)

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _apply_eval_stability_env() -> None:
    """Prefer deterministic retrieval paths during systematic eval."""
    os.environ["JOB_WEB_SEARCH_ENABLED"] = "false"
    os.environ["STUDY_PLAN_WEB_SEARCH_ENABLED"] = "false"
    os.environ["STUDY_PLAN_USE_FUNCTION_CALLING"] = "false"
    os.environ.setdefault("OPENAI_TEMPERATURE", "0")
    # Force off so .env QDRANT_ENABLED=true does not spam version warnings mid-eval.
    os.environ["QDRANT_ENABLED"] = "false"
    os.environ["QDRANT_AUTO_START"] = "false"


_apply_eval_stability_env()

from agents import job_matching, resume_analysis, skill_gap, study_planning  # noqa: E402
from agents.evaluator import run_judge  # noqa: E402
from eval.scoring import score_case  # noqa: E402

_AGENT_RUNNERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "resume_analysis": resume_analysis.run,
    "job_matching": job_matching.run,
    "skill_gap": skill_gap.run,
    "study_planning": study_planning.run,
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def resolve_case_files(cases_path: Path) -> list[Path]:
    if cases_path.is_file():
        return [cases_path]
    if cases_path.is_dir():
        files = sorted(cases_path.glob("*_cases.jsonl"))
        if not files:
            raise FileNotFoundError(f"No *_cases.jsonl under {cases_path}")
        return files
    raise FileNotFoundError(f"Cases path not found: {cases_path}")


def run_agent(agent_name: str, state: dict[str, Any]) -> dict[str, Any]:
    runner = _AGENT_RUNNERS.get(agent_name)
    if runner is None:
        raise ValueError(f"No runner registered for agent: {agent_name}")
    return runner(dict(state))


def extract_agent_output(agent_name: str, agent_result: dict[str, Any]) -> dict[str, Any]:
    if agent_name == "skill_gap":
        out = agent_result.get("skill_gaps") or {}
        return out if isinstance(out, dict) else {"raw": out}
    if agent_name == "resume_analysis":
        profile = agent_result.get("candidate_profile") or {}
        return profile if isinstance(profile, dict) else {"raw": profile}
    if agent_name == "job_matching":
        matches = agent_result.get("job_matches") or []
        return {"job_matches": matches if isinstance(matches, list) else []}
    if agent_name == "study_planning":
        plan = agent_result.get("study_plan") or {}
        return plan if isinstance(plan, dict) else {"raw": plan}
    return dict(agent_result)


def evaluate_case(case: dict[str, Any], *, skip_judge: bool = False) -> dict[str, Any]:
    case_id = str(case.get("id") or "")
    agent_name = str(case.get("agent") or "")
    state = case.get("state") or {}
    reference = case.get("reference") or {}

    agent_result = run_agent(agent_name, state)
    output = extract_agent_output(agent_name, agent_result)
    field_scores = score_case(agent_name, output, reference)

    judge_verdict: dict[str, Any] = {}
    if not skip_judge:
        judge_verdict = run_judge(
            agent_type=agent_name,
            input_payload=state,
            candidate_output=output,
            reference=reference,
        )

    judge_pass = bool(judge_verdict.get("pass")) if judge_verdict else None
    overall_pass = field_scores["field_pass"] and (judge_pass is not False if judge_verdict else True)

    return {
        "id": case_id,
        "description": case.get("description"),
        "agent": agent_name,
        "output": output,
        "field_scores": field_scores,
        "judge": judge_verdict,
        "pass": overall_pass,
    }


def run_suite(
    *,
    cases_path: Path,
    output_path: Path | None,
    skip_judge: bool,
) -> tuple[list[dict[str, Any]], int]:
    files = resolve_case_files(cases_path)
    results: list[dict[str, Any]] = []

    for file_path in files:
        cases = load_cases(file_path)
        print(f"\n=== {file_path.name} ({len(cases)} cases) ===", flush=True)
        for case in cases:
            print(f"  Evaluating {case.get('id')} …", flush=True)
            results.append(evaluate_case(case, skip_judge=skip_judge))

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results, _print_summary(results, skip_judge=skip_judge, output_path=output_path)


def _print_summary(
    results: list[dict[str, Any]],
    *,
    skip_judge: bool,
    output_path: Path | None,
) -> int:
    n = len(results)
    if n == 0:
        print("No cases evaluated.", file=sys.stderr)
        return 1

    pass_n = sum(1 for r in results if r.get("pass"))
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_agent[str(row.get("agent") or "unknown")].append(row)

    print("\n=== Summary ===")
    print(f"Cases: {n}")
    print(f"Overall pass: {pass_n}/{n} ({100 * pass_n / n:.1f}%)")
    for agent, rows in sorted(by_agent.items()):
        a_pass = sum(1 for r in rows if r.get("pass"))
        primary_vals = [
            float((r.get("field_scores") or {}).get("primary_value") or 0.0) for r in rows
        ]
        avg_primary = sum(primary_vals) / len(primary_vals)
        metric_name = (rows[0].get("field_scores") or {}).get("primary_metric") or "primary"
        print(
            f"  {agent}: {a_pass}/{len(rows)} pass | avg {metric_name}={avg_primary:.2%}"
        )
        if not skip_judge:
            j_pass = sum(1 for r in rows if r.get("judge") and r["judge"].get("pass"))
            print(f"    judge pass: {j_pass}/{len(rows)}")
    if output_path is not None:
        print(f"Results written to: {output_path}")
    return 0 if pass_n == n else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run systematic multi-agent eval suite")
    parser.add_argument(
        "--cases",
        type=Path,
        default=_ROOT / "eval" / "cases",
        help="JSONL file or directory of *_cases.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_ROOT / "eval" / "results" / "systematic.jsonl",
        help="Write per-case results JSONL",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Only run agents + field metrics (no LLM judge calls)",
    )
    args = parser.parse_args(argv)

    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        print("ERROR: OPENAI_API_KEY is required.", file=sys.stderr)
        return 1

    try:
        _, code = run_suite(
            cases_path=args.cases,
            output_path=args.output,
            skip_judge=args.skip_judge,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
