# User Memory Skill

**Purpose:** Long-term preferences and run history without login (client ID or resume hash).

## Used by
- `api.py` — load/save memory per run; reject-job endpoint
- `agents/job_matching` — preferred roles + filter rejected jobs
- `agents/apply_strategist` — deprioritize rejected roles in strategy

## Services
| Service | File | Description |
|---------|------|-------------|
| `derive_user_id` | `store.py` | Hash client_id or resume text |
| `load_user_memory` / `save_user_memory` | `store.py` | JSON file persistence |
| `merge_run_into_memory` | `store.py` | Append run summary after pipeline |
| `filter_jobs_by_memory` | `store.py` | Demote rejected job IDs |

## Resources
- `data/user_memory/*.json` — one file per user_id

## Reuse
Any agent that should respect user preferences imports `skills.user_memory` — no DB required for demo.
