"""Platform-independent outbound messaging contracts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.domain.outbound import DeliveryCertainty
from app.domain.persistence import Platform


class PlatformCapability(StrEnum):
    VERIFY_BOT_IDENTITY = "verify_bot_identity"
    SEND_TEXT = "send_text"
    REPLY_TO_MESSAGE = "reply_to_message"
    SEND_STICKER = "send_sticker"
    GET_CHAT_MEMBER = "get_chat_member"
    GET_UPDATES = "get_updates"
    SET_WEBHOOK = "set_webhook"
    DELETE_WEBHOOK = "delete_webhook"
    GET_WEBHOOK_INFO = "get_webhook_info"


class PlatformErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    SERVER = "server"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_RESPONSE = "unsupported_response"


@dataclass(frozen=True, slots=True)
class BotIdentity:
    platform: Platform
    external_bot_id: str
    username: str | None
    display_name: str
    is_bot: bool
    can_join_groups: bool | None
    can_read_all_group_messages: bool | None


@dataclass(frozen=True, slots=True)
class TextEntity:
    entity_type: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class SendTextRequest:
    conversation_id: str
    text: str
    reply_to_message_id: str | None = None
    message_thread_id: str | None = None
    entities: tuple[TextEntity, ...] = ()
    disable_notification: bool | None = None
    protect_content: bool | None = None


@dataclass(frozen=True, slots=True)
class SendStickerRequest:
    conversation_id: str
    asset_reference: str
    reply_to_message_id: str | None = None
    message_thread_id: str | None = None
    disable_notification: bool | None = None
    protect_content: bool | None = None


@dataclass(frozen=True, slots=True)
class SentMessage:
    platform: Platform
    platform_message_id: str
    conversation_id: str
    sender_id: str | None
    message_thread_id: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ChatMember:
    conversation_id: str
    user_id: str
    status: str
    is_administrator: bool
    is_owner: bool
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class WebhookInfo:
    url: str
    pending_update_count: int
    allowed_updates: tuple[str, ...]
    max_connections: int | None
    last_error_at: datetime | None
    last_error_message: str | None
    ip_address: str | None
    has_custom_certificate: bool


class PlatformAdapterError(Exception):
    def __init__(
        self,
        category: PlatformErrorCategory,
        operation: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
        replacement_conversation_id: str | None = None,
        telegram_error_code: int | None = None,
        delivery_certainty: DeliveryCertainty = DeliveryCertainty.NOT_SENT,
        diagnostic: str = "Telegram operation failed",
    ) -> None:
        self.category = category
        self.operation = operation
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.replacement_conversation_id = replacement_conversation_id
        self.telegram_error_code = telegram_error_code
        self.delivery_certainty = delivery_certainty
        self.diagnostic = diagnostic
        super().__init__(f"{operation}: {category.value}")


class PlatformAdapter(Protocol):
    @property
    def capabilities(self) -> frozenset[PlatformCapability]: ...

    async def verify_identity(self) -> BotIdentity: ...

    async def send_text(self, request: SendTextRequest) -> SentMessage: ...

    async def send_sticker(self, request: SendStickerRequest) -> SentMessage: ...

    async def get_chat_member(
        self, conversation_id: str, user_id: str
    ) -> ChatMember: ...
