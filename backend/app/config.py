"""Application settings loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: Literal["development", "production", "test"] = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hyundai"
    JWT_SECRET: str = "dev-insecure-secret-change-me-dev-insecure-secret-change-me"
    JWT_EXPIRES_MINUTES: int = 720
    COOKIE_SECURE: bool = False
    COOKIE_NAME: str = "hyundai_session"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    ALLOW_REGISTRATION: bool = True

    STORAGE_BACKEND: Literal["supabase", "local"] = "local"
    LOCAL_UPLOAD_DIR: str = "./uploads"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_BUCKET: str = "brochures"
    MAX_UPLOAD_MB: int = 50

    LLM_PROVIDER: Literal["gemini", "openai", "fake"] = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-3.5-flash"
    # Tried in order when the chat model is overloaded (503), rate limited (429) or missing (404).
    GEMINI_FALLBACK_MODELS: str = "gemini-2.5-flash,gemini-3.5-flash-lite"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 768

    VISION_OCR_FALLBACK: bool = True
    RETRIEVAL_TOP_K: int = 8
    LLM_TIMEOUT_SECONDS: int = 60
    MAX_MESSAGE_CHARS: int = Field(default=2000)

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Accept plain postgres:// URLs (as copied from Supabase) and convert to asyncpg.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
