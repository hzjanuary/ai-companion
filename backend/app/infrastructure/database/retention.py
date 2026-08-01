"""Bounded, content-clearing retention mutations for terminal records."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.base import Executable

from app.domain.outbound import OutboundActionStatus
from app.domain.persistence import CommandJobStatus, MessageProcessingStatus
from app.infrastructure.database.models import (
    IncomingPlatformUpdateModel,
    MessageModel,
    OutboundActionModel,
    ResponsePlanModel,
    TelegramCommandJobModel,
)


@dataclass(frozen=True, slots=True)
class RetentionCounts:
    incoming_updates: int = 0
    messages: int = 0
    response_plans: int = 0
    outbound_actions: int = 0
    command_arguments: int = 0


class SqlAlchemyRetentionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def redact_once(
        self, *, now: datetime | None = None, retention_days: int, batch_size: int
    ) -> RetentionCounts:
        current = now or datetime.now(UTC)
        cutoff = current - timedelta(days=retention_days)
        async with self._session_factory() as session:
            async with session.begin():
                return RetentionCounts(
                    incoming_updates=await _redact_updates(
                        session, cutoff, current, batch_size
                    ),
                    messages=await _redact_messages(
                        session, cutoff, current, batch_size
                    ),
                    response_plans=await _redact_plans(
                        session, cutoff, current, batch_size
                    ),
                    outbound_actions=await _redact_actions(
                        session, cutoff, current, batch_size
                    ),
                    command_arguments=await _redact_commands(
                        session, cutoff, current, batch_size
                    ),
                )


async def _redact_updates(
    session: AsyncSession, cutoff: datetime, now: datetime, limit: int
) -> int:
    ids = (
        select(IncomingPlatformUpdateModel.id)
        .where(
            IncomingPlatformUpdateModel.received_at <= cutoff,
            IncomingPlatformUpdateModel.payload_redacted_at.is_(None),
        )
        .order_by(
            IncomingPlatformUpdateModel.received_at, IncomingPlatformUpdateModel.id
        )
        .limit(limit)
    )
    return await _count(
        session,
        update(IncomingPlatformUpdateModel)
        .where(IncomingPlatformUpdateModel.id.in_(ids))
        .values(raw_payload={}, payload_redacted_at=now)
        .returning(IncomingPlatformUpdateModel.id),
    )


async def _redact_messages(
    session: AsyncSession, cutoff: datetime, now: datetime, limit: int
) -> int:
    ids = (
        select(MessageModel.id)
        .where(
            MessageModel.platform_sent_at <= cutoff,
            MessageModel.content_redacted_at.is_(None),
            MessageModel.processing_status != MessageProcessingStatus.PENDING,
        )
        .order_by(MessageModel.platform_sent_at, MessageModel.id)
        .limit(limit)
    )
    return await _count(
        session,
        update(MessageModel)
        .where(MessageModel.id.in_(ids))
        .values(text=None, metadata_={}, content_redacted_at=now)
        .returning(MessageModel.id),
    )


async def _redact_plans(
    session: AsyncSession, cutoff: datetime, now: datetime, limit: int
) -> int:
    ids = (
        select(ResponsePlanModel.id)
        .where(
            ResponsePlanModel.created_at <= cutoff,
            ResponsePlanModel.content_redacted_at.is_(None),
        )
        .order_by(ResponsePlanModel.created_at, ResponsePlanModel.id)
        .limit(limit)
    )
    return await _count(
        session,
        update(ResponsePlanModel)
        .where(ResponsePlanModel.id.in_(ids))
        .values(text=None, content_redacted_at=now)
        .returning(ResponsePlanModel.id),
    )


async def _redact_actions(
    session: AsyncSession, cutoff: datetime, now: datetime, limit: int
) -> int:
    terminal = (
        OutboundActionStatus.DELIVERED,
        OutboundActionStatus.SKIPPED,
        OutboundActionStatus.PERMANENTLY_FAILED,
        OutboundActionStatus.DELIVERY_UNKNOWN,
    )
    ids = (
        select(OutboundActionModel.id)
        .where(
            OutboundActionModel.created_at <= cutoff,
            OutboundActionModel.payload_redacted_at.is_(None),
            OutboundActionModel.status.in_(terminal),
        )
        .order_by(OutboundActionModel.created_at, OutboundActionModel.id)
        .limit(limit)
    )
    return await _count(
        session,
        update(OutboundActionModel)
        .where(OutboundActionModel.id.in_(ids))
        .values(text=None, sticker_intent=None, payload_redacted_at=now)
        .returning(OutboundActionModel.id),
    )


async def _redact_commands(
    session: AsyncSession, cutoff: datetime, now: datetime, limit: int
) -> int:
    ids = (
        select(TelegramCommandJobModel.id)
        .where(
            TelegramCommandJobModel.completed_at <= cutoff,
            TelegramCommandJobModel.arguments_redacted_at.is_(None),
            TelegramCommandJobModel.status.in_(
                (CommandJobStatus.COMPLETED, CommandJobStatus.FAILED)
            ),
        )
        .order_by(TelegramCommandJobModel.completed_at, TelegramCommandJobModel.id)
        .limit(limit)
    )
    return await _count(
        session,
        update(TelegramCommandJobModel)
        .where(TelegramCommandJobModel.id.in_(ids))
        .values(arguments="", arguments_redacted_at=now)
        .returning(TelegramCommandJobModel.id),
    )


async def _count(session: AsyncSession, statement: Executable) -> int:
    result = await session.scalars(statement)
    return len(list(result))
