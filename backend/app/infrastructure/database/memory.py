"""Scoped explicit-memory persistence without semantic retrieval."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.memory import ExplicitMemoryDraft
from app.domain.persistence import (
    MemoryDeletionReason,
    MemoryStatus,
    MemoryVisibility,
    SemanticMemoryIndexOperation,
)
from app.infrastructure.database.models import (
    ConversationModel,
    MemoryEventModel,
    MemoryItemModel,
    ParticipantModel,
)
from app.infrastructure.database.semantic_memory import (
    SqlAlchemySemanticMemoryRepository,
)

semantic_memory_jobs = SqlAlchemySemanticMemoryRepository


@dataclass(frozen=True, slots=True)
class MemoryListEntry:
    item: MemoryItemModel
    creator_label: str


class SqlAlchemyMemoryRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_version: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_version = embedding_version

    @property
    def embedding_version(self) -> str | None:
        return self._embedding_version

    async def create(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
        creator_participant_id: UUID,
        source_message_id: UUID,
        source_command_job_id: UUID,
        draft: ExplicitMemoryDraft,
    ) -> MemoryItemModel:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(MemoryItemModel).where(
                        MemoryItemModel.source_command_job_id == source_command_job_id
                    )
                )
                if existing is not None:
                    return existing
                item = MemoryItemModel(
                    public_id=token_urlsafe(9).replace("-", "A").replace("_", "B"),
                    assistant_id=assistant_id,
                    platform_connection_id=platform_connection_id,
                    conversation_id=conversation_id,
                    creator_participant_id=creator_participant_id,
                    kind=draft.kind,
                    scope=draft.scope,
                    visibility=draft.visibility,
                    content=draft.content,
                    normalized_content_hash=sha256(draft.content.encode()).hexdigest(),
                    confidence=draft.confidence,
                    source_message_id=source_message_id,
                    source_command_job_id=source_command_job_id,
                )
                session.add(item)
                await session.flush()
                session.add(
                    MemoryEventModel(
                        memory_id=item.id,
                        command_job_id=source_command_job_id,
                        actor_participant_id=creator_participant_id,
                        action_code="created",
                    )
                )
                if self._embedding_version is not None:
                    await SqlAlchemySemanticMemoryRepository.schedule(
                        session,
                        item.id,
                        SemanticMemoryIndexOperation.UPSERT,
                        self._embedding_version,
                    )
                conversation = await session.get(ConversationModel, conversation_id)
                if conversation is not None:
                    conversation.memory_privacy_revision += 1
                return item

    async def active_for_conversation(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[MemoryListEntry]:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            rows = await session.execute(
                select(MemoryItemModel, ParticipantModel)
                .outerjoin(
                    ParticipantModel,
                    ParticipantModel.id == MemoryItemModel.creator_participant_id,
                )
                .where(
                    MemoryItemModel.assistant_id == assistant_id,
                    MemoryItemModel.platform_connection_id == platform_connection_id,
                    MemoryItemModel.conversation_id == conversation_id,
                    MemoryItemModel.status == MemoryStatus.ACTIVE,
                    MemoryItemModel.visibility == MemoryVisibility.SAME_CONVERSATION,
                    or_(
                        MemoryItemModel.expires_at.is_(None),
                        MemoryItemModel.expires_at > now,
                    ),
                )
                .order_by(MemoryItemModel.created_at, MemoryItemModel.id)
                .limit(limit)
            )
            return [
                MemoryListEntry(
                    item=item,
                    creator_label=(
                        "Deleted user"
                        if participant is None
                        or participant.privacy_deleted_at is not None
                        else participant.display_name
                    ),
                )
                for item, participant in rows
            ]

    async def count_active(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
    ) -> int:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.scalar(
                select(func.count(MemoryItemModel.id)).where(
                    MemoryItemModel.assistant_id == assistant_id,
                    MemoryItemModel.platform_connection_id == platform_connection_id,
                    MemoryItemModel.conversation_id == conversation_id,
                    MemoryItemModel.status == MemoryStatus.ACTIVE,
                    MemoryItemModel.visibility == MemoryVisibility.SAME_CONVERSATION,
                    or_(
                        MemoryItemModel.expires_at.is_(None),
                        MemoryItemModel.expires_at > now,
                    ),
                )
            )
            return int(result or 0)

    async def resolve_active(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
        public_id: str,
    ) -> MemoryItemModel | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            value = await session.scalar(
                select(MemoryItemModel).where(
                    MemoryItemModel.assistant_id == assistant_id,
                    MemoryItemModel.platform_connection_id == platform_connection_id,
                    MemoryItemModel.conversation_id == conversation_id,
                    MemoryItemModel.public_id == public_id,
                    MemoryItemModel.status == MemoryStatus.ACTIVE,
                    MemoryItemModel.visibility == MemoryVisibility.SAME_CONVERSATION,
                    or_(
                        MemoryItemModel.expires_at.is_(None),
                        MemoryItemModel.expires_at > now,
                    ),
                )
            )
            return value if isinstance(value, MemoryItemModel) else None

    async def delete(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
        public_id: str,
        actor_id: UUID,
        reason: MemoryDeletionReason,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                item = await session.scalar(
                    select(MemoryItemModel)
                    .where(
                        MemoryItemModel.assistant_id == assistant_id,
                        MemoryItemModel.platform_connection_id
                        == platform_connection_id,
                        MemoryItemModel.conversation_id == conversation_id,
                        MemoryItemModel.public_id == public_id,
                        or_(
                            MemoryItemModel.expires_at.is_(None),
                            MemoryItemModel.expires_at > now,
                        ),
                    )
                    .with_for_update()
                )
                if item is None or item.status != MemoryStatus.ACTIVE:
                    return False
                item.status = MemoryStatus.DELETED
                item.content = None
                item.normalized_content_hash = None
                item.deleted_at = now
                item.deletion_reason = reason
                session.add(
                    MemoryEventModel(
                        memory_id=item.id,
                        actor_participant_id=actor_id,
                        action_code="deleted",
                        deletion_reason=reason.value,
                    )
                )
                await semantic_memory_jobs.schedule_deletes_for_memory(
                    session,
                    item.id,
                    self._embedding_version,
                )
                conversation = await session.get(ConversationModel, conversation_id)
                if conversation is not None:
                    conversation.memory_privacy_revision += 1
                return True

    async def reset_group(
        self,
        *,
        assistant_id: UUID,
        platform_connection_id: UUID,
        conversation_id: UUID,
        actor_id: UUID,
        command_job_id: UUID,
    ) -> int:
        """Redact active group memory set-wise; audit contains only the count."""

        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                updated_ids = list(
                    await session.scalars(
                        update(MemoryItemModel)
                        .where(
                            MemoryItemModel.assistant_id == assistant_id,
                            MemoryItemModel.platform_connection_id
                            == platform_connection_id,
                            MemoryItemModel.conversation_id == conversation_id,
                            MemoryItemModel.status == MemoryStatus.ACTIVE,
                        )
                        .values(
                            status=MemoryStatus.DELETED,
                            content=None,
                            normalized_content_hash=None,
                            deleted_at=now,
                            deletion_reason=MemoryDeletionReason.ADMINISTRATOR_RESET,
                        )
                        .returning(MemoryItemModel.id)
                    )
                )
                count = len(updated_ids)
                for memory_id in updated_ids:
                    await semantic_memory_jobs.schedule_deletes_for_memory(
                        session,
                        memory_id,
                        self._embedding_version,
                    )
                session.add(
                    MemoryEventModel(
                        command_job_id=command_job_id,
                        actor_participant_id=actor_id,
                        action_code="group_reset",
                        deletion_reason=MemoryDeletionReason.ADMINISTRATOR_RESET.value,
                        affected_count=count,
                    )
                )
                if count:
                    conversation = await session.get(ConversationModel, conversation_id)
                    if conversation is not None:
                        conversation.memory_privacy_revision += 1
                return count
