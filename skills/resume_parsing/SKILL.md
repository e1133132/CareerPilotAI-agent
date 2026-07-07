# Resume Parsing Skill

**Purpose:** Extract plain text from uploaded resume files (PDF or text).

## Used by
- `agents/resume_analysis` — intake step before LLM profile extraction

## Services
| Service | File | Description |
|---------|------|-------------|
| `load_resume_text` | `service.py` | Read PDF or UTF-8 text from disk |

## Resources
- None (stateless I/O; resume bytes come from API upload)

## Reuse
Import from `skills.resume_parsing` in any agent that needs resume file loading without duplicating PDF logic.
