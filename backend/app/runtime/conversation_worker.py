"""Consume durable ingress references into normalized conversation state."""

import asyncio
import logging
import socket

from sqlalchemy import select

from app.application.ingress import IngressQueueEvent
from app.core.config import Settings
from app.infrastructure.database.conversation import (
    ConversationProcessingError,
    SqlAlchemyConversationProcessor,
)
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import (
    AssistantModel,
    IncomingPlatformUpdateModel,
    PlatformConnectionModel,
)
from app.infrastructure.queue.redis_streams import QueuePayloadError, RedisIngressQueue
from app.infrastructure.telegram.normalizer import (
    TelegramNormalizationError,
    normalize_telegram_update,
)
from app.infrastructure.telegram.updates import parse_telegram_update

logger = logging.getLogger(__name__)


def consumer_name(settings: Settings) -> str:
    return settings.conversation_consumer_name or f"conversation-{socket.gethostname()}"


async def process_event(
    event: IngressQueueEvent,
    settings: Settings,
    database: Database,
    processor: SqlAlchemyConversationProcessor,
) -> None:
    """Process one event; ledger permanent malformed data and raise transient errors."""

    if event.schema_version != 1:
        await processor.reject_malformed(event)
        return
    async with database.session_factory() as session:
        row = await session.execute(
            select(IncomingPlatformUpdateModel, PlatformConnectionModel, AssistantModel)
            .join(
                PlatformConnectionModel,
                IncomingPlatformUpdateModel.platform_connection_id
                == PlatformConnectionModel.id,
            )
            .join(
                AssistantModel,
                PlatformConnectionModel.assistant_id == AssistantModel.id,
            )
            .where(IncomingPlatformUpdateModel.id == event.incoming_update_id)
        )
        durable = row.first()
    if durable is None:
        raise ConversationProcessingError("durable ingress record is missing")
    incoming, connection, assistant = durable
    try:
        normalized = normalize_telegram_update(
            parse_telegram_update(incoming.raw_payload),
            platform_connection_id=connection.id,
            assistant_platform_user_id=connection.external_bot_id,
            assistant_display_name=assistant.name,
            assistant_username=None,
        )
    except (TelegramNormalizationError, ValueError):
        await processor.reject_malformed(event)
        return
    if (
        settings.demo_live_enabled
        and normalized.conversation.platform_conversation_id
        not in settings.demo_allowed_chat_ids
    ):
        await processor.ignore_not_allowed(event)
        return
    result = await processor.process(event, normalized)
    logger.info(
        "conversation event processed",
        extra={
            "incoming_update_id": str(result.incoming_update_id),
            "outcome": result.outcome,
            "duplicate": result.duplicate,
            "eligible": result.eligibility.eligible if result.eligibility else None,
        },
    )


async def consume_once(
    settings: Settings,
    database: Database,
    queue: RedisIngressQueue,
    processor: SqlAlchemyConversationProcessor,
    consumer: str | None = None,
    *,
    reclaim: bool = True,
) -> int:
    """Acknowledge queue entries only after durable transaction completion."""

    name = consumer or consumer_name(settings)
    await queue.ensure_group()
    entries = await queue.reclaim(name) if reclaim else []
    entries.extend(await queue.read_new(name))
    for entry_id, event in entries:
        await process_event(event, settings, database, processor)
        await queue.acknowledge(entry_id)
    return len(entries)


async def run() -> None:
    settings = Settings()
    database = Database(settings)
    queue = RedisIngressQueue(settings)
    await database.start()
    processor = SqlAlchemyConversationProcessor(
        database.session_factory,
        stickers_enabled=bool(settings.telegram_sticker_mapping),
    )
    try:
        while True:
            try:
                processed = await consume_once(settings, database, queue, processor)
                if processed == 0:
                    await asyncio.sleep(
                        settings.conversation_worker_poll_interval_seconds
                    )
            except QueuePayloadError:
                logger.exception("conversation queue payload rejected")
                await asyncio.sleep(settings.conversation_worker_poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("conversation worker transient failure")
                await asyncio.sleep(settings.conversation_worker_poll_interval_seconds)
    finally:
        await queue.aclose()
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
