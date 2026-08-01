from uuid import uuid4

import pytest

from app.application.commands import CommandOperation, parse_command
from app.core.config import Settings
from app.infrastructure.database.models import ParticipantModel
from app.infrastructure.telegram.commands import (
    TelegramCommandParseError,
)
from app.infrastructure.telegram.commands import (
    parse_command as parse_telegram_command,
)
from app.runtime.telegram_command_worker import (
    _authorization_retry_delay,
    _configuration_change,
)


def test_entity_command_normalizes_and_trims_arguments() -> None:
    command = parse_telegram_command(
        "/MoDe@JanuaryBot mention_only  ",
        [{"type": "bot_command", "offset": 0, "length": 16}],
        "JanuaryBot",
        160,
    )
    assert command is not None
    assert (command.name, command.arguments) == ("mode", "mention_only")


def test_other_bot_and_slash_prose_are_not_commands() -> None:
    assert (
        parse_telegram_command(
            "/status@OtherBot",
            [{"type": "bot_command", "offset": 0, "length": 16}],
            "JanuaryBot",
            160,
        )
        is None
    )
    assert parse_telegram_command("/status", [], "JanuaryBot", 160) is None


def test_utf16_entity_offsets_are_checked() -> None:
    command = parse_telegram_command(
        "/status hello 😀",
        [{"type": "bot_command", "offset": 0, "length": 7}],
        "JanuaryBot",
        160,
    )
    assert command is not None and command.name == "status"
    try:
        parse_telegram_command(
            "/status",
            [{"type": "bot_command", "offset": 0, "length": 99}],
            "JanuaryBot",
            160,
        )
    except TelegramCommandParseError:
        pass
    else:
        raise AssertionError("out-of-range entity must be rejected")


def test_command_grammar_is_bounded() -> None:
    assert (
        parse_command("mode", "mention_and_name").operation
        == CommandOperation.CONFIGURATION
    )
    assert parse_command("mode", "paused").operation == CommandOperation.USAGE
    assert (
        parse_command("personality", "use lively@2").operation
        == CommandOperation.CONFIGURATION
    )
    assert parse_command("personality", "use {bad}").operation == CommandOperation.USAGE
    assert parse_command("mentions", "off").operation == CommandOperation.PREFERENCE


@pytest.mark.parametrize(
    ("name", "arguments", "operation", "action", "value"),
    [
        ("start", "", CommandOperation.READ, "status", None),
        ("help", "", CommandOperation.READ, "status", None),
        ("status", "", CommandOperation.READ, "status", None),
        ("mode", "status", CommandOperation.READ, "status", None),
        (
            "mode",
            "mention_only",
            CommandOperation.CONFIGURATION,
            "mode",
            "mention_only",
        ),
        (
            "mode",
            "mention_and_name",
            CommandOperation.CONFIGURATION,
            "mode",
            "mention_and_name",
        ),
        (
            "mode",
            "ambient_selective",
            CommandOperation.CONFIGURATION,
            "mode",
            "ambient_selective",
        ),
        ("frequency", "", CommandOperation.READ, "status", None),
        ("frequency", "status", CommandOperation.READ, "status", None),
        (
            "frequency",
            "low",
            CommandOperation.CONFIGURATION,
            "frequency",
            "low",
        ),
        (
            "frequency",
            "normal",
            CommandOperation.CONFIGURATION,
            "frequency",
            "normal",
        ),
        (
            "frequency",
            "high",
            CommandOperation.CONFIGURATION,
            "frequency",
            "high",
        ),
        ("quiet", "", CommandOperation.CONFIGURATION, "quiet", None),
        ("resume", "", CommandOperation.CONFIGURATION, "resume", None),
        ("personality", "list", CommandOperation.READ, "list", None),
        ("personality", "use lively", CommandOperation.CONFIGURATION, "use", "lively"),
        (
            "personality",
            "use lively@12",
            CommandOperation.CONFIGURATION,
            "use",
            "lively@12",
        ),
        ("stickers", "on", CommandOperation.CONFIGURATION, "set", True),
        ("stickers", "off", CommandOperation.CONFIGURATION, "set", False),
        ("mentions", "on", CommandOperation.PREFERENCE, "set", True),
        ("teasing", "off", CommandOperation.PREFERENCE, "set", False),
    ],
)
def test_every_accepted_command_form_has_a_typed_result(
    name: str,
    arguments: str,
    operation: CommandOperation,
    action: str,
    value: str | bool | None,
) -> None:
    result = parse_command(name, arguments)
    assert (result.operation, result.action, result.value) == (operation, action, value)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("start", "now"),
        ("quiet", "please"),
        ("mode", "paused"),
        ("frequency", "fast"),
        ("personality", "use arbitrary prompt text"),
        ("personality", "use {json}"),
        ("stickers", "maybe"),
        ("mentions", "other-user off"),
        ("teasing", "off extra"),
    ],
)
def test_malformed_command_forms_are_usage_errors(name: str, arguments: str) -> None:
    assert parse_command(name, arguments).operation == CommandOperation.USAGE


def test_authorization_retry_delay_is_exponential_and_bounded() -> None:
    settings = Settings(
        _env_file=None,
        command_retry_min_delay_seconds=2,
        command_retry_max_delay_seconds=5,
    )
    assert _authorization_retry_delay(settings, 1) == 2
    assert _authorization_retry_delay(settings, 2) == 4
    assert _authorization_retry_delay(settings, 3) == 5


@pytest.mark.parametrize(
    ("name", "arguments", "action"),
    [
        ("memory", "", "summary"),
        ("memory", "list", "list"),
        ("memory", "remember a fact", "remember"),
        ("memory", "reset_group confirm", "reset_group"),
        ("forget", "Abc12345", "forget"),
        ("forget_me", "", "warning"),
        ("forget_me", "confirm", "confirm"),
    ],
)
def test_memory_command_grammar_is_exact(
    name: str, arguments: str, action: str
) -> None:
    result = parse_command(name, arguments)
    assert result.operation == CommandOperation.MEMORY
    assert result.action == action


def test_ambient_and_sticker_configuration_gates_are_deterministic() -> None:
    participant = ParticipantModel(
        conversation_id=uuid4(), platform_user_id="test-user", display_name="Test"
    )
    ambient = parse_command("mode", "ambient_selective")
    stickers = parse_command("stickers", "on")
    code, change, _ = _configuration_change(
        Settings(_env_file=None), participant, ambient
    )
    assert (code, change) == ("ambient_disabled", None)
    code, change, _ = _configuration_change(
        Settings(_env_file=None), participant, stickers
    )
    assert (code, change) == ("sticker_mapping_unavailable", None)
    code, change, _ = _configuration_change(
        Settings(
            _env_file=None,
            ambient_selective_enabled=True,
            telegram_sticker_mapping={"celebrate": "file-id"},
        ),
        participant,
        ambient,
    )
    assert code == "success" and change is not None
