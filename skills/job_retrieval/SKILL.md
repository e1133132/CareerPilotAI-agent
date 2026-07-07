# Job Retrieval Skill

**Purpose:** Hybrid job retrieval — **company-internal postings** from `jobs.jsonl` plus optional **web listings**, ranked together.

## Used by
- `agents/job_matching` — primary job recommendations
- `agents/apply_strategist` — via `user_memory` filtering on ranked lists

## Services
| Service | File | Description |
|---------|------|-------------|
| `load_jobs` | `dataset.py` | Parse internal `data/jobs.jsonl` (`source: internal`) |
| `fetch_web_job_listings` | `web_fetch.py` | DuckDuckGo public job snippets (`source: web`) |
| `merge_job_listings` | `web_fetch.py` | Dedupe; internal wins on title clash |
| `rank_jobs_semantic` | `rank.py` | Qdrant → keyword on merged corpus |

## Resources
- `data/jobs.jsonl` — CareerPilot-branded internal reqs (`[CareerPilot Internal] …`)
- Web results normalized to same schema with `url`

## Config
- `INTERNAL_COMPANY_NAME` (default `CareerPilot`)
- `JOB_WEB_SEARCH_ENABLED` (default `true`)

## Reuse
Swap internal jsonl for HRIS export; keep web merge for market comparison.
