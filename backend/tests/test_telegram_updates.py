import pytest

from app.infrastructure.telegram.updates import (
    TelegramUpdateValidationError,
    parse_telegram_update,
)


def test_supported_update_parses_without_losing_raw_json() -> None:
    update = parse_telegram_update(
        {"update_id": 4_000_000_000, "message": {"message_id": 1}, "future": None}
    )

    assert update.update_id == "4000000000"
    assert update.update_type == "message"
    assert update.supported is True
    assert update.raw_payload["message"] == {"message_id": 1}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"update_id": "wrong"},
        {"update_id": 1, "message": {}, "chat_member": {}},
        {"update_id": 1, "message": "wrong"},
    ],
)
def test_invalid_update_shapes_are_rejected(payload: object) -> None:
    with pytest.raises(TelegramUpdateValidationError):
        parse_telegram_update(payload)


def test_unknown_update_type_is_explicitly_not_supported() -> None:
    update = parse_telegram_update({"update_id": 2, "callback_query": {"id": "x"}})

    assert update.update_type == "callback_query"
    assert update.supported is False
