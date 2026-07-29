"""PostgreSQL reader that converts persisted messages into context values."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.context import ContextMessage, ConversationContext, build_context
from app.application.conversation import CharacterTokenEstimator
from app.core.config import Settings
from app.infrastructure.database.models import MessageModel, ParticipantModel


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
            platform_thread_id=message.platform_thread_id,
            text=message.text,
            sent_at=message.platform_sent_at or message.created_at,
            reply_to_message_id=message.reply_to_message_id,
            sender_display_name=participant.display_name if participant else "Unknown",
            mention_allowed=participant.mention_allowed if participant else False,
            teasing_allowed=participant.teasing_allowed if participant else False,
        )
