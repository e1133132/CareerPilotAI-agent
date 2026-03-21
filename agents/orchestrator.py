from utils import debug


STAGES = ["intake", "resume", "match", "gap", "plan", "done"]


def orchestrator(state):
    """
    Routes the workflow through the four agents sequentially.
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
        debug("routing to skill_gap", "ORCH")
        return {"next_agent": "skill_gap", "stage": "gap"}
    if stage == "gap":
        debug("routing to study_planning", "ORCH")
        return {"next_agent": "study_planning", "stage": "plan"}
    if stage == "plan":
        debug("routing to human, marking done", "ORCH")
        return {"next_agent": "human", "stage": "done"}

    debug("fallback to human, marking done", "ORCH")
    return {"next_agent": "human", "stage": "done"}
