"""PostgreSQL reader that converts persisted messages into context values."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.context import (
    ContextMemory,
    ContextMessage,
    ConversationContext,
    build_context,
)
from app.application.conversation import CharacterTokenEstimator
from app.core.config import Settings
from app.domain.persistence import MemoryStatus, MemoryVisibility
from app.infrastructure.database.models import (
    ConversationModel,
    MemoryItemModel,
    MessageModel,
    ParticipantModel,
    PlatformConnectionModel,
)


class SqlAlchemyConversationContextReader:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def build_for_message(
        self, message_id: UUID, now: datetime | None = None
    ) -> ConversationContext | None:
        current_time = now or datetime.now(UTC)
        async with self._session_factory() as session:
            current = await self._load_message(session, message_id)
            if current is None:
                return None
            cutoff = current_time - timedelta(
                days=self._settings.context_max_history_age_days
            )
            rows = await session.execute(
                select(MessageModel, ParticipantModel)
                .outerjoin(
                    ParticipantModel, MessageModel.participant_id == ParticipantModel.id
                )
                .where(
                    MessageModel.conversation_id == current.conversation_id,
                    MessageModel.platform_sent_at >= cutoff,
                )
                .order_by(MessageModel.platform_sent_at.desc(), MessageModel.id.desc())
                .limit(
                    self._settings.context_recent_message_limit
                    + self._settings.context_reply_chain_depth
                    + 10
                )
            )
            candidates = tuple(
                self._to_context(message, participant) for message, participant in rows
            )
            memory_rows = await session.execute(
                select(MemoryItemModel, ParticipantModel)
                .join(
                    ConversationModel,
                    ConversationModel.id == MemoryItemModel.conversation_id,
                )
                .join(
                    PlatformConnectionModel,
                    PlatformConnectionModel.id
                    == ConversationModel.platform_connection_id,
                )
                .outerjoin(
                    ParticipantModel,
                    ParticipantModel.id == MemoryItemModel.creator_participant_id,
                )
                .where(
                    MemoryItemModel.conversation_id == current.conversation_id,
                    MemoryItemModel.platform_connection_id
                    == ConversationModel.platform_connection_id,
                    MemoryItemModel.assistant_id
                    == PlatformConnectionModel.assistant_id,
                    MemoryItemModel.status == MemoryStatus.ACTIVE,
                    MemoryItemModel.visibility == MemoryVisibility.SAME_CONVERSATION,
                    or_(
                        MemoryItemModel.expires_at.is_(None),
                        MemoryItemModel.expires_at > current_time,
                    ),
                )
                .order_by(MemoryItemModel.created_at, MemoryItemModel.id)
                .limit(self._settings.memory_context_limit)
            )
            memories = tuple(
                self._to_memory(memory, participant)
                for memory, participant in memory_rows
            )
        return build_context(
            current=current,
            candidates=candidates,
            now=current_time,
            recent_limit=self._settings.context_recent_message_limit,
            reply_chain_depth=self._settings.context_reply_chain_depth,
            token_budget=self._settings.context_token_budget,
            character_limit=self._settings.context_message_character_limit,
            max_age_days=self._settings.context_max_history_age_days,
            estimator=CharacterTokenEstimator(),
            explicit_memories=memories,
            memory_character_budget=self._settings.memory_context_character_budget,
        )

    async def _load_message(
        self, session: AsyncSession, message_id: UUID
    ) -> ContextMessage | None:
        row = await session.execute(
            select(MessageModel, ParticipantModel)
            .outerjoin(
                ParticipantModel, MessageModel.participant_id == ParticipantModel.id
            )
            .where(MessageModel.id == message_id)
        )
        result = row.first()
        return self._to_context(*result) if result is not None else None

    @staticmethod
    def _to_context(
        message: MessageModel, participant: ParticipantModel | None
    ) -> ContextMessage:
        return ContextMessage(
            id=message.id,
            conversation_id=message.conversation_id,
            participant_id=message.participant_id,
            platform_thread_id=message.platform_thread_id,
            text=message.text,
            sent_at=message.platform_sent_at or message.created_at,
            reply_to_message_id=message.reply_to_message_id,
            sender_display_name=participant.display_name if participant else "Unknown",
            mention_allowed=participant.mention_allowed if participant else False,
            teasing_allowed=participant.teasing_allowed if participant else False,
            privacy_deleted=participant.privacy_deleted_at is not None
            if participant
            else False,
        )

    @staticmethod
    def _to_memory(
        memory: MemoryItemModel, participant: ParticipantModel | None
    ) -> ContextMemory:
        return ContextMemory(
            public_id=memory.public_id,
            content=memory.content or "",
            created_at=memory.created_at,
            creator_label=(
                "Deleted user"
                if participant is None or participant.privacy_deleted_at is not None
                else participant.display_name
            ),
        )
