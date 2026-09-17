# CareerPilot AI — Architecture

This document describes how the backend is organized after consolidating on a single LangGraph pipeline.

## Layers

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **API** | `api.py` | HTTP, auth, PDF upload, JSON responses |
| **Pipeline** | `pipeline/` | Run sessions, LangGraph runner, trace helpers |
| **Workflow** | `workflow_graph.py` | LangGraph StateGraph (orchestrator ↔ participant loop) |
| **Agents** | `agents/` | Thin agent steps; call LangChain LLM/tools |
| **Skills** | `skills/` | Reusable retrieval, RAG, memory, export logic |
| **State** | `state.py` | TypedDict schema for one run's business fields |

## One pipeline, two API modes

Both endpoints use the **same LangGraph workflow**:

- `POST /api/careerpilot/run_partial` — phase-1 returns fast; phase-2 continues in background
- `POST /api/careerpilot/run` — waits until the graph reaches `finalize`

Entry points live in `pipeline/runner.py`:

- `start_partial_run()` + `finish_run_background()` — async partial flow
- `run_sync()` — full synchronous run

## State: what lives where

**`state.py` (business State)** — CareerPilot-owned schema: resume, job matches, gaps, plan, routing, trace. Used by all agents regardless of orchestration.

**LangGraph checkpoint** — graph engine snapshot keyed by `run_id` (thread_id). Used to resume the orchestrator/participant loop between steps.

**`RunSession` (`pipeline/session.py`)** — API-facing record for frontend polling (`GET /result/{run_id}`). Holds business `state` plus API metadata (`plan_status`, `report_text`, errors).

Rule: agents mutate business fields; the runner syncs graph checkpoint → `RunSession` after each step.

## LangGraph vs LangChain

- **LangGraph** (`workflow_graph.py`): multi-agent routing, conditional skips, interrupt-after-participant for stepwise API responses.
- **LangChain** (inside `agents/*.py`): `ChatOpenAI`, messages, function-calling tools, DuckDuckGo search adapters.

## Request flow (web UI)

1. Browser uploads PDF → `run_partial`
2. `start_partial_run()` runs graph until skill_gap completes
3. API returns profile / jobs / gaps + `run_id`
4. Background task `finish_run_background()` continues graph (optimize → plan → apply → finalize)
5. Frontend polls `/result/{run_id}` reading `RunSession`

## Extending the system

- **New agent**: add `agents/foo.py`, register in `agents/participant.py`, extend routing in `agents/orchestrator.py`
- **New skill**: add under `skills/` with `SKILL.md`
- **New pipeline step**: update graph nodes/edges in `workflow_graph.py` — no duplicate loop in `api.py`

## Removed complexity

Previously the project maintained a legacy orchestrator loop in `api.py` behind `USE_LANGGRAPH_PIPELINE`. That dual path is removed; LangGraph is the only pipeline driver.
