import os


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "career-pilot-ai")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8080"))

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0"))
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # Per-agent model assignments
    OPENAI_MODEL_RESUME_ANALYSIS: str = os.getenv("OPENAI_MODEL_RESUME_ANALYSIS", "gpt-5-nano")
    OPENAI_MODEL_JOB_MATCHING: str = os.getenv("OPENAI_MODEL_JOB_MATCHING", "gpt-5-nano")
    OPENAI_MODEL_SKILL_GAP: str = os.getenv("OPENAI_MODEL_SKILL_GAP", "gpt-5-nano")
    OPENAI_MODEL_STUDY_PLANNING: str = os.getenv("OPENAI_MODEL_STUDY_PLANNING", "gpt-5-nano")

    # Study plan RAG (retrieval from data/learning_resources.jsonl)
    STUDY_PLAN_RAG_TOP_K: int = int(os.getenv("STUDY_PLAN_RAG_TOP_K", "5"))

    # Qdrant vector store
    QDRANT_ENABLED: bool = os.getenv("QDRANT_ENABLED", "true").lower() == "true"
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
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
