"""
Centralized application settings, loaded from environment variables / .env.
Using pydantic-settings so every config value is validated and typed instead
of scattered os.environ[...] calls through the codebase.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM provider ---
    # "mock"  -> no API key needed, deterministic, used for local dev / tests / demos
    # "openai" | "anthropic" -> real providers, require the matching API key below
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Embeddings (local, free, no API key required) ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Retrieval / chunking ---
    top_k: int = 5
    max_chunk_lines: int = 60
    chunk_overlap_lines: int = 10

    # --- Storage ---
    data_dir: str = "./data"

    # --- Simple in-memory rate limiter ---
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    # --- Auth ---
    # CHANGE jwt_secret in your .env before deploying anywhere beyond localhost.
    jwt_secret: str = "dev-secret-change-me-in-.env"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- Database ---
    # Local Postgres. Format: postgresql://<user>:<password>@<host>:<port>/<database>
    database_url: str = "postgresql://postgres:postgres@localhost:5432/repomind"

    # --- Git ingestion ---
    git_clone_timeout_seconds: int = 120


settings = Settings()
