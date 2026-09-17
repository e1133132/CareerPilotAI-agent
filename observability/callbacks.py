from __future__ import annotations

import logging
import os
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from observability.metrics import metrics_store

logger = logging.getLogger(__name__)


class LLMUsageCallbackHandler(BaseCallbackHandler):
    """Records token usage and latency from LangChain LLM responses."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self._start: float | None = None

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        self._start = time.perf_counter()

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        model = _model_from_kwargs(kwargs)
        metrics_store.record_llm_usage(
            agent=self.agent_name,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            error=True,
        )
        logger.warning("llm_error agent=%s model=%s error=%s", self.agent_name, model, error)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        duration_ms = None
        if self._start is not None:
            duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
        model = _model_from_kwargs(kwargs)
        usage = _extract_token_usage(response)
        metrics_store.record_llm_usage(
            agent=self.agent_name,
            model=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            duration_ms=duration_ms,
        )
        logger.info(
            "llm_call agent=%s model=%s tokens_total=%s duration_ms=%s",
            self.agent_name,
            model,
            usage["total_tokens"],
            duration_ms,
            extra={
                "agent": self.agent_name,
                "duration_ms": duration_ms,
                "tokens_total": usage["total_tokens"],
            },
        )


def _model_from_kwargs(kwargs: dict[str, Any]) -> str:
    invocation = kwargs.get("invocation_params") or {}
    if isinstance(invocation, dict):
        return str(invocation.get("model") or invocation.get("model_name") or "unknown")
    return "unknown"


def _extract_token_usage(response: Any) -> dict[str, int]:
    prompt = 0
    completion = 0
    total = 0
    llm_output = getattr(response, "llm_output", None) or {}
    if isinstance(llm_output, dict):
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if isinstance(usage, dict):
            prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            total = int(usage.get("total_tokens") or prompt + completion)
    if total == 0:
        for gen_list in getattr(response, "generations", []) or []:
            for gen in gen_list or []:
                info = getattr(gen, "generation_info", None) or {}
                if isinstance(info, dict):
                    usage = info.get("token_usage") or info.get("usage") or {}
                    if isinstance(usage, dict):
                        prompt += int(usage.get("prompt_tokens") or 0)
                        completion += int(usage.get("completion_tokens") or 0)
                        total += int(usage.get("total_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total if total else prompt + completion,
    }


def get_llm_callbacks(agent_name: str) -> list[BaseCallbackHandler]:
    return [LLMUsageCallbackHandler(agent_name=agent_name)]
