import os


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "career-pilot-ai")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8080"))

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0"))
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "90"))
    # Default to 0 retries to prevent retries from multiplying perceived "timeout" duration.
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "0"))

    # Per-agent model assignments
    OPENAI_MODEL_RESUME_ANALYSIS: str = os.getenv("OPENAI_MODEL_RESUME_ANALYSIS", "gpt-5-nano")
    OPENAI_MODEL_JOB_MATCHING: str = os.getenv("OPENAI_MODEL_JOB_MATCHING", "gpt-5-nano")
    OPENAI_MODEL_SKILL_GAP: str = os.getenv("OPENAI_MODEL_SKILL_GAP", "gpt-5-nano")
    OPENAI_MODEL_STUDY_PLANNING: str = os.getenv("OPENAI_MODEL_STUDY_PLANNING", "gpt-5-nano")

    # Reduce input size to lower latency and avoid request timeouts.
    RESUME_ANALYSIS_RESUME_TEXT_MAX_CHARS: int = int(
        os.getenv("RESUME_ANALYSIS_RESUME_TEXT_MAX_CHARS", "12000")
    )
    API_RESUME_TEXT_MAX_CHARS: int = int(
        os.getenv("API_RESUME_TEXT_MAX_CHARS", os.getenv("RESUME_ANALYSIS_RESUME_TEXT_MAX_CHARS", "12000"))
    )

    INPUT_GUARD_ENABLED: bool = os.getenv("INPUT_GUARD_ENABLED", "true").lower() == "true"
    INPUT_GUARD_PROMPT_INJECTION_THRESHOLD: int = int(os.getenv("INPUT_GUARD_PROMPT_INJECTION_THRESHOLD", "1"))
    TARGET_ROLES_MAX_COUNT: int = int(os.getenv("TARGET_ROLES_MAX_COUNT", "12"))
    TARGET_ROLE_MAX_CHARS: int = int(os.getenv("TARGET_ROLE_MAX_CHARS", "120"))

    INPUT_GUARD_LLM_ENABLED: bool = os.getenv("INPUT_GUARD_LLM_ENABLED", "false").lower() == "true"
    INPUT_GUARD_LLM_MODEL: str = os.getenv("INPUT_GUARD_LLM_MODEL", "gpt-4o-mini")
    INPUT_GUARD_LLM_MAX_INPUT_CHARS: int = int(os.getenv("INPUT_GUARD_LLM_MAX_INPUT_CHARS", "6000"))
    INPUT_GUARD_LLM_TIMEOUT_SECONDS: float = float(os.getenv("INPUT_GUARD_LLM_TIMEOUT_SECONDS", "20"))
    INPUT_GUARD_LLM_FAIL_OPEN: bool = os.getenv("INPUT_GUARD_LLM_FAIL_OPEN", "true").lower() == "true"

    # Output safety (post-LLM): heuristics always run when enabled; moderation is optional (extra API calls).
    OUTPUT_FILTER_ENABLED: bool = os.getenv("OUTPUT_FILTER_ENABLED", "true").lower() == "true"
    OUTPUT_FILTER_OPENAI_MODERATION: bool = (
        os.getenv("OUTPUT_FILTER_OPENAI_MODERATION", "false").lower() == "true"
    )
    OUTPUT_FILTER_OPENAI_FAIL_OPEN: bool = (
        os.getenv("OUTPUT_FILTER_OPENAI_FAIL_OPEN", "true").lower() == "true"
    )
    OUTPUT_FILTER_MAX_STRING_CHARS: int = int(os.getenv("OUTPUT_FILTER_MAX_STRING_CHARS", "8000"))
    OUTPUT_FILTER_HEURISTIC_MAX_SCAN_CHARS: int = int(
        os.getenv("OUTPUT_FILTER_HEURISTIC_MAX_SCAN_CHARS", "24000")
    )
    OUTPUT_FILTER_MODERATION_BATCH_SIZE: int = int(os.getenv("OUTPUT_FILTER_MODERATION_BATCH_SIZE", "16"))

    SKILL_GAP_USER_MAX_CHARS: int = int(os.getenv("SKILL_GAP_USER_MAX_CHARS", "15000"))
    STUDY_PLANNING_USER_MAX_CHARS: int = int(os.getenv("STUDY_PLANNING_USER_MAX_CHARS", "30000"))

    # Study plan RAG (retrieval from data/learning_resources.jsonl)
    STUDY_PLAN_RAG_TOP_K: int = int(os.getenv("STUDY_PLAN_RAG_TOP_K", "5"))

    # Qdrant vector store
    QDRANT_ENABLED: bool = os.getenv("QDRANT_ENABLED", "true").lower() == "true"
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_TIMEOUT_SECONDS: float = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "5"))
    QDRANT_AUTO_START: bool = os.getenv("QDRANT_AUTO_START", "true").lower() == "true"
    QDRANT_READY_RETRIES: int = int(os.getenv("QDRANT_READY_RETRIES", "20"))
    QDRANT_READY_SLEEP_SECONDS: float = float(os.getenv("QDRANT_READY_SLEEP_SECONDS", "0.5"))
    QDRANT_RECREATE_COLLECTIONS: bool = (
        os.getenv("QDRANT_RECREATE_COLLECTIONS", "false").lower() == "true"
    )
    QDRANT_COLLECTION_JOBS: str = os.getenv("QDRANT_COLLECTION_JOBS", "careerpilot_jobs")
    QDRANT_COLLECTION_LEARNING: str = os.getenv(
        "QDRANT_COLLECTION_LEARNING",
        "careerpilot_learning_resources",
    )
    QDRANT_INDEX_META_PATH: str = os.getenv("QDRANT_INDEX_META_PATH", "data/.qdrant_index_meta.json")


settings = Settings()
