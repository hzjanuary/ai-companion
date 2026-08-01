"""Set-based primary-database privacy erasure without content-bearing audit data."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.base import Executable

from app.domain.persistence import MemoryDeletionReason, MemoryStatus
from app.infrastructure.database.models import (
    ConversationModel,
    ConversationProcessingRecordModel,
    IncomingPlatformUpdateModel,
    MemoryEventModel,
    MemoryItemModel,
    MessageModel,
    OutboundActionModel,
    ParticipantModel,
    PlatformConnectionModel,
    ResponsePlanModel,
    ResponsePlanningJobModel,
    TelegramCommandJobModel,
)


@dataclass(frozen=True, slots=True)
class PrivacyErasureResult:
    participants: int
    messages: int
    incoming_updates: int
    command_arguments: int
    response_plans: int
    outbound_actions: int
    memories: int
    already_deleted: bool


class SqlAlchemyPrivacyRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def erase_subject(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        platform_user_id: str,
        command_job_id: UUID,
        now: datetime | None = None,
    ) -> PrivacyErasureResult:
        """Clear subject content across this Assistant/connection, idempotently."""

        current = now or datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                participant_ids = list(
                    await session.scalars(
                        select(ParticipantModel.id)
                        .join(
                            ConversationModel,
                            ParticipantModel.conversation_id == ConversationModel.id,
                        )
                        .join(
                            PlatformConnectionModel,
                            ConversationModel.platform_connection_id
                            == PlatformConnectionModel.id,
                        )
                        .where(
                            ConversationModel.platform_connection_id
                            == platform_connection_id,
                            PlatformConnectionModel.assistant_id == assistant_id,
                            ParticipantModel.platform_user_id == platform_user_id,
                        )
                        .with_for_update()
                    )
                )
                if not participant_ids:
                    return PrivacyErasureResult(0, 0, 0, 0, 0, 0, 0, True)
                active = await session.scalar(
                    select(ParticipantModel.id).where(
                        ParticipantModel.id.in_(participant_ids),
                        ParticipantModel.privacy_deleted_at.is_(None),
                    )
                )
                if active is None:
                    return PrivacyErasureResult(0, 0, 0, 0, 0, 0, 0, True)
                participant_count = await _count(
                    session,
                    update(ParticipantModel)
                    .where(ParticipantModel.id.in_(participant_ids))
                    .values(
                        username=None,
                        display_name="Deleted user",
                        metadata_={},
                        mention_allowed=False,
                        teasing_allowed=False,
                        privacy_deleted_at=current,
                    )
                    .returning(ParticipantModel.id),
                )
                message_ids = select(MessageModel.id).where(
                    MessageModel.participant_id.in_(participant_ids)
                )
                message_count = await _count(
                    session,
                    update(MessageModel)
                    .where(MessageModel.id.in_(message_ids))
                    .values(text=None, metadata_={}, content_redacted_at=current)
                    .returning(MessageModel.id),
                )
                update_ids = select(
                    ConversationProcessingRecordModel.incoming_update_id
                ).where(ConversationProcessingRecordModel.message_id.in_(message_ids))
                update_count = await _count(
                    session,
                    update(IncomingPlatformUpdateModel)
                    .where(IncomingPlatformUpdateModel.id.in_(update_ids))
                    .values(raw_payload={}, payload_redacted_at=current)
                    .returning(IncomingPlatformUpdateModel.id),
                )
                command_count = await _count(
                    session,
                    update(TelegramCommandJobModel)
                    .where(TelegramCommandJobModel.participant_id.in_(participant_ids))
                    .values(arguments="", arguments_redacted_at=current)
                    .returning(TelegramCommandJobModel.id),
                )
                plan_ids = select(ResponsePlanModel.id).where(
                    ResponsePlanModel.command_job_id.in_(
                        select(TelegramCommandJobModel.id).where(
                            TelegramCommandJobModel.participant_id.in_(participant_ids)
                        )
                    )
                    | ResponsePlanModel.planning_job_id.in_(
                        select(ResponsePlanningJobModel.id).where(
                            ResponsePlanningJobModel.message_id.in_(message_ids)
                        )
                    )
                )
                plan_count = await _count(
                    session,
                    update(ResponsePlanModel)
                    .where(ResponsePlanModel.id.in_(plan_ids))
                    .values(text=None, content_redacted_at=current)
                    .returning(ResponsePlanModel.id),
                )
                action_count = await _count(
                    session,
                    update(OutboundActionModel)
                    .where(OutboundActionModel.response_plan_id.in_(plan_ids))
                    .values(text=None, sticker_intent=None, payload_redacted_at=current)
                    .returning(OutboundActionModel.id),
                )
                memory_ids = list(
                    await session.scalars(
                        update(MemoryItemModel)
                        .where(
                            MemoryItemModel.assistant_id == assistant_id,
                            MemoryItemModel.platform_connection_id
                            == platform_connection_id,
                            MemoryItemModel.creator_participant_id.in_(participant_ids),
                            MemoryItemModel.status == MemoryStatus.ACTIVE,
                        )
                        .values(
                            status=MemoryStatus.DELETED,
                            content=None,
                            normalized_content_hash=None,
                            deleted_at=current,
                            deletion_reason=MemoryDeletionReason.PROFILE_DELETION,
                        )
                        .returning(MemoryItemModel.id)
                    )
                )
                for memory_id in memory_ids:
                    session.add(
                        MemoryEventModel(
                            memory_id=memory_id,
                            command_job_id=command_job_id,
                            action_code="profile_deleted",
                            deletion_reason=MemoryDeletionReason.PROFILE_DELETION.value,
                        )
                    )
                conversation_ids = select(ConversationModel.id).where(
                    ConversationModel.id.in_(
                        select(ParticipantModel.conversation_id).where(
                            ParticipantModel.id.in_(participant_ids)
                        )
                    )
                )
                await session.execute(
                    update(ConversationModel)
                    .where(ConversationModel.id.in_(conversation_ids))
                    .values(
                        memory_privacy_revision=ConversationModel.memory_privacy_revision
                        + 1
                    )
                )
                return PrivacyErasureResult(
                    participant_count,
                    message_count,
                    update_count,
                    command_count,
                    plan_count,
                    action_count,
                    len(memory_ids),
                    False,
                )


async def _count(session: AsyncSession, statement: Executable) -> int:
    result = await session.scalars(statement)
    return len(list(result))
