# Vector Store Skill

**Purpose:** Shared Qdrant indexing and vector search for jobs and learning resources.

## Used by
- `skills/job_retrieval/rank.py` — `search_jobs`
- `skills/learning_rag/retrieval.py` — `search_learning_resources`
- `api.py` — `warmup_qdrant_indexes` on startup

## Services
| Service | File | Description |
|---------|------|-------------|
| `warmup_qdrant_indexes` | `qdrant.py` | Best-effort index warmup |
| `search_jobs` | `qdrant.py` | Top-k job vector search |
| `search_learning_resources` | `qdrant.py` | Top-k learning snippet search |

## Resources
- `data/.qdrant_index_meta.json` — file-hash versioning for re-index

## Reuse
Centralizes vector DB logic so retrieval skills stay focused on ranking and RAG formatting.
