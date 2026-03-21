import os


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "career-pilot-ai")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8080"))

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0"))
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    # Per-agent model assignments
    OPENAI_MODEL_RESUME_ANALYSIS: str = os.getenv("OPENAI_MODEL_RESUME_ANALYSIS", "gpt-5")
    OPENAI_MODEL_JOB_MATCHING: str = os.getenv("OPENAI_MODEL_JOB_MATCHING", "gpt-5-mini")
    OPENAI_MODEL_SKILL_GAP: str = os.getenv("OPENAI_MODEL_SKILL_GAP", "gpt-5-mini")
    OPENAI_MODEL_STUDY_PLANNING: str = os.getenv("OPENAI_MODEL_STUDY_PLANNING", "gpt-5-mini")


settings = Settings()
