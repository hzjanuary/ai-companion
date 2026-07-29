"""Typed runtime settings loaded from the environment."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


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
    database_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(default="january", min_length=1, max_length=63)
    database_user: str = Field(default="january", min_length=1, max_length=63)
    database_password: SecretStr = SecretStr("january-local")
    database_url: SecretStr | None = None
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    database_echo: bool = False
    telegram_enabled: bool = False
    telegram_bot_token: SecretStr | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_timeout_seconds: float = Field(default=10, gt=0, le=60)
    telegram_connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    telegram_connection_limit: int = Field(default=10, ge=1, le=100)
    telegram_user_agent: str = Field(
        default="january/0.1", min_length=1, max_length=128
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        url = make_url(value)
        if url.drivername != "postgresql+asyncpg":
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return value

    @field_validator("telegram_api_base_url")
    @classmethod
    def validate_telegram_api_base_url(cls, value: str) -> str:
        url = urlparse(value)
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("telegram_api_base_url must be an absolute HTTP(S) URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_telegram_token_when_enabled(self) -> "Settings":
        if self.telegram_enabled and self.telegram_bot_token is None:
            raise ValueError(
                "telegram_bot_token is required when telegram_enabled is true"
            )
        return self

    @property
    def resolved_database_url(self) -> URL:
        """Build the only database URL used by engines and migrations."""

        if self.database_url is not None:
            return make_url(self.database_url.get_secret_value())
        return URL.create(
            "postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Return process settings once; tests may clear this cache between cases."""

    return Settings()
