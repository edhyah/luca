"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # STT
    deepgram_api_key: str = ""

    # TTS
    elevenlabs_api_key: str = ""
    cartesia_api_key: str = ""
    tts_provider: Literal["elevenlabs", "cartesia"] = "elevenlabs"
    tts_voice_id: str = ""

    # LLMs
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""

    # Transport
    daily_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://luca:luca@localhost:5432/luca"

    # Config
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
