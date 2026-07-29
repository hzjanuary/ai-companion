import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "January"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JANUARY_APP_NAME", "January Test")
    monkeypatch.setenv("JANUARY_ENVIRONMENT", "test")
    monkeypatch.setenv("JANUARY_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "January Test"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_invalid_settings_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JANUARY_ENVIRONMENT", "unsupported")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
