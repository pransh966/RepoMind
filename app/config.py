from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    top_k: int = 5
    max_chunk_lines: int = 60
    chunk_overlap_lines: int = 10

    data_dir: str = "./data"

    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    jwt_secret: str = "dev-secret-change-me-in-.env"
    jwt_expire_minutes: int = 60 * 24 * 7

    database_url: str = "postgresql://postgres:postgres@localhost:5432/repomind"

    git_clone_timeout_seconds: int = 120


settings = Settings()
