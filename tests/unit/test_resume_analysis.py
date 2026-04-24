from __future__ import annotations

import builtins
import json
import sys
import types
from typing import Any

import agents.resume_analysis as ra
import pytest


def _install_fake_langchain(monkeypatch, response_content: Any, captured: dict[str, Any]) -> None:
    class _Message:
        def __init__(self, content: str):
            self.content = content

    class _Resp:
        def __init__(self, content: Any):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured["llm_init_kwargs"] = kwargs

        def invoke(self, messages):
            captured["messages"] = messages
            return _Resp(response_content)

    langchain_core = types.ModuleType("langchain_core")
    langchain_core_messages = types.ModuleType("langchain_core.messages")
    langchain_core_messages.SystemMessage = _Message
    langchain_core_messages.HumanMessage = _Message
    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = _FakeChatOpenAI

    monkeypatch.setitem(sys.modules, "langchain_core", langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", langchain_core_messages)
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)


def test_run_returns_contract_fields_and_explainability(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    payload = {
        "profile": {
            "name": "Alex Tan",
            "headline": "Data Analyst",
            "education": [{"school": "NUS", "degree": "BSc", "field": "CS", "dates": "2019-2023"}],
            "experience": [{"company": "ACME", "role": "Analyst", "dates": "2023-2025", "highlights": ["Built dashboards"]}],
            "skills": ["Python", "SQL"],
            "certifications": ["PL-300"],
            "links": ["alex@example.com", "https://linkedin.com/in/alex"],
        },
        "evidence": {
            "skills": [{"skill": "Python", "snippets": ["Python, SQL, Power BI"]}],
            "education": [{"school": "NUS", "degree": "BSc", "field": "CS", "dates": "2019-2023"}],
            "experience": [{"company": "ACME", "role": "Analyst", "dates": "2023-2025", "highlights": ["Built dashboards"]}],
        },
    }
    _install_fake_langchain(monkeypatch, json.dumps(payload), captured)
    monkeypatch.setattr(ra, "resume_rationale_from_outputs", lambda cand, ev: f"skills={len(cand.get('skills', []))};ev={len(ev.get('skills', []))}")

    out = ra.run({"resume_text": "Alex Tan\nData Analyst\nSkills: Python, SQL"})

    assert out["candidate_profile"]["name"] == "Alex Tan"
    assert out["candidate_profile"]["skills"] == ["Python", "SQL"]
    assert out["resume_evidence"]["skills"][0]["skill"] == "Python"
    assert out["messages"][0]["name"] == ra.AGENT_NAME
    assert "_step_explainability" in out
    assert "summary" in out["_step_explainability"]
    assert out["_step_explainability"]["rationale"] == "skills=2;ev=1"
    assert captured["llm_init_kwargs"]["model"] == ra.DEFAULT_MODEL
    assert captured["llm_init_kwargs"]["temperature"] == 0


def test_run_uses_resume_path_loader_when_resume_text_missing(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    payload = {"profile": {"name": "", "headline": "", "education": [], "experience": [], "skills": [], "certifications": [], "links": []}, "evidence": {"skills": [], "education": [], "experience": []}}
    _install_fake_langchain(monkeypatch, json.dumps(payload), captured)
    monkeypatch.setattr(ra, "load_resume_text", lambda _p: "Loaded from file resume content")

    ra.run({"resume_path": "tests/fixtures/eval_resumes/long_01_many_projects.txt"})

    human_message = captured["messages"][1]
    assert human_message.content == "Loaded from file resume content"


def test_run_raises_when_no_resume_text_or_path() -> None:
    with pytest.raises(ValueError, match="No resume provided"):
        ra.run({})


def test_run_fallbacks_to_empty_payload_when_json_is_unparseable(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _install_fake_langchain(monkeypatch, "not a json payload at all", captured)

    out = ra.run({"resume_text": "Short resume"})

    assert out["candidate_profile"]["name"] == ""
    assert out["candidate_profile"]["skills"] == []
    assert out["resume_evidence"]["experience"] == []


def test_run_uses_extract_json_block_when_wrapped_output(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    wrapped = """Result:
```json
{"profile":{"name":"Jamie","headline":"","education":[],"experience":[],"skills":["SQL"],"certifications":[],"links":[]},"evidence":{"skills":[],"education":[],"experience":[]}}
```"""
    _install_fake_langchain(monkeypatch, wrapped, captured)

    out = ra.run({"resume_text": "Jamie\nSkills: SQL"})
    assert out["candidate_profile"]["name"] == "Jamie"
    assert out["candidate_profile"]["skills"] == ["SQL"]


def test_run_fallback_mode_when_langchain_unavailable(monkeypatch) -> None:
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"langchain_core.messages", "langchain_openai"}:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    monkeypatch.delitem(sys.modules, "langchain_core.messages", raising=False)
    monkeypatch.delitem(sys.modules, "langchain_openai", raising=False)

    out = ra.run({"resume_text": "Resume text"})

    assert out["candidate_profile"] == {}
    assert out["resume_evidence"] == {}
    fe = out["_step_explainability"].get("fallback_event")
    assert fe is not None
    assert fe["component"] == "resume_analysis"
    assert fe["to"] == "minimal_stub"


def test_bias_prompt_guardrail_present_and_counterfactual_output_equivalent(monkeypatch) -> None:
    captured_messages: list[list[Any]] = []
    payload = {
        "profile": {
            "name": "Candidate",
            "headline": "Data Analyst",
            "education": [],
            "experience": [],
            "skills": ["Python", "SQL"],
            "certifications": [],
            "links": [],
        },
        "evidence": {"skills": [], "education": [], "experience": []},
    }

    class _Message:
        def __init__(self, content: str):
            self.content = content

    class _Resp:
        def __init__(self, content: Any):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            captured_messages.append(messages)
            return _Resp(json.dumps(payload))

    langchain_core = types.ModuleType("langchain_core")
    langchain_core_messages = types.ModuleType("langchain_core.messages")
    langchain_core_messages.SystemMessage = _Message
    langchain_core_messages.HumanMessage = _Message
    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = _FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_core", langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", langchain_core_messages)
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)

    out_a = ra.run({"resume_text": "Aisha, female, 22 years old. Data Analyst. Skills: Python, SQL"})
    out_b = ra.run({"resume_text": "Brandon, male, 47 years old. Data Analyst. Skills: Python, SQL"})

    assert "Fairness: do not infer protected characteristics" in captured_messages[0][0].content
    assert out_a["candidate_profile"] == out_b["candidate_profile"]
    assert out_a["resume_evidence"] == out_b["resume_evidence"]

