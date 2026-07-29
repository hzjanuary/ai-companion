"""Platform-independent persistence records and validated string enums."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AssistantStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Platform(StrEnum):
    TELEGRAM = "telegram"
    ZALO = "zalo"


class PlatformConnectionStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class ConversationType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class ResponseMode(StrEnum):
    MENTION_ONLY = "mention_only"
    MENTION_AND_NAME = "mention_and_name"
    AMBIENT_SELECTIVE = "ambient_selective"
    PAUSED = "paused"


class ParticipantRole(StrEnum):
    MEMBER = "member"
    ADMINISTRATOR = "administrator"
    OWNER = "owner"


class MessageDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class MessageType(StrEnum):
    TEXT = "text"
    STICKER = "sticker"
    OTHER = "other"


class MessageProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AssistantRecord:
    id: UUID
    name: str
    status: AssistantStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlatformConnectionRecord:
    id: UUID
    assistant_id: UUID
    platform: Platform
    external_bot_id: str
    status: PlatformConnectionStatus
    credential_reference: str | None
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: UUID
    platform_connection_id: UUID
    platform_conversation_id: str
    conversation_type: ConversationType
    title: str | None
    status: ConversationStatus
    response_mode: ResponseMode
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ParticipantRecord:
    id: UUID
    conversation_id: UUID
    platform_user_id: str
    username: str | None
    display_name: str
    role: ParticipantRole
    mention_allowed: bool
    teasing_allowed: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: UUID
    conversation_id: UUID
    participant_id: UUID | None
    platform_message_id: str
    direction: MessageDirection
    message_type: MessageType
    text: str | None
    reply_to_message_id: UUID | None
    metadata: dict[str, Any]
    processing_status: MessageProcessingStatus
    created_at: datetime
    updated_at: datetime
