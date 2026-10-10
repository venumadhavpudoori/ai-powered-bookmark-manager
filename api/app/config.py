"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://recallai:recallai@db:5432/recallai"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://recallai:recallai@db:5432/recallai"

    # ── Auth ──────────────────────────────────────────────
    SECRET_KEY: str = "change-me-to-a-random-secret-at-least-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── AI ────────────────────────────────────────────────
    AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # ── Rate Limits ───────────────────────────────────────
    RATE_LIMIT_BOOKMARKS: str = "30/minute"
    RATE_LIMIT_SEARCH: str = "60/minute"

    # ── Worker ────────────────────────────────────────────
    WORKER_POLL_INTERVAL: int = 2
    WORKER_BATCH_SIZE: int = 5

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
