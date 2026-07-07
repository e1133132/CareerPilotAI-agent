# Skills Layer (Reusable Capabilities)

CareerPilot separates **agents** (workflow steps) from **skills** (reusable capability packages).

```
agents/          → orchestrated pipeline steps (thin: call skills + LLM)
skills/          → reusable packages (docs + scripts + resource refs)
data/            → shared corpora (jobs, learning KB, user memory files)
```

## Skill packages

| Skill | Purpose | Key consumers |
|-------|---------|---------------|
| [resume_parsing](resume_parsing/SKILL.md) | PDF/text resume I/O | `resume_analysis` |
| [job_retrieval](job_retrieval/SKILL.md) | Load & rank jobs | `job_matching`, `apply_strategist` |
| [vector_store](vector_store/SKILL.md) | Qdrant index + search | `job_retrieval`, `learning_rag`, `api` |
| [learning_rag](learning_rag/SKILL.md) | RAG + FC tools for learning | `study_planning` |
| [user_memory](user_memory/SKILL.md) | Long-term preferences (JSON) | `api`, `job_matching`, `apply_strategist` |
| [application_pack](application_pack/SKILL.md) | Downloadable apply materials | `api`, frontend |
| [explainability](explainability/SKILL.md) | User-facing rationales | all agents, `api` |

Each folder contains:
- **SKILL.md** — what it does, services, resources, which agents use it
- **Python modules** — callable services (`service.py`, `rank.py`, `store.py`, …)
- **FC tools** (study planning only) — LLM-invokable via `learning_rag/fc_tools.py`

## Naming: services vs FC tools

| Term | Meaning |
|------|---------|
| **Service** | Python function/class called directly by agents or orchestrator (`load_jobs`, `fetch_web_job_listings`, DuckDuckGo adapter in `web_fetch.py`, …) |
| **FC tool** | LangChain `StructuredTool` bound to LLM via `bind_tools()` — only `search_local_learning_kb` and `search_web_learning` |

## Interview talking points

1. **Agents vs skills:** Agents decide *when*; skills implement *how* — same skill can power multiple agents.
2. **Services vs FC tools:** Most skill functions are services (deterministic library calls); only study planning exposes 2 LangChain FC tools the LLM chooses at runtime.
3. **No login memory:** `user_memory` skill persists JSON by hashed client ID — demo-friendly, swappable to DB later.
4. **Extensibility:** Add a new skill folder (e.g. `interview_prep/`) and wire one agent — no need to copy RAG or retrieval code.

## Import examples

```python
from skills import load_jobs, rank_jobs_semantic
from skills.learning_rag import needs_external_resources, run_rag_tool_loop
from skills.user_memory import filter_jobs_by_memory
```
