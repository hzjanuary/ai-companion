"""Telegram payload normalization into platform-independent conversation values."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.domain.conversation import (
    ConversationIdentity,
    MembershipStatus,
    MentionReference,
    NormalizedMembership,
    NormalizedMessage,
    ParticipantIdentity,
)
from app.domain.persistence import ConversationType, ParticipantRole, Platform
from app.infrastructure.telegram.updates import TelegramUpdate


class TelegramNormalizationError(ValueError):
    """A durable Telegram payload cannot be safely normalized."""


def normalize_telegram_update(
    update: TelegramUpdate,
    *,
    platform_connection_id: UUID,
    assistant_platform_user_id: str,
    assistant_display_name: str,
    assistant_username: str | None,
) -> NormalizedMessage | NormalizedMembership:
    if update.update_type in {"message", "edited_message"}:
        payload = _object(update.raw_payload, update.update_type)
        return _message(
            payload,
            platform_connection_id=platform_connection_id,
            assistant_platform_user_id=assistant_platform_user_id,
            assistant_username=assistant_username,
            is_edit=update.update_type == "edited_message",
        )
    if update.update_type in {"chat_member", "my_chat_member"}:
        payload = _object(update.raw_payload, update.update_type)
        return _membership(
            payload,
            platform_connection_id=platform_connection_id,
            is_assistant_membership=update.update_type == "my_chat_member",
        )
    raise TelegramNormalizationError("unsupported Telegram update type")


def _message(
    payload: dict[str, Any],
    *,
    platform_connection_id: UUID,
    assistant_platform_user_id: str,
    assistant_username: str | None,
    is_edit: bool,
) -> NormalizedMessage:
    conversation = _conversation(payload, platform_connection_id)
    sender = _participant(_object(payload, "from"), status=MembershipStatus.MEMBER)
    message_id = _identifier(payload, "message_id")
    date = _timestamp(payload, "date")
    text = _optional_string(payload, "text") or _optional_string(payload, "caption")
    has_sticker = isinstance(payload.get("sticker"), dict)
    message_type = "sticker" if has_sticker else "text" if text else "other"
    reply = payload.get("reply_to_message")
    reply_id: str | None = None
    replies_to_assistant = False
    if reply is not None:
        reply_object = _object_value(reply, "reply_to_message")
        reply_id = _identifier(reply_object, "message_id")
        reply_sender = reply_object.get("from")
        if isinstance(reply_sender, dict):
            replies_to_assistant = (
                _identifier(reply_sender, "id") == assistant_platform_user_id
            )
    entities = payload.get("entities") or payload.get("caption_entities") or []
    mentions = _mentions(entities, text, assistant_platform_user_id)
    mentions_assistant = any(
        reference.platform_user_id == assistant_platform_user_id
        or (
            assistant_username is not None
            and reference.username is not None
            and reference.username.casefold() == assistant_username.casefold()
        )
        for reference in mentions
    )
    thread_id = _optional_identifier(payload, "message_thread_id")
    return NormalizedMessage(
        conversation=conversation,
        sender=sender,
        platform_message_id=message_id,
        sent_at=date,
        message_type=message_type,
        text=text,
        reply_to_platform_message_id=reply_id,
        platform_thread_id=thread_id,
        mentions_assistant=mentions_assistant,
        replies_to_assistant=replies_to_assistant,
        mentions=mentions,
        is_edit=is_edit,
        edited_at=date if is_edit else None,
    )


def _membership(
    payload: dict[str, Any],
    *,
    platform_connection_id: UUID,
    is_assistant_membership: bool,
) -> NormalizedMembership:
    conversation = _conversation(payload, platform_connection_id)
    member = _object(payload, "new_chat_member")
    participant = _participant(
        _object(member, "user"),
        status=_membership_status(member.get("status")),
        role=_role(member.get("status")),
    )
    return NormalizedMembership(
        conversation=conversation,
        participant=participant,
        is_assistant_membership=is_assistant_membership,
        occurred_at=_timestamp(payload, "date"),
    )


def _conversation(
    payload: dict[str, Any], platform_connection_id: UUID
) -> ConversationIdentity:
    chat = _object(payload, "chat")
    raw_type = _required_string(chat, "type")
    try:
        conversation_type = ConversationType(raw_type)
    except ValueError as error:
        raise TelegramNormalizationError("unsupported Telegram chat type") from error
    return ConversationIdentity(
        platform=Platform.TELEGRAM,
        platform_connection_id=platform_connection_id,
        platform_conversation_id=_identifier(chat, "id"),
        conversation_type=conversation_type,
        title=_optional_string(chat, "title"),
        platform_thread_id=_optional_identifier(payload, "message_thread_id"),
    )


def _participant(
    payload: dict[str, Any],
    *,
    status: MembershipStatus,
    role: ParticipantRole = ParticipantRole.MEMBER,
) -> ParticipantIdentity:
    raw_status = payload.get("is_bot")
    if not isinstance(raw_status, bool):
        raise TelegramNormalizationError("Telegram user is_bot is required")
    first_name = _required_string(payload, "first_name")
    return ParticipantIdentity(
        platform_user_id=_identifier(payload, "id"),
        username=_optional_string(payload, "username"),
        display_name=first_name,
        is_bot=raw_status,
        membership_status=status,
        role=role,
    )


def _membership_status(value: object) -> MembershipStatus:
    if value in {"member", "administrator", "creator", "owner"}:
        return MembershipStatus.MEMBER
    if value == "restricted":
        return MembershipStatus.RESTRICTED
    if value == "left":
        return MembershipStatus.LEFT
    if value in {"kicked", "banned"}:
        return MembershipStatus.KICKED
    return MembershipStatus.UNKNOWN


def _role(value: object) -> ParticipantRole:
    if value in {"creator", "owner"}:
        return ParticipantRole.OWNER
    if value == "administrator":
        return ParticipantRole.ADMINISTRATOR
    return ParticipantRole.MEMBER


def _mentions(
    raw_entities: object, text: str | None, assistant_platform_user_id: str
) -> tuple[MentionReference, ...]:
    if not isinstance(raw_entities, list):
        raise TelegramNormalizationError("Telegram entities must be an array")
    references: list[MentionReference] = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            raise TelegramNormalizationError("Telegram entity must be an object")
        entity_type = raw_entity.get("type")
        if entity_type == "text_mention":
            user = raw_entity.get("user")
            if not isinstance(user, dict):
                raise TelegramNormalizationError(
                    "Telegram text_mention user is required"
                )
            references.append(MentionReference(_identifier(user, "id"), None))
        elif entity_type == "mention" and text is not None:
            offset = raw_entity.get("offset")
            length = raw_entity.get("length")
            if (
                isinstance(offset, int)
                and isinstance(length, int)
                and offset >= 0
                and length > 0
            ):
                segment = text[offset : offset + length]
                if segment.startswith("@"):
                    references.append(MentionReference(None, segment[1:]))
    return tuple(references)


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _object_value(payload.get(key), key)


def _object_value(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TelegramNormalizationError(f"Telegram {key} must be an object")
    return value


def _identifier(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise TelegramNormalizationError(f"Telegram {key} is required")
    return str(value)


def _optional_identifier(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise TelegramNormalizationError(f"Telegram {key} is invalid")
    return str(value)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TelegramNormalizationError(f"Telegram {key} is required")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TelegramNormalizationError(f"Telegram {key} is invalid")
    return value


def _timestamp(payload: dict[str, Any], key: str) -> datetime:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TelegramNormalizationError(f"Telegram {key} is required")
    return datetime.fromtimestamp(value, UTC)
