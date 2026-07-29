"""Durable outbound delivery worker with explicit ambiguity handling."""

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.application.ports.outbound import StickerAssetResolver
from app.application.ports.platform import (
    PlatformAdapterError,
    PlatformCapability,
    SendStickerRequest,
    SendTextRequest,
    SentMessage,
)
from app.core.config import Settings
from app.domain.conversation import MembershipStatus
from app.domain.outbound import (
    DeliveryAttemptStatus,
    DeliveryCertainty,
    OutboundActionKind,
    OutboundActionStatus,
)
from app.domain.persistence import AssistantStatus
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import (
    AssistantModel,
    ConversationModel,
    MessageModel,
    OutboundActionModel,
    ParticipantModel,
    PlatformConnectionModel,
)
from app.infrastructure.database.outbound import SqlAlchemyOutboundRepository
from app.infrastructure.telegram.adapter import TelegramAdapter
from app.infrastructure.telegram.assets import TelegramStickerAssetResolver
from app.infrastructure.telegram.rendering import (
    MentionTarget,
    render_text_with_mentions,
)


def worker_name(settings: Settings) -> str:
    return f"{settings.outbound_owner_name}-{socket.gethostname()}"


async def consume_once(
    settings: Settings, database: Database, adapter: TelegramAdapter | None = None
) -> int:
    if not settings.outbound_delivery_enabled:
        return 0
    owner = worker_name(settings)
    repository = SqlAlchemyOutboundRepository(database.session_factory)
    actions = await repository.claim(
        owner, settings.outbound_batch_size, settings.outbound_lease_seconds
    )
    owns_adapter = adapter is None
    sender = adapter or TelegramAdapter(settings)
    asset_resolver = TelegramStickerAssetResolver(settings)
    try:
        for action in actions:
            try:
                resolved = await _resolve(database, action.conversation_id, action)
                if resolved is None:
                    await repository.finalize(
                        action.id,
                        owner,
                        OutboundActionStatus.SKIPPED,
                        DeliveryAttemptStatus.REJECTED,
                        DeliveryCertainty.NOT_SENT,
                        error_category="outbound_precondition_failed",
                    )
                    continue
                conversation, reply, participants = resolved
                capability = (
                    PlatformCapability.SEND_TEXT
                    if action.kind == OutboundActionKind.TEXT
                    else PlatformCapability.SEND_STICKER
                )
                if capability not in sender.capabilities:
                    await repository.finalize(
                        action.id,
                        owner,
                        OutboundActionStatus.SKIPPED,
                        DeliveryAttemptStatus.REJECTED,
                        DeliveryCertainty.NOT_SENT,
                        error_category="unsupported_platform_capability",
                    )
                    continue
                if action.kind == OutboundActionKind.STICKER and (
                    action.sticker_intent is None
                    or asset_resolver.resolve(action.sticker_intent) is None
                ):
                    await repository.finalize(
                        action.id,
                        owner,
                        OutboundActionStatus.SKIPPED,
                        DeliveryAttemptStatus.REJECTED,
                        DeliveryCertainty.NOT_SENT,
                        error_category="sticker_not_configured",
                    )
                    continue
                if not await repository.mark_external_started(action.id, owner):
                    continue
                sent = await _send(
                    sender,
                    settings,
                    asset_resolver,
                    action,
                    conversation,
                    reply,
                    participants,
                )
            except PlatformAdapterError as error:
                await _record_error(
                    repository, action.id, owner, action.attempt_count, settings, error
                )
            else:
                await repository.finalize(
                    action.id,
                    owner,
                    OutboundActionStatus.DELIVERED,
                    DeliveryAttemptStatus.CONFIRMED,
                    DeliveryCertainty.CONFIRMED,
                    delivered_platform_message_id=sent.platform_message_id,
                    delivered_thread_id=sent.message_thread_id,
                )
        return len(actions)
    finally:
        if owns_adapter:
            await sender.aclose()


