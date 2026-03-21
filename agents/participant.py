from __future__ import annotations

from typing import Any, Callable

from utils import debug

from . import job_matching, resume_analysis, skill_gap, study_planning

AgentRunner = Callable[[dict], dict]


AGENTS: dict[str, dict[str, Any]] = {
    resume_analysis.AGENT_ID: {
        "name": resume_analysis.AGENT_NAME,
        "tools": resume_analysis.TOOLS,
        "model": resume_analysis.DEFAULT_MODEL,
        "run": resume_analysis.run,
    },
    job_matching.AGENT_ID: {
        "name": job_matching.AGENT_NAME,
        "tools": job_matching.TOOLS,
        "model": job_matching.DEFAULT_MODEL,
        "run": job_matching.run,
    },
    skill_gap.AGENT_ID: {
        "name": skill_gap.AGENT_NAME,
        "tools": skill_gap.TOOLS,
        "model": skill_gap.DEFAULT_MODEL,
        "run": skill_gap.run,
    },
    study_planning.AGENT_ID: {
        "name": study_planning.AGENT_NAME,
        "tools": study_planning.TOOLS,
        "model": study_planning.DEFAULT_MODEL,
        "run": study_planning.run,
    },
}


def participant(agent_id: str, state: dict) -> dict:
    """
    Execute one agent step and return state updates.
    """
    debug(f"agent_id={agent_id}", "PARTICIPANT")

    entry = AGENTS.get(agent_id)
    if entry:
        runner: Any = entry.get("run")
        if callable(runner):
            return runner(state)

    return {"messages": [{"role": "assistant", "content": f"Unknown agent: {agent_id}"}]}

