"""Typed runtime settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration that is safe to load without external dependencies."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JANUARY_",
        extra="ignore",
    )

    app_name: str = Field(default="January", min_length=1, max_length=100)
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return process settings once; tests may clear this cache between cases."""

    return Settings()
