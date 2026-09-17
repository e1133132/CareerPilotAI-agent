# Observability (logging, metrics, tracing)

## Logging

- Structured logging via Python `logging` (`observability/logging_config.py`).
- `LOG_LEVEL=INFO` (default), `LOG_JSON=true` for JSON lines (GCP Cloud Logging friendly).
- Each HTTP request logs `path`, `status_code`, `duration_ms` with `X-Request-Id` header for correlation.

## Metrics (`GET /metrics`)

In-process counters (reset on container restart):

| Area | Fields |
|------|--------|
| HTTP | total, by_path, by_status, latency avg/p95 |
| LLM | calls, errors, prompt/completion/total tokens, per agent+model |
| Tools | calls, success/failure, success_rate, per tool name |

Disable with `METRICS_ENDPOINT_ENABLED=false`.

Token usage is collected via LangChain callback on all `create_chat_openai()` agents + embedding calls.

Tool success rate is recorded in `skills/learning_rag/fc_tools.py` function-calling loop.

## Tracing (LangSmith)

Configured per the **langsmith-trace** skill (`.agents/skills/langsmith-trace/SKILL.md`).

### Enable locally

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=careerpilot-ai
LANGCHAIN_CALLBACKS_BACKGROUND=false   # recommended for Cloud Run / serverless
```

Legacy `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` still work.

### What gets traced

| Layer | Mechanism |
|-------|-----------|
| LangChain agents (`ChatOpenAI`) | Automatic when env vars are set |
| LangGraph steps | Automatic + `@traceable` on `run_graph_step` |
| Pipeline entry points | `@traceable` on `start_partial_run`, `finish_run_background`, `run_sync` |
| Direct OpenAI calls | `wrap_openai()` on embeddings + input-guard classifier |

Startup calls `setup_tracing()` in `api.py`. Check `GET /health` for `tracing.langsmith_enabled`.

### View traces

1. [LangSmith UI](https://smith.langchain.com) → project `careerpilot-ai` (or your `LANGSMITH_PROJECT`)
2. CLI (optional): `curl -sSL https://raw.githubusercontent.com/langchain-ai/langsmith-cli/main/scripts/install.sh | sh`
   ```bash
   langsmith trace list --project careerpilot-ai --limit 10 --api-key $LANGSMITH_API_KEY
   ```

Product explainability (`pipeline_trace`, `fallback_events`) remains separate — user-facing, not APM.

## GCP

- Cloud Run: default request metrics in console; export logs from JSON stdout.
- Deploy workflow sets `LANGSMITH_TRACING`, `LANGCHAIN_CALLBACKS_BACKGROUND=false`, and `LANGSMITH_API_KEY` from GitHub secrets.
- Wire `/metrics` to a scraper or poll periodically for custom LLM/tool dashboards.
