"""PostgreSQL leasing and finalization for outbound delivery."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.outbound import (
    DeliveryAttemptStatus,
    DeliveryCertainty,
    OutboundActionStatus,
)
from app.domain.persistence import (
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
)
from app.infrastructure.database.models import (
    ConversationModel,
    MessageModel,
    OutboundActionModel,
    OutboundDeliveryAttemptModel,
    OutboundRecoveryEventModel,
)


class SqlAlchemyOutboundRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self, owner: str, limit: int, lease_seconds: int
    ) -> list[OutboundActionModel]:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                earlier = OutboundActionModel.__table__.alias("earlier")
                actions = list(
                    await session.scalars(
                        select(OutboundActionModel)
                        .where(
                            or_(
                                (
                                    OutboundActionModel.status
                                    == OutboundActionStatus.PENDING
                                )
                                & (OutboundActionModel.available_at <= now),
                                (
                                    OutboundActionModel.status
                                    == OutboundActionStatus.LEASED
                                )
                                & (OutboundActionModel.lease_expires_at < now),
                            ),
                            ~exists(
                                select(earlier.c.id).where(
                                    (
                                        earlier.c.response_plan_id
                                        == OutboundActionModel.response_plan_id
                                    )
                                    & (
                                        earlier.c.sequence_number
                                        < OutboundActionModel.sequence_number
                                    )
                                    & earlier.c.status.in_(["pending", "leased"])
                                )
                            ),
                        )
                        .order_by(
                            OutboundActionModel.available_at,
                            OutboundActionModel.created_at,
                            OutboundActionModel.id,
                        )
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                for action in actions:
                    if action.status == OutboundActionStatus.LEASED:
                        attempt = await session.scalar(
                            select(OutboundDeliveryAttemptModel)
                            .where(
                                OutboundDeliveryAttemptModel.outbound_action_id
                                == action.id,
                                OutboundDeliveryAttemptModel.attempt_number
                                == action.attempt_count,
                            )
                            .with_for_update()
                        )
                        if (
                            attempt is not None
                            and attempt.external_started_at is not None
                        ):
                            action.status = OutboundActionStatus.DELIVERY_UNKNOWN
                            action.last_error_category = "lease_expired"
                            action.last_error_at = now
                            action.completed_at = now
                            action.delivery_unknown_at = now
                            attempt.status = DeliveryAttemptStatus.UNKNOWN
                            attempt.certainty = DeliveryCertainty.UNKNOWN
                            attempt.error_category = "lease_expired"
                            attempt.finished_at = now
                        else:
                            action.status = OutboundActionStatus.PENDING
                            action.lease_owner = None
                            action.lease_expires_at = None
                            action.available_at = now
                            if attempt is not None:
                                attempt.status = DeliveryAttemptStatus.REJECTED
                                attempt.certainty = DeliveryCertainty.NOT_SENT
                                attempt.error_category = "lease_expired_before_send"
                                attempt.finished_at = now
                        continue
                    action.status = OutboundActionStatus.LEASED
                    action.lease_owner = owner
                    action.lease_expires_at = now + timedelta(seconds=lease_seconds)
                    action.attempt_count += 1
                    session.add(
                        OutboundDeliveryAttemptModel(
                            outbound_action_id=action.id,
                            attempt_number=action.attempt_count,
                            operation="sendMessage"
                            if action.kind.value == "text"
                            else "sendSticker",
                            status=DeliveryAttemptStatus.STARTED,
                            certainty=DeliveryCertainty.NOT_SENT,
                            started_at=now,
                        )
                    )
                return [a for a in actions if a.status == OutboundActionStatus.LEASED]

    async def mark_external_started(self, action_id: UUID, owner: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                action = await session.get(
                    OutboundActionModel, action_id, with_for_update=True
                )
                if (
                    action is None
                    or action.status != OutboundActionStatus.LEASED
                    or action.lease_owner != owner
                ):
                    return False
                attempt = await session.scalar(
                    select(OutboundDeliveryAttemptModel)
                    .where(
                        OutboundDeliveryAttemptModel.outbound_action_id == action.id,
                        OutboundDeliveryAttemptModel.attempt_number
                        == action.attempt_count,
                    )
                    .with_for_update()
                )
                if attempt is None:
                    return False
                attempt.external_started_at = datetime.now(UTC)
                return True

    async def finalize(
        self,
        action_id: UUID,
        owner: str,
        status: OutboundActionStatus,
        attempt_status: DeliveryAttemptStatus,
        certainty: DeliveryCertainty,
        *,
        error_category: str | None = None,
        error_code: str | None = None,
        retry_after_seconds: float | None = None,
        migration_conversation_id: str | None = None,
        available_at: datetime | None = None,
        delivered_platform_message_id: str | None = None,
        delivered_thread_id: str | None = None,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                action = await session.get(
                    OutboundActionModel, action_id, with_for_update=True
                )
                if (
                    action is None
                    or action.status != OutboundActionStatus.LEASED
                    or action.lease_owner != owner
                ):
                    return False
                now = datetime.now(UTC)
                attempt = await session.scalar(
                    select(OutboundDeliveryAttemptModel)
                    .where(
                        OutboundDeliveryAttemptModel.outbound_action_id == action.id,
                        OutboundDeliveryAttemptModel.attempt_number
                        == action.attempt_count,
                    )
                    .with_for_update()
                )
                if attempt is None:
                    return False
                attempt.status = attempt_status
                attempt.certainty = certainty
                attempt.finished_at = now
                attempt.error_category = error_category
                attempt.error_code = error_code
                attempt.retry_after_seconds = retry_after_seconds
                attempt.migration_conversation_id = migration_conversation_id
                action.status = status
                action.lease_owner = None
                action.lease_expires_at = None
                action.last_error_category = error_category
                action.last_error_code = error_code
                action.last_error_at = now if error_category else None
                action.completed_at = (
                    now if status != OutboundActionStatus.PENDING else None
                )
                action.delivery_unknown_at = (
                    now if status == OutboundActionStatus.DELIVERY_UNKNOWN else None
                )
                if available_at is not None:
                    action.available_at = available_at
                if migration_conversation_id is not None:
                    conversation = await session.get(
                        ConversationModel, action.conversation_id, with_for_update=True
                    )
                    if conversation is None:
                        return False
                    collision = await session.scalar(
                        select(ConversationModel.id).where(
                            ConversationModel.platform_connection_id
                            == conversation.platform_connection_id,
                            ConversationModel.platform_conversation_id
                            == migration_conversation_id,
                            ConversationModel.id != conversation.id,
                        )
                    )
                    if collision is not None:
                        action.status = OutboundActionStatus.PERMANENTLY_FAILED
                        action.available_at = now
                        action.last_error_category = "migration_identity_conflict"
                        action.completed_at = now
                    else:
                        conversation.platform_conversation_id = (
                            migration_conversation_id
                        )
                if delivered_platform_message_id is not None:
                    message = MessageModel(
                        conversation_id=action.conversation_id,
                        outbound_action_id=action.id,
                        platform_message_id=delivered_platform_message_id,
                        direction=MessageDirection.OUTGOING,
                        message_type=MessageType.TEXT
                        if action.kind.value == "text"
                        else MessageType.STICKER,
                        text=action.text if action.kind.value == "text" else None,
                        reply_to_message_id=action.reply_to_message_id,
                        processing_status=MessageProcessingStatus.PROCESSED,
                        platform_thread_id=delivered_thread_id,
                    )
                    session.add(message)
                    await session.flush()
                    action.delivered_message_id = message.id
                return True

    async def requeue_unknown(self, action_id: UUID, actor: str = "operator") -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                action = await session.get(
                    OutboundActionModel, action_id, with_for_update=True
                )
                if (
                    action is None
                    or action.status != OutboundActionStatus.DELIVERY_UNKNOWN
                ):
                    return False
                action.status = OutboundActionStatus.PENDING
                action.available_at = datetime.now(UTC)
                action.last_error_category = "operator_requeue_possible_duplicate"
                session.add(
                    OutboundRecoveryEventModel(
                        outbound_action_id=action.id,
                        event_type="requeued_possible_duplicate",
                        actor=actor,
                    )
                )
                return True
