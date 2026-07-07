from typing import TypedDict, Optional, Annotated, Any
import operator


class State(TypedDict, total=False):
    """
    Shared state for CareerPilot AI workflow.
    """

    messages: Annotated[list[dict[str, Any]], operator.add]

    # user inputs
    resume_path: Optional[str]
    resume_text: Optional[str]
    target_roles: Optional[list[str]]

    # agent outputs
    candidate_profile: Optional[dict[str, Any]]
    job_matches: Optional[list[dict[str, Any]]]
    skill_gaps: Optional[dict[str, Any]]
    study_plan: Optional[dict[str, Any]]
    resume_suggestions: Optional[dict[str, Any]]
    apply_strategy: Optional[dict[str, Any]]
    application_pack: Optional[dict[str, Any]]
    user_memory: Optional[dict[str, Any]]
    user_id: Optional[str]

    # orchestration
    next_agent: Optional[str]
    stage: str  # intake -> resume -> match -> gap -> optimize -> plan -> apply -> done
    routing_decision: Optional[dict[str, Any]]
    skip_study_plan: Optional[bool]
    session_memory: Optional[dict[str, Any]]

    # pipeline / run metadata
    run_id: Optional[str]
    pipeline_trace: Optional[list[dict[str, Any]]]
    fallback_events: Optional[list[dict[str, Any]]]
    account_username: Optional[str]

