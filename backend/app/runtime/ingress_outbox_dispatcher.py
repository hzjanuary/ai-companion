"""Transactional outbox dispatcher for Redis ingress-reference events."""

import asyncio

from app.core.config import Settings
from app.infrastructure.database.database import Database
from app.infrastructure.database.ingress import SqlAlchemyDurableIngressRepository
from app.infrastructure.queue.redis_streams import RedisIngressQueue


async def dispatch_once(
    settings: Settings,
    repository: SqlAlchemyDurableIngressRepository,
    queue: RedisIngressQueue,
) -> int:
    events = await repository.pending_events(settings.ingress_outbox_batch_size)
    for event in events:
        queue_event = await repository.event_for(event.id)
        if queue_event is None:
            continue
        try:
            await queue.publish(queue_event)
        except Exception:
            await repository.mark_publish_failed(
                event.id, settings.ingress_outbox_poll_interval_seconds
            )
            continue
        await repository.mark_published(event.id)
    return len(events)


async def run() -> None:
    settings = Settings()
    database = Database(settings)
    queue = RedisIngressQueue(settings)
    await database.start()
    repository = SqlAlchemyDurableIngressRepository(
        database.session_factory, settings.ingress_event_schema_version
    )
    try:
        while True:
            processed = await dispatch_once(settings, repository, queue)
            if processed == 0:
                await asyncio.sleep(settings.ingress_outbox_poll_interval_seconds)
    except asyncio.CancelledError:
        raise
    finally:
        await queue.aclose()
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
