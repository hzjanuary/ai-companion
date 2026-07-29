"""Typed runtime settings loaded from the environment."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

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
    telegram_delivery_mode: Literal["disabled", "webhook", "polling"] = "disabled"
    telegram_platform_connection_id: UUID | None = None
    telegram_allowed_updates: tuple[
        Literal["message", "edited_message", "my_chat_member", "chat_member"], ...
    ] = ("message", "edited_message", "my_chat_member", "chat_member")
    telegram_webhook_secret_token: SecretStr | None = None
    telegram_webhook_public_base_url: str | None = None
    telegram_webhook_body_limit_bytes: int = Field(
        default=1_048_576, ge=1024, le=10_485_760
    )
    telegram_webhook_max_connections: int = Field(default=40, ge=1, le=100)
    telegram_poll_timeout_seconds: int = Field(default=30, ge=1, le=50)
    telegram_poll_batch_limit: int = Field(default=100, ge=1, le=100)
    telegram_poll_retry_backoff_seconds: float = Field(default=1, gt=0, le=60)
    telegram_poll_max_backoff_seconds: float = Field(default=30, gt=0, le=300)
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    redis_stream_name: str = Field(
        default="january:incoming-updates", min_length=1, max_length=255
    )
    redis_consumer_group: str = Field(
        default="january-ingress", min_length=1, max_length=255
    )
    redis_block_timeout_ms: int = Field(default=1000, ge=1, le=60_000)
    redis_batch_size: int = Field(default=10, ge=1, le=100)
    redis_reclaim_idle_ms: int = Field(default=60_000, ge=1_000, le=86_400_000)
    ingress_outbox_batch_size: int = Field(default=50, ge=1, le=500)
    ingress_outbox_poll_interval_seconds: float = Field(default=1, gt=0, le=60)
    ingress_event_schema_version: int = Field(default=1, ge=1, le=100)
    conversation_consumer_name: str | None = None
    conversation_worker_poll_interval_seconds: float = Field(default=1, gt=0, le=60)
    context_recent_message_limit: int = Field(default=20, ge=1, le=100)
    context_reply_chain_depth: int = Field(default=5, ge=0, le=20)
    context_token_budget: int = Field(default=1200, ge=64, le=32_000)
    context_message_character_limit: int = Field(default=2000, ge=64, le=20_000)
    context_max_history_age_days: int = Field(default=30, ge=1, le=365)

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

    @field_validator(
        "telegram_bot_token",
        "telegram_webhook_secret_token",
        "telegram_platform_connection_id",
        mode="before",
    )
    @classmethod
    def normalize_empty_optional_values(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("telegram_webhook_public_base_url")
    @classmethod
    def validate_webhook_base_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        url = urlparse(value)
        if url.scheme != "https" or not url.netloc:
            raise ValueError(
                "telegram_webhook_public_base_url must be an absolute HTTPS URL"
            )
        return value.rstrip("/")

    @field_validator("telegram_webhook_secret_token")
    @classmethod
    def validate_webhook_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if not 1 <= len(secret) <= 256 or not all(
            char.isascii() and (char.isalnum() or char in "_-") for char in secret
        ):
            raise ValueError(
                "telegram_webhook_secret_token must use 1-256 safe ASCII characters"
            )
        return value

    @model_validator(mode="after")
    def validate_delivery_configuration(self) -> "Settings":
        if self.telegram_enabled and self.telegram_bot_token is None:
            raise ValueError(
                "telegram_bot_token is required when telegram_enabled is true"
            )
        if (
            self.telegram_poll_retry_backoff_seconds
            > self.telegram_poll_max_backoff_seconds
        ):
            raise ValueError("telegram poll retry backoff cannot exceed its maximum")
        if self.telegram_delivery_mode != "disabled":
            if not self.telegram_enabled or self.telegram_bot_token is None:
                raise ValueError(
                    "Telegram enabled mode and bot token are required for delivery"
                )
            if self.telegram_platform_connection_id is None:
                raise ValueError(
                    "telegram_platform_connection_id is required for delivery"
                )
        if self.telegram_delivery_mode == "webhook":
            if self.telegram_webhook_secret_token is None:
                raise ValueError(
                    "telegram_webhook_secret_token is required for webhook delivery"
                )
            if self.telegram_webhook_public_base_url is None:
                raise ValueError(
                    "telegram_webhook_public_base_url is required for webhook delivery"
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
