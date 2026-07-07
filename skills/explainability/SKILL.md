# Explainability Skill

**Purpose:** User-facing rationales and API `explainability` blocks — no extra LLM calls.

## Used by
- All core agents (`resume_analysis`, `job_matching`, `skill_gap`, `study_planning`, …)
- `api.py` — `build_explainability_block` on responses

## Services
| Service | File | Description |
|---------|------|-------------|
| `resume_rationale_from_outputs` | `trace.py` | Why profile looks this way |
| `job_matching_rationale` | `trace.py` | Why these jobs ranked |
| `skill_gap_rationale` | `trace.py` | Gap analysis summary |
| `study_plan_rationale` | `trace.py` | Plan grounding summary |
| `build_explainability_block` | `trace.py` | Full API explainability payload |

## Resources
- None (derived from existing structured agent outputs)

## Reuse
Cross-cutting observability skill — attach to any new agent for consistent UX.
