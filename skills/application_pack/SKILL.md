# Application Pack Skill

**Purpose:** Assemble resume tweaks, cover letter, follow-up email, and checklist into downloadable materials (human-in-the-loop apply — no auto-submit).

## Used by
- `api.py` — build after pipeline completes; download endpoints
- Frontend — Application Pack card with ZIP / Markdown download

## Services
| Service | File | Description |
|---------|------|-------------|
| `build_application_pack` | `builder.py` | Merge state into structured pack |
| `pack_to_markdown` | `export.py` | Single-file markdown export |
| `pack_to_zip_bytes` | `export.py` | ZIP with cover letter, resume tips, checklist |

## Inputs (from shared state)
- `candidate_profile`, `resume_suggestions`, `apply_strategy`, `skill_gaps`, `job_matches`, optional `job_id`

## Reuse
Any workflow that produces strategy + resume tips can call this skill for export without a new LLM call.
