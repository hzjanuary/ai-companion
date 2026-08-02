from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "January"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"
    assert settings.resolved_database_url.drivername == "postgresql+asyncpg"
    assert settings.telegram_delivery_mode == "disabled"
    assert settings.context_recent_message_limit == 20
    assert settings.llm_enabled is False
    assert settings.outbound_delivery_enabled is False
    assert settings.command_worker_enabled is False
    assert settings.raw_content_retention_days == 30
    assert settings.retention_worker_enabled is False
    assert settings.rate_limit_enabled is False
    assert settings.rate_limit_generation_conversation_per_minute == 12
    assert settings.semantic_memory_enabled is False


def test_rate_limit_settings_are_typed_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JANUARY_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("JANUARY_RATE_LIMIT_GENERATION_PROVIDER_PER_MINUTE", "17")
    settings = Settings(_env_file=None)
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_generation_provider_per_minute == 17
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_delivery_conversation_per_second=0)


def test_provider_concurrency_settings_are_typed_and_reject_unknown_provider() -> None:
    settings = Settings(
        _env_file=None,
        provider_concurrency_enabled=True,
        provider_concurrency_limits='{"openai": 2}',
    )
    assert settings.provider_concurrency_limits == {"openai": 2}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, provider_concurrency_limits='{"unknown": 2}')


def test_command_settings_validate_retry_bounds_and_limits() -> None:
    settings = Settings(_env_file=None, command_max_argument_length=500)
    assert settings.command_max_argument_length == 500
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            command_retry_min_delay_seconds=10,
            command_retry_max_delay_seconds=1,
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, command_max_authorization_attempts=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, command_max_argument_length=501)


def test_llm_settings_require_remote_credentials_and_allow_keyless_ollama() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_enabled=True, llm_openai_model="fake")
    settings = Settings(
        _env_file=None,
        llm_enabled=True,
        llm_primary_provider="ollama",
        llm_ollama_model="fake-local",
    )
    assert settings.llm_ollama_model == "fake-local"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            llm_enabled=True,
            llm_primary_provider="ollama",
            llm_ollama_model="fake",
            llm_fallback_provider="ollama",
        )


def test_outbound_settings_require_telegram_and_validate_stickers() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, outbound_delivery_enabled=True)
    settings = Settings(
        _env_file=None,
        telegram_enabled=True,
        telegram_bot_token="fake-token",
        telegram_platform_connection_id=uuid4(),
        outbound_delivery_enabled=True,
        telegram_sticker_mapping={"laugh": "file-id"},
    )
    assert settings.telegram_sticker_mapping == {"laugh": "file-id"}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_sticker_mapping={"unknown": "file-id"})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_sticker_mapping={"laugh": " "})


def test_demo_mode_requires_polling_allowlist_and_live_components() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_live_enabled=True)
    settings = Settings(
        _env_file=None,
        demo_live_enabled=True,
        demo_allowed_chat_ids=("-1000000000001", "123"),
        telegram_enabled=True,
        telegram_bot_token="fake-token",
        telegram_delivery_mode="polling",
        telegram_platform_connection_id=uuid4(),
        llm_enabled=True,
        llm_primary_provider="ollama",
        llm_ollama_model="fake",
        outbound_delivery_enabled=True,
    )
    assert settings.demo_allowed_chat_ids == ("-1000000000001", "123")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_allowed_chat_ids=("1", "1"))


def test_demo_allowlist_parses_environment_json_and_rejects_non_numeric_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JANUARY_DEMO_ALLOWED_CHAT_IDS", '["-1000000000001", "123"]')
    assert Settings(_env_file=None).demo_allowed_chat_ids == ("-1000000000001", "123")

    monkeypatch.setenv("JANUARY_DEMO_ALLOWED_CHAT_IDS", '["not-a-chat"]')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_webhook_delivery_requires_complete_redacted_configuration() -> None:
    connection_id = uuid4()
    settings = Settings(
        _env_file=None,
        telegram_enabled=True,
        telegram_bot_token="fake-token",
        telegram_delivery_mode="webhook",
        telegram_platform_connection_id=connection_id,
        telegram_webhook_secret_token="safe-secret_123",
        telegram_webhook_public_base_url="https://example.invalid",
    )

    assert settings.telegram_platform_connection_id == connection_id
    assert "safe-secret_123" not in repr(settings)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_delivery_mode="polling")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JANUARY_TELEGRAM_WEBHOOK_BODY_LIMIT_BYTES", "1"),
        ("JANUARY_TELEGRAM_POLL_TIMEOUT_SECONDS", "0"),
        ("JANUARY_REDIS_BATCH_SIZE", "0"),
        ("JANUARY_REDIS_RECLAIM_IDLE_MS", "1"),
        ("JANUARY_INGRESS_EVENT_SCHEMA_VERSION", "0"),
    ],
)
def test_invalid_ingress_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JANUARY_CONTEXT_RECENT_MESSAGE_LIMIT", "0"),
        ("JANUARY_CONTEXT_REPLY_CHAIN_DEPTH", "-1"),
        ("JANUARY_CONTEXT_TOKEN_BUDGET", "1"),
        ("JANUARY_CONTEXT_MESSAGE_CHARACTER_LIMIT", "1"),
    ],
)
def test_invalid_context_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JANUARY_MEMORY_CONTEXT_LIMIT", "11"),
        ("JANUARY_MEMORY_CONTEXT_CHARACTER_BUDGET", "0"),
        ("JANUARY_RAW_CONTENT_RETENTION_DAYS", "31"),
        ("JANUARY_RETENTION_BATCH_SIZE", "0"),
        ("JANUARY_RETENTION_WORKER_POLL_INTERVAL_SECONDS", "0"),
    ],
)
def test_invalid_memory_and_retention_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_semantic_memory_settings_require_a_separate_embedding_capability() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantic_memory_enabled=True)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            semantic_memory_worker_enabled=True,
        )
    settings = Settings(
        _env_file=None,
        semantic_memory_enabled=True,
        embedding_provider="ollama",
        embedding_model="nomic-embed-text",
        embedding_dimension=768,
    )
    assert settings.embedding_model == "nomic-embed-text"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            semantic_memory_retry_min_delay_seconds=2,
            semantic_memory_retry_max_delay_seconds=1,
        )


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JANUARY_APP_NAME", "January Test")
    monkeypatch.setenv("JANUARY_ENVIRONMENT", "test")
    monkeypatch.setenv("JANUARY_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "January Test"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_database_settings_read_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JANUARY_DATABASE_HOST", "database")
    monkeypatch.setenv("JANUARY_DATABASE_PORT", "5433")
    monkeypatch.setenv("JANUARY_DATABASE_NAME", "january_test")
    monkeypatch.setenv("JANUARY_DATABASE_PASSWORD", "not-for-logs")
    monkeypatch.setenv("JANUARY_DATABASE_POOL_SIZE", "7")

    settings = Settings(_env_file=None)

    assert settings.resolved_database_url.host == "database"
    assert settings.resolved_database_url.port == 5433
    assert settings.resolved_database_url.database == "january_test"
    assert settings.database_pool_size == 7
    assert "not-for-logs" not in repr(settings)


def test_invalid_settings_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JANUARY_ENVIRONMENT", "unsupported")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JANUARY_DATABASE_PORT", "0"),
        ("JANUARY_DATABASE_POOL_SIZE", "0"),
        ("JANUARY_DATABASE_CONNECT_TIMEOUT_SECONDS", "0"),
        ("JANUARY_DATABASE_URL", "sqlite:///not-allowed"),
    ],
)
def test_invalid_database_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
