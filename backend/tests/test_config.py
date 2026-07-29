import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "January"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"
    assert settings.resolved_database_url.drivername == "postgresql+asyncpg"


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
