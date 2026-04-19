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

    # orchestration
    next_agent: Optional[str]
    stage: str  # intake -> resume -> match -> gap -> plan -> done

    # explainability (optional; assembled in api pipeline)
    pipeline_trace: Optional[list[dict[str, Any]]]
    fallback_events: Optional[list[dict[str, Any]]]

