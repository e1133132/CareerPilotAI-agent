"""Security helpers: input validation, heuristics, optional LLM prompt-injection classifier."""

from .input_guard import (
    normalize_target_roles,
    prompt_injection_hit_count,
    truncate_resume_text,
    validate_api_user_inputs,
    validate_no_prompt_injection,
    validate_roles_list,
)
from .llm_injection_guard import combined_user_text_for_llm_guard, llm_input_is_unsafe

__all__ = [
    "combined_user_text_for_llm_guard",
    "llm_input_is_unsafe",
    "normalize_target_roles",
    "prompt_injection_hit_count",
    "truncate_resume_text",
    "validate_api_user_inputs",
    "validate_no_prompt_injection",
    "validate_roles_list",
]