async def _resolve(
    database: Database, conversation_id: UUID, action: OutboundActionModel
) -> tuple[ConversationModel, MessageModel | None, list[ParticipantModel]] | None:
    async with database.session_factory() as session:
        conversation = await session.get(ConversationModel, conversation_id)
        if conversation is None:
            return None
        connection = await session.get(
            PlatformConnectionModel, conversation.platform_connection_id
        )
        if (
            connection is None
            or conversation.status.value != "active"
            or connection.status.value != "active"
        ):
            return None
        assistant = await session.get(AssistantModel, connection.assistant_id)
        invalid_membership = conversation.assistant_membership_status in {
            MembershipStatus.LEFT,
            MembershipStatus.KICKED,
            MembershipStatus.RESTRICTED,
        }
        if (
            assistant is None
            or assistant.status != AssistantStatus.ACTIVE
            or invalid_membership
        ):
            return None
        reply_id = action.reply_to_message_id
        reply = await session.get(MessageModel, reply_id) if reply_id else None
        if reply_id is not None and (
            reply is None or reply.conversation_id != conversation.id
        ):
            return None
        identifiers = [UUID(value) for value in action.mention_participant_ids]
        fetched = list(
            await session.scalars(
                select(ParticipantModel).where(
                    ParticipantModel.conversation_id == conversation.id,
                    ParticipantModel.id.in_(identifiers),
                    ParticipantModel.mention_allowed.is_(True),
                )
            )
        )
        by_id = {participant.id: participant for participant in fetched}
        participants = [
            by_id[identifier] for identifier in identifiers if identifier in by_id
        ]
        return conversation, reply, participants


async def _send(
    sender: TelegramAdapter,
    settings: Settings,
    asset_resolver: StickerAssetResolver,
    action: OutboundActionModel,
    conversation: ConversationModel,
    reply: MessageModel | None,
    participants: list[ParticipantModel],
) -> SentMessage:
    reply_id = reply.platform_message_id if reply else None
    thread_id = reply.platform_thread_id if reply else action.message_thread_id
    if action.kind == OutboundActionKind.TEXT:
        rendered, entities = render_text_with_mentions(
            action.text or "",
            tuple(MentionTarget(item.id, item.username) for item in participants),
        )
        return await sender.send_text(
            SendTextRequest(
                conversation_id=conversation.platform_conversation_id,
                text=rendered,
                reply_to_message_id=reply_id,
                message_thread_id=thread_id,
                entities=entities,
                disable_notification=settings.telegram_disable_notification,
                protect_content=settings.telegram_protect_content,
            )
        )
    intent = action.sticker_intent
    asset = asset_resolver.resolve(intent) if intent else None
    if asset is None:
        raise RuntimeError("configured sticker action reached send without an asset")
    return await sender.send_sticker(
        SendStickerRequest(
            conversation_id=conversation.platform_conversation_id,
            asset_reference=asset,
            reply_to_message_id=reply_id,
            message_thread_id=thread_id,
            disable_notification=settings.telegram_disable_notification,
            protect_content=settings.telegram_protect_content,
        )
    )


async def _record_error(
    repository: SqlAlchemyOutboundRepository,
    action_id: UUID,
    owner: str,
    attempts: int,
    settings: Settings,
    error: PlatformAdapterError,
) -> None:
    code = str(error.telegram_error_code) if error.telegram_error_code else None
    if error.delivery_certainty == DeliveryCertainty.UNKNOWN:
        await repository.finalize(
            action_id,
            owner,
            OutboundActionStatus.DELIVERY_UNKNOWN,
            DeliveryAttemptStatus.UNKNOWN,
            DeliveryCertainty.UNKNOWN,
            error_category=error.category.value,
            error_code=code,
        )
        return
    retryable = error.retryable and (
        attempts < settings.outbound_max_confirmed_rejection_attempts
    )
    if error.replacement_conversation_id is not None and attempts > 1:
        retryable = False
    delay = error.retry_after_seconds or min(
        settings.outbound_retry_max_delay_seconds,
        settings.outbound_retry_min_delay_seconds * (2 ** (attempts - 1)),
    )
    await repository.finalize(
        action_id,
        owner,
        OutboundActionStatus.PENDING
        if retryable
        else OutboundActionStatus.PERMANENTLY_FAILED,
        DeliveryAttemptStatus.REJECTED,
        error.delivery_certainty,
        error_category=error.category.value,
        error_code=code,
        retry_after_seconds=float(delay) if retryable else None,
        migration_conversation_id=error.replacement_conversation_id,
        available_at=datetime.now(UTC) + timedelta(seconds=delay)
        if retryable
        else None,
    )


async def run() -> None:
    settings = Settings()
    database = Database(settings)
    await database.start()
    try:
        while True:
            if await consume_once(settings, database) == 0:
                await asyncio.sleep(settings.outbound_poll_interval_seconds)
    finally:
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
