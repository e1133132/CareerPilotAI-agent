from __future__ import annotations

import json
from typing import Any

from config import settings
from skills.learning_rag.retrieval import (
    build_study_rag_query,
    format_rag_context_for_prompt,
    load_learning_resources,
    retrieve_learning_context,
)
from skills.learning_rag.web_fetch import fetch_web_learning_resources, merge_learning_resources


def _default_learning_resources_path() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent.parent.parent / "data" / "learning_resources.jsonl")


def _load_kb_rows() -> tuple[list[dict[str, Any]], str]:
    import os

    default_path = _default_learning_resources_path()
    env_path = (os.getenv("LEARNING_RESOURCES_PATH") or "").strip()
    primary = env_path or default_path
    rows = load_learning_resources(primary)
    if rows:
        for r in rows:
            r.setdefault("source", "internal")
            r.setdefault("company", settings.INTERNAL_COMPANY_NAME)
        return rows, primary
    if primary != default_path:
        rows = load_learning_resources(default_path)
        if rows:
            for r in rows:
                r.setdefault("source", "internal")
                r.setdefault("company", settings.INTERNAL_COMPANY_NAME)
            return rows, default_path
    return [], primary


def _gap_skill_names(gaps: dict[str, Any]) -> list[str]:
    missing = gaps.get("missing_skills") or []
    names: list[str] = []
    for m in missing:
        if isinstance(m, dict) and m.get("skill"):
            names.append(str(m["skill"]))
        elif isinstance(m, str) and m.strip():
            names.append(m.strip())
    return names


class StudyPlanToolContext:
    """Mutable context shared by function-calling tools during one study plan run."""

    def __init__(
        self,
        *,
        profile: dict[str, Any],
        gaps: dict[str, Any],
        embed_fn: Any | None,
    ) -> None:
        self.profile = profile
        self.gaps = gaps
        self.embed_fn = embed_fn
        self.rag_query = build_study_rag_query(profile, gaps)
        self.gap_skills = _gap_skill_names(gaps)
        self.local_rows, self.rag_path_used = _load_kb_rows()
        self.web_rows: list[dict[str, Any]] = []
        self.snippets: list[dict[str, Any]] = []
        self.tools_called: list[str] = []

    def search_local_kb(self, query: str | None = None) -> str:
        q = (query or self.rag_query).strip() or self.rag_query
        rows = retrieve_learning_context(
            query=q,
            resources=self.local_rows,
            embed_fn=self.embed_fn,
            top_k=settings.STUDY_PLAN_RAG_TOP_K,
            dataset_path=self.rag_path_used,
            force_in_memory=False,
        )
        self.tools_called.append("search_local_learning_kb")
        self.snippets.extend(rows)
        if not rows:
            return "No local learning resources matched the query."
        return format_rag_context_for_prompt(rows)

    def search_web(self, query: str | None = None) -> str:
        if not settings.STUDY_PLAN_WEB_SEARCH_ENABLED:
            return "Web search disabled by configuration."
        q = (query or self.rag_query).strip() or self.rag_query
        self.web_rows = fetch_web_learning_resources(q, gap_skills=self.gap_skills)
        merged = merge_learning_resources(self.local_rows, self.web_rows)
        rows = retrieve_learning_context(
            query=q,
            resources=merged,
            embed_fn=self.embed_fn,
            top_k=settings.STUDY_PLAN_RAG_TOP_K,
            dataset_path=self.rag_path_used,
            force_in_memory=True,
        )
        self.tools_called.append("search_web_learning")
        self.snippets.extend(rows)
        if not rows:
            return "Web search returned no usable learning snippets."
        return format_rag_context_for_prompt(rows)


def needs_external_resources(gaps: dict[str, Any]) -> tuple[bool, str]:
    """
    Heuristic gate before RAG / function calling.
    Returns (needs_rag, reason).
    """
    missing = gaps.get("missing_skills") or []
    if not missing:
        return False, "no_missing_skills"

    high = [
        m
        for m in missing
        if isinstance(m, dict) and str(m.get("priority") or "").lower() == "high"
    ]
    if high:
        return True, "high_priority_gaps"

    medium = [
        m
        for m in missing
        if isinstance(m, dict) and str(m.get("priority") or "").lower() == "medium"
    ]
    if len(medium) >= 2:
        return True, "multiple_medium_gaps"

    if len(missing) >= 3:
        return True, "many_gaps"

    return False, "gaps_trivial"


def build_study_plan_tools(ctx: StudyPlanToolContext) -> list[Any]:
    """LangChain tools for study planning function calling."""
    from langchain_core.tools import StructuredTool

    def search_local_learning_kb(query: str = "") -> str:
        """Search the local learning_resources knowledge base for snippets relevant to skill gaps."""
        return ctx.search_local_kb(query or None)

    def search_web_learning(query: str = "") -> str:
        """Search the web for free learning resources (courses, docs, videos) aligned to skill gaps."""
        return ctx.search_web(query or None)

    return [
        StructuredTool.from_function(
            func=search_local_learning_kb,
            name="search_local_learning_kb",
            description="Retrieve top learning snippets from the local KB. Pass an optional query override.",
        ),
        StructuredTool.from_function(
            func=search_web_learning,
            name="search_web_learning",
            description="Search the web for learning resources when local KB is insufficient.",
        ),
    ]


def run_rag_tool_loop(
    *,
    ctx: StudyPlanToolContext,
    llm: Any,
    profile: dict[str, Any],
    gaps: dict[str, Any],
    max_rounds: int | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Function-calling loop: LLM decides whether to call local KB and/or web search.
    Returns deduplicated snippets and tool names invoked.
    """
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    max_rounds = max_rounds or settings.STUDY_PLAN_FC_MAX_TOOL_ROUNDS
    tools = build_study_plan_tools(ctx)
    tool_map = {t.name: t for t in tools}
    llm_tools = llm.bind_tools(tools)

    system = """You are the Study Planning retrieval agent.
Decide whether external learning resources are needed for the candidate's skill gaps.
- Call search_local_learning_kb when gaps map to known topics in a local course library.
- Call search_web_learning only if gaps are niche/newer or local KB may be insufficient.
- You may call zero, one, or both tools.
- Do NOT generate the final study plan here; only gather retrieval context."""

    user = json.dumps(
        {"candidate_profile": profile, "skill_gaps": gaps, "rag_query_hint": ctx.rag_query},
        ensure_ascii=False,
    )
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user)]

    for _ in range(max(1, max_rounds)):
        resp = llm_tools.invoke(messages)
        messages.append(resp)
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            break
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
            tool_call_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
            tool = tool_map.get(str(name))
            if not tool:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:  # noqa: BLE001
                    result = f"Tool error: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=str(tool_call_id)))

    # Deduplicate snippets by id/title
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for s in ctx.snippets:
        key = str(s.get("id") or s.get("title") or json.dumps(s, sort_keys=True)[:80])
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    ctx.snippets = unique
    return unique, list(dict.fromkeys(ctx.tools_called))
