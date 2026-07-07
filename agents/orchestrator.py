from utils import debug

from agents.supervisor import evaluate_after_gap, evaluate_after_match, merge_routing_decision


STAGES = ["intake", "resume", "match", "gap", "optimize", "plan", "apply", "done"]


def orchestrator(state):
    """
    Supervisor-style routing: fixed pipeline with conditional skips after match/gap.
    """
    stage = state.get("stage") or "intake"
    print("[ORCH]", f"stage={stage}")

    if stage == "intake":
        debug("routing to resume_analysis", "ORCH")
        return {"next_agent": "resume_analysis", "stage": "resume"}

    if stage == "resume":
        debug("routing to job_matching", "ORCH")
        return {"next_agent": "job_matching", "stage": "match"}

    if stage == "match":
        match_decision = evaluate_after_match(state)
        routing = merge_routing_decision(state, match_decision)
        debug("routing to skill_gap", "ORCH")
        return {
            "next_agent": "skill_gap",
            "stage": "gap",
            "routing_decision": routing,
        }

    if stage == "gap":
        gap_decision = evaluate_after_gap(state)
        routing = merge_routing_decision(state, gap_decision)
        routing["skip_study_plan"] = bool(gap_decision.get("skip_study_plan"))
        debug("routing to resume_optimizer", "ORCH")
        return {
            "next_agent": "resume_optimizer",
            "stage": "optimize",
            "skip_study_plan": bool(gap_decision.get("skip_study_plan")),
            "routing_decision": routing,
        }

    if stage == "plan":
        debug("routing to apply_strategist", "ORCH")
        return {"next_agent": "apply_strategist", "stage": "apply"}

    if stage == "apply":
        debug("routing to human, marking done", "ORCH")
        return {"next_agent": "human", "stage": "done"}

    if stage == "optimize":
        if state.get("skip_study_plan"):
            debug("supervisor skip study_planning; route to apply", "ORCH")
            return {"next_agent": "apply_strategist", "stage": "apply"}
        debug("routing to study_planning", "ORCH")
        return {"next_agent": "study_planning", "stage": "plan"}

    debug("fallback to human, marking done", "ORCH")
    return {"next_agent": "human", "stage": "done"}
