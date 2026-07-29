import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.application.ports.platform import (
    PlatformAdapterError,
    PlatformErrorCategory,
    SendStickerRequest,
    SendTextRequest,
)
from app.core.config import Settings
from app.infrastructure.telegram.adapter import TelegramAdapter, create_telegram_adapter

TOKEN = "123456:UNMISTAKABLE_FAKE_TOKEN"


def settings(**values: object) -> Settings:
    return Settings(
        _env_file=None, telegram_enabled=True, telegram_bot_token=TOKEN, **values
    )


def client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="https://test.invalid")


def test_telegram_is_disabled_by_default_and_token_is_redacted() -> None:
    disabled = Settings(_env_file=None)

    assert disabled.telegram_enabled is False
    assert create_telegram_adapter(disabled) is None
    assert TOKEN not in repr(settings())


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JANUARY_TELEGRAM_TIMEOUT_SECONDS", "0"),
        ("JANUARY_TELEGRAM_CONNECTION_LIMIT", "0"),
        ("JANUARY_TELEGRAM_API_BASE_URL", "not-a-url"),
    ],
)
def test_invalid_telegram_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("JANUARY_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("JANUARY_TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_enabled_telegram_requires_token() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_enabled=True)


def test_get_me_maps_identity_without_network_at_construction() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "id": 99,
                    "is_bot": True,
                    "first_name": "January",
                    "username": "jan",
                    "can_join_groups": True,
                },
            },
        )

    async def scenario() -> None:
        supplied = client(httpx.MockTransport(handler))
        adapter = TelegramAdapter(settings(), supplied)
        assert calls == []
        identity = await adapter.verify_identity()
        assert identity.external_bot_id == "99"
        assert identity.username == "jan"
        assert calls[0].url.path.endswith("/getMe")
        await adapter.aclose()
        assert not supplied.is_closed
        await supplied.aclose()

    asyncio.run(scenario())


def test_send_operations_serialize_typed_payloads_and_reuse_client() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 7,
                    "date": 1,
                    "chat": {"id": -100},
                    "from": {"id": 9},
                },
            },
        )

    async def scenario() -> None:
        supplied = client(httpx.MockTransport(handler))
        adapter = TelegramAdapter(settings(), supplied)
        message = await adapter.send_text(
            SendTextRequest(
                "-100", "hello", reply_to_message_id="4", disable_notification=True
            )
        )
        sticker = await adapter.send_sticker(
            SendStickerRequest("-100", "file-id", message_thread_id="8")
        )
        assert message.platform_message_id == "7"
        assert sticker.conversation_id == "-100"
        assert payloads == [
            {
                "chat_id": "-100",
                "text": "hello",
                "reply_parameters": {"message_id": "4"},
                "disable_notification": True,
            },
            {"chat_id": "-100", "sticker": "file-id", "message_thread_id": "8"},
        ]
        await supplied.aclose()

    asyncio.run(scenario())


def test_chat_member_and_classified_failures_are_safe() -> None:
    responses = [
        {
            "ok": True,
            "result": {"status": "administrator", "can_delete_messages": True},
        },
        {
            "ok": False,
            "error_code": 429,
            "description": TOKEN,
            "parameters": {"retry_after": 4, "migrate_to_chat_id": -200},
        },
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    async def scenario() -> None:
        supplied = client(httpx.MockTransport(handler))
        adapter = TelegramAdapter(settings(), supplied)
        member = await adapter.get_chat_member("-100", "42")
        assert member.is_administrator and not member.is_owner
        with pytest.raises(PlatformAdapterError) as captured:
            await adapter.send_text(SendTextRequest("-100", "hello"))
        error = captured.value
        assert error.category == PlatformErrorCategory.RATE_LIMITED
        assert error.retry_after_seconds == 4
        assert error.replacement_conversation_id == "-200"
        assert TOKEN not in str(error)
        await supplied.aclose()

    asyncio.run(scenario())


def test_malformed_and_timeout_responses_are_not_retried() -> None:
    async def scenario() -> None:
        timeout = TelegramAdapter(
            settings(),
            client(
                httpx.MockTransport(
                    lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
                )
            ),
        )
        with pytest.raises(PlatformAdapterError) as captured:
            await timeout.send_sticker(SendStickerRequest("-100", "file"))
        assert captured.value.category == PlatformErrorCategory.TIMEOUT
        with pytest.raises(PlatformAdapterError) as invalid:
            await timeout.send_text(SendTextRequest("", ""))
        assert invalid.value.category == PlatformErrorCategory.INVALID_REQUEST

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("code", "category"),
    [
        (401, PlatformErrorCategory.AUTHENTICATION),
        (403, PlatformErrorCategory.PERMISSION),
        (404, PlatformErrorCategory.NOT_FOUND),
        (409, PlatformErrorCategory.CONFLICT),
        (500, PlatformErrorCategory.SERVER),
    ],
)
def test_telegram_http_failures_are_classified(
    code: int, category: PlatformErrorCategory
) -> None:
    async def scenario() -> None:
        supplied = client(
            httpx.MockTransport(
                lambda _: httpx.Response(code, json={"ok": False, "error_code": code})
            )
        )
        with pytest.raises(PlatformAdapterError) as captured:
            await TelegramAdapter(settings(), supplied).verify_identity()
        assert captured.value.category == category
        await supplied.aclose()

    asyncio.run(scenario())


def test_malformed_response_and_unknown_member_status_are_rejected() -> None:
    responses = [
        {"ok": True, "result": []},
        {"ok": True, "result": {"status": "future"}},
    ]

    async def scenario() -> None:
        supplied = client(
            httpx.MockTransport(lambda _: httpx.Response(200, json=responses.pop(0)))
        )
        adapter = TelegramAdapter(settings(), supplied)
        with pytest.raises(PlatformAdapterError) as malformed:
            await adapter.verify_identity()
        assert malformed.value.category == PlatformErrorCategory.MALFORMED_RESPONSE
        with pytest.raises(PlatformAdapterError) as unsupported:
            await adapter.get_chat_member("-100", "1")
        assert unsupported.value.category == PlatformErrorCategory.UNSUPPORTED_RESPONSE
        await supplied.aclose()

    asyncio.run(scenario())


def test_update_delivery_and_webhook_lifecycle_are_typed() -> None:
    payloads: list[dict[str, object]] = []
    responses = [
        {"ok": True, "result": [{"update_id": 4_000_000_000, "message": {}}]},
        {"ok": True, "result": True},
        {"ok": True, "result": True},
        {
            "ok": True,
            "result": {
                "url": "https://example.invalid/hook",
                "has_custom_certificate": False,
                "pending_update_count": 2,
                "allowed_updates": ["message"],
                "max_connections": 10,
            },
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    async def scenario() -> None:
        supplied = client(httpx.MockTransport(handler))
        adapter = TelegramAdapter(settings(), supplied)
        updates = await adapter.get_updates(
            offset="4000000000",
            limit=10,
            timeout_seconds=20,
            allowed_updates=("message",),
        )
        assert updates[0].update_id == "4000000000"
        await adapter.set_webhook(
            url="https://example.invalid/hook",
            secret_token="safe-secret",
            allowed_updates=("message",),
            max_connections=10,
        )
        await adapter.delete_webhook()
        info = await adapter.get_webhook_info()
        assert info.pending_update_count == 2
        assert payloads[0]["offset"] == 4_000_000_000
        assert payloads[1]["drop_pending_updates"] is False
        assert payloads[2]["drop_pending_updates"] is False
        await supplied.aclose()

    asyncio.run(scenario())
