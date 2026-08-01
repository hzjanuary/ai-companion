"""Dedicated no-network raw-content retention runtime."""

import argparse
import asyncio
import logging

from app.core.config import Settings
from app.infrastructure.database.database import Database
from app.infrastructure.database.retention import SqlAlchemyRetentionRepository

logger = logging.getLogger(__name__)


async def consume_once(settings: Settings, database: Database) -> int:
    counts = await SqlAlchemyRetentionRepository(database.session_factory).redact_once(
        retention_days=settings.raw_content_retention_days,
        batch_size=settings.retention_batch_size,
    )
    total = sum(
        (
            counts.incoming_updates,
            counts.messages,
            counts.response_plans,
            counts.outbound_actions,
            counts.command_arguments,
        )
    )
    logger.info("retention_redaction_complete counts=%s", counts)
    return total


async def run(once: bool) -> None:
    settings = Settings()
    if not settings.retention_worker_enabled:
        return
    database = Database(settings)
    await database.start()
    try:
        while True:
            processed = await consume_once(settings, database)
            if once:
                return
            if processed == 0:
                await asyncio.sleep(settings.retention_worker_poll_interval_seconds)
    finally:
        await database.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    asyncio.run(run(parser.parse_args().once))
