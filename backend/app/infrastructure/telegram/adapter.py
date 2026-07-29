"""Narrow Telegram Bot API adapter with token-safe failures."""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.application.ports.platform import (
    BotIdentity,
    ChatMember,
    PlatformAdapterError,
    PlatformCapability,
    PlatformErrorCategory,
    SendStickerRequest,
    SendTextRequest,
    SentMessage,
)
from app.core.config import Settings
from app.domain.persistence import Platform


class TelegramAdapter:
    """Implements only getMe, sendMessage, sendSticker, and getChatMember."""

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        if not settings.telegram_enabled or settings.telegram_bot_token is None:
            raise PlatformAdapterError(
                PlatformErrorCategory.CONFIGURATION, "telegram_configuration"
            )
        self._token = settings.telegram_bot_token.get_secret_value()
        self._base_url = settings.telegram_api_base_url
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.telegram_timeout_seconds,
                connect=settings.telegram_connect_timeout_seconds,
            ),
            limits=httpx.Limits(max_connections=settings.telegram_connection_limit),
            headers={"User-Agent": settings.telegram_user_agent},
        )

    @property
    def capabilities(self) -> frozenset[PlatformCapability]:
        return frozenset(PlatformCapability)

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def verify_identity(self) -> BotIdentity:
        result = await self._request("getMe", {})
        if result.get("is_bot") is not True:
            raise PlatformAdapterError(
                PlatformErrorCategory.UNSUPPORTED_RESPONSE, "getMe"
            )
        return BotIdentity(
            platform=Platform.TELEGRAM,
            external_bot_id=self._string(result, "id", "getMe"),
            username=self._optional_string(result, "username", "getMe"),
            display_name=self._string(result, "first_name", "getMe"),
            is_bot=True,
            can_join_groups=self._optional_bool(result, "can_join_groups", "getMe"),
            can_read_all_group_messages=self._optional_bool(
                result, "can_read_all_group_messages", "getMe"
            ),
        )

    async def send_text(self, request: SendTextRequest) -> SentMessage:
        if not request.conversation_id or not request.text or len(request.text) > 4096:
            raise PlatformAdapterError(
                PlatformErrorCategory.INVALID_REQUEST, "sendMessage"
            )
        payload: dict[str, Any] = {
            "chat_id": request.conversation_id,
            "text": request.text,
        }
        self._add_send_options(payload, request)
        if request.entities:
            payload["entities"] = [
                {
                    "type": entity.entity_type,
                    "offset": entity.offset,
                    "length": entity.length,
                }
                for entity in request.entities
            ]
        return self._message(await self._request("sendMessage", payload), "sendMessage")

    async def send_sticker(self, request: SendStickerRequest) -> SentMessage:
        if not request.conversation_id or not request.asset_reference.strip():
            raise PlatformAdapterError(
                PlatformErrorCategory.INVALID_REQUEST, "sendSticker"
            )
        payload: dict[str, Any] = {
            "chat_id": request.conversation_id,
            "sticker": request.asset_reference,
        }
        self._add_send_options(payload, request)
        return self._message(await self._request("sendSticker", payload), "sendSticker")

    async def get_chat_member(self, conversation_id: str, user_id: str) -> ChatMember:
        if not conversation_id or not user_id:
            raise PlatformAdapterError(
                PlatformErrorCategory.INVALID_REQUEST, "getChatMember"
            )
        result = await self._request(
            "getChatMember", {"chat_id": conversation_id, "user_id": user_id}
        )
        status = self._string(result, "status", "getChatMember")
        normalized = {
            "creator": "owner",
            "owner": "owner",
            "administrator": "administrator",
            "member": "member",
            "restricted": "restricted",
            "left": "left",
            "kicked": "kicked",
        }
        if status not in normalized:
            raise PlatformAdapterError(
                PlatformErrorCategory.UNSUPPORTED_RESPONSE, "getChatMember"
            )
        permissions = frozenset(
            key
            for key, value in result.items()
            if key.startswith("can_") and value is True
        )
        return ChatMember(
            conversation_id=conversation_id,
            user_id=user_id,
            status=normalized[status],
            is_administrator=status in {"creator", "owner", "administrator"},
            is_owner=status in {"creator", "owner"},
            permissions=permissions,
        )

    def _add_send_options(
        self, payload: dict[str, Any], request: SendTextRequest | SendStickerRequest
    ) -> None:
        if request.reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": request.reply_to_message_id}
        if request.message_thread_id is not None:
            payload["message_thread_id"] = request.message_thread_id
        if request.disable_notification is not None:
            payload["disable_notification"] = request.disable_notification
        if request.protect_content is not None:
            payload["protect_content"] = request.protect_content

    async def _request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self._base_url}/bot{self._token}/{operation}", json=payload
            )
        except httpx.TimeoutException as error:
            raise PlatformAdapterError(
                PlatformErrorCategory.TIMEOUT, operation
            ) from error
        except httpx.HTTPError as error:
            raise PlatformAdapterError(
                PlatformErrorCategory.NETWORK, operation, retryable=True
            ) from error
        try:
            envelope = response.json()
        except ValueError as error:
            raise PlatformAdapterError(
                PlatformErrorCategory.MALFORMED_RESPONSE, operation
            ) from error
        if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
            raise PlatformAdapterError(
                PlatformErrorCategory.MALFORMED_RESPONSE, operation
            )
        if envelope["ok"] is True:
            result = envelope.get("result")
            if not isinstance(result, dict):
                raise PlatformAdapterError(
                    PlatformErrorCategory.MALFORMED_RESPONSE, operation
                )
            return result
        self._raise_failure(operation, envelope, response.status_code)
        raise AssertionError("unreachable")

    def _raise_failure(
        self, operation: str, envelope: dict[str, Any], status_code: int
    ) -> None:
        raw_code = envelope.get("error_code")
        code = raw_code if isinstance(raw_code, int) else status_code
        category = {
            401: PlatformErrorCategory.AUTHENTICATION,
            403: PlatformErrorCategory.PERMISSION,
            400: PlatformErrorCategory.INVALID_REQUEST,
            404: PlatformErrorCategory.NOT_FOUND,
            409: PlatformErrorCategory.CONFLICT,
            429: PlatformErrorCategory.RATE_LIMITED,
        }.get(code)
        if category is None:
            category = (
                PlatformErrorCategory.SERVER
                if code >= 500
                else PlatformErrorCategory.INVALID_REQUEST
            )
        raw_parameters = envelope.get("parameters")
        parameters: dict[str, Any] = (
            raw_parameters if isinstance(raw_parameters, dict) else {}
        )
        retry_after = (
            parameters.get("retry_after")
            if isinstance(parameters.get("retry_after"), int)
            else None
        )
        migrate = parameters.get("migrate_to_chat_id")
        raise PlatformAdapterError(
            category,
            operation,
            retryable=category
            in {PlatformErrorCategory.RATE_LIMITED, PlatformErrorCategory.SERVER},
            retry_after_seconds=retry_after,
            replacement_conversation_id=str(migrate)
            if isinstance(migrate, str | int)
            else None,
            telegram_error_code=code,
        )

    def _message(self, result: dict[str, Any], operation: str) -> SentMessage:
        raw_chat = result.get("chat")
        chat: dict[str, Any] = raw_chat if isinstance(raw_chat, dict) else {}
        raw_sender = result.get("from")
        sender: dict[str, Any] = raw_sender if isinstance(raw_sender, dict) else {}
        date = result.get("date")
        return SentMessage(
            Platform.TELEGRAM,
            self._string(result, "message_id", operation),
            self._string(chat, "id", operation),
            str(sender["id"]) if isinstance(sender.get("id"), str | int) else None,
            str(result["message_thread_id"])
            if isinstance(result.get("message_thread_id"), str | int)
            else None,
            datetime.fromtimestamp(date, UTC) if isinstance(date, int) else None,
        )

    def _string(self, value: dict[str, Any], key: str, operation: str) -> str:
        raw = value.get(key)
        if not isinstance(raw, str | int):
            raise PlatformAdapterError(
                PlatformErrorCategory.MALFORMED_RESPONSE, operation
            )
        return str(raw)

    def _optional_string(
        self, value: dict[str, Any], key: str, operation: str
    ) -> str | None:
        raw = value.get(key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise PlatformAdapterError(
                PlatformErrorCategory.MALFORMED_RESPONSE, operation
            )
        return raw

    def _optional_bool(
        self, value: dict[str, Any], key: str, operation: str
    ) -> bool | None:
        raw = value.get(key)
        if raw is None:
            return None
        if not isinstance(raw, bool):
            raise PlatformAdapterError(
                PlatformErrorCategory.MALFORMED_RESPONSE, operation
            )
        return raw


def create_telegram_adapter(settings: Settings) -> TelegramAdapter | None:
    """Compose Telegram only when explicitly enabled; construction is network-free."""

    return TelegramAdapter(settings) if settings.telegram_enabled else None
