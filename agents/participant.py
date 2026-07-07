from __future__ import annotations

from typing import Any, Callable

from utils import debug
from security.output_filter import filter_agent_output

from . import apply_strategist, job_matching, resume_analysis, resume_optimizer, skill_gap, study_planning

AgentRunner = Callable[[dict], dict]


AGENTS: dict[str, dict[str, Any]] = {
    resume_analysis.AGENT_ID: {
        "name": resume_analysis.AGENT_NAME,
        "services": resume_analysis.SERVICES,
        "model": resume_analysis.DEFAULT_MODEL,
        "run": resume_analysis.run,
    },
    job_matching.AGENT_ID: {
        "name": job_matching.AGENT_NAME,
        "services": job_matching.SERVICES,
        "model": job_matching.DEFAULT_MODEL,
        "run": job_matching.run,
    },
    skill_gap.AGENT_ID: {
        "name": skill_gap.AGENT_NAME,
        "services": skill_gap.SERVICES,
        "model": skill_gap.DEFAULT_MODEL,
        "run": skill_gap.run,
    },
    resume_optimizer.AGENT_ID: {
        "name": resume_optimizer.AGENT_NAME,
        "services": resume_optimizer.SERVICES,
        "model": resume_optimizer.DEFAULT_MODEL,
        "run": resume_optimizer.run,
    },
    study_planning.AGENT_ID: {
        "name": study_planning.AGENT_NAME,
        "services": study_planning.SERVICES,
        "fc_tools": study_planning.FC_TOOLS,
        "model": study_planning.DEFAULT_MODEL,
        "run": study_planning.run,
    },
    apply_strategist.AGENT_ID: {
        "name": apply_strategist.AGENT_NAME,
        "services": apply_strategist.SERVICES,
        "model": apply_strategist.DEFAULT_MODEL,
        "run": apply_strategist.run,
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
            out = runner(state) or {}
            return filter_agent_output(out, agent_id=agent_id)

    return filter_agent_output(
        {"messages": [{"role": "assistant", "content": f"Unknown agent: {agent_id}"}]},
        agent_id=agent_id,
    )
