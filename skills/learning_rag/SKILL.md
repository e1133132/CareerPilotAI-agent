# Learning RAG Skill

**Purpose:** Retrieve learning snippets and expose LLM function-calling tools for study planning.

## Used by
- `agents/study_planning` — RAG context + optional FC tool loop

## Services
| Service | File | Description |
|---------|------|-------------|
| `load_learning_resources` | `retrieval.py` | Load `data/learning_resources.jsonl` |
| `retrieve_learning_context` | `retrieval.py` | Top-k snippet retrieval |
| `build_study_rag_query` | `retrieval.py` | Build query from profile + gaps |
| `fetch_web_learning_resources` | `web_fetch.py` | DuckDuckGo web supplement |
| `merge_learning_resources` | `web_fetch.py` | Merge local + web rows |

## LLM Function-Calling Tools (agent-invokable)
| FC Tool | File | Description |
|---------|------|-------------|
| `search_local_learning_kb` | `fc_tools.py` | LLM calls local KB search |
| `search_web_learning` | `fc_tools.py` | LLM calls web search |
| `run_rag_tool_loop` | `fc_tools.py` | Orchestrates FC rounds |

## Resources
- `data/learning_resources.jsonl` — CareerPilot L&D internal snippets (`[CareerPilot L&D] …`)
- Web rows via `web_fetch.py` when study plan FC / legacy path enables search

## Depends on
- `skills/vector_store` — optional Qdrant path

## Reuse
Future agents (e.g. interview prep, certification planner) can import this skill for the same RAG + FC pattern.
