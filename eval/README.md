# CareerPilot evaluation sets

Two complementary layers:

| Layer | Purpose | When it runs |
|-------|---------|--------------|
| **Promptfoo** | Prompt **contract** / JSON shape / light assertions | CI `promptfoo-evals` |
| **Systematic (labeled)** | **Correctness** vs golden references (recall / hit@k / coverage) | CI `systematic-evals` (`--skip-judge`) + local optional LLM judge |

LangSmith is **runtime tracing**, not part of this eval CI.

## 1. Promptfoo (contract / stability)

**Configs** (`promptfoo/`):

| File | Agent |
|------|--------|
| `resume_analysis_promptfooconfig.yaml` | Resume extraction JSON contract |
| `job_matching_promptfooconfig.yaml` | Job ranking prompts |
| `promptfooconfig.yaml` | Skill gap |
| `study_planning_promptfooconfig.yaml` | Study plan |

**Run locally** (needs `OPENAI_API_KEY`):

```bash
cd career_pilot_ai
npx promptfoo@latest eval -c promptfoo/resume_analysis_promptfooconfig.yaml
npx promptfoo@latest view
```

**CI**: job `promptfoo-evals` when `OPENAI_API_KEY` secret is set.

## 2. Systematic labeled eval (correctness)

**Runner:** `eval/run_systematic.py`

**Cases** (`eval/cases/*_cases.jsonl`):

| File | Agent | Primary metric |
|------|--------|----------------|
| `resume_analysis_cases.jsonl` | resume_analysis | `skills_recall` |
| `job_matching_cases.jsonl` | job_matching | `hit_at_k` |
| `skill_gap_cases.jsonl` | skill_gap | `missing_skills_recall` |
| `study_planning_cases.jsonl` | study_planning | `plan_skill_coverage` |

Each line:

```json
{"id": "...", "agent": "...", "description": "...", "state": {}, "reference": {}}
```

**Scoring:** `eval/scoring.py` → `score_case(agent, output, reference)`  
**Optional judge:** `agents/evaluator.py` + `eval/rubrics/*_rubric.md` (not in CI by default)

### Run locally

```bash
cd career_pilot_ai

# Field metrics only (same as CI — cheaper)
PYTHONPATH=. python eval/run_systematic.py --cases eval/cases --skip-judge

# With LLM judge (2× LLM cost per case)
PYTHONPATH=. python eval/run_systematic.py --cases eval/cases

# Single agent file
PYTHONPATH=. python eval/run_systematic.py --cases eval/cases/skill_gap_cases.jsonl --skip-judge
```

Stability env (also set by the runner / CI):

```bash
JOB_WEB_SEARCH_ENABLED=false
STUDY_PLAN_WEB_SEARCH_ENABLED=false
STUDY_PLAN_USE_FUNCTION_CALLING=false
OPENAI_TEMPERATURE=0
```

Results: `eval/results/systematic.jsonl` (exit code `2` if any `field_pass` fails).

Legacy entrypoint: `python eval/run_llm_judge.py` (defaults to skill_gap cases + judge).

**CI**: job `systematic-evals` runs `--skip-judge` when `OPENAI_API_KEY` is set.

### Adding a new labeled case

1. Append a JSONL row under `eval/cases/<agent>_cases.jsonl` with `state` + `reference`.
2. For job_matching, ensure `must_include_title_substrings` match titles in `data/jobs.jsonl`.
3. Add/adjust unit tests in `tests/unit/test_eval_scoring.py` if you introduce new reference keys.
4. CI picks up new `*_cases.jsonl` files automatically when running `--cases eval/cases`.

## 3. Pytest

- `tests/unit/` — including scorer unit tests (no live LLM)
- `tests/integration/` — API contract, adversarial, bias stability

## 4. What is still not covered

- End-to-end full pipeline golden suite every PR
- Retrieval recall@k on a dedicated Qdrant golden set
- LangSmith experiments/datasets in CI
- Evaluator agent inside production LangGraph (offline only)
