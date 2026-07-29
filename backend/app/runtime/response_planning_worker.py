"""Dedicated durable response-planning worker; it never sends platform actions."""

import asyncio
import logging
import socket
from uuid import UUID

from app.application.model_provider import ModelProvider
from app.application.planning_service import generate_validated_plan
from app.application.prompting import build_generation_request
from app.application.response_plan import ResponsePlanPolicy
from app.core.config import Settings
from app.domain.planning import (
    GenerationAttemptKind,
    GenerationAttemptStatus,
    ProviderId,
    StickerIntent,
)
from app.infrastructure.database.context import SqlAlchemyConversationContextReader
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import ConversationModel
from app.infrastructure.database.planning import SqlAlchemyPlanningRepository
from app.infrastructure.model_providers import create_model_provider

logger = logging.getLogger(__name__)


def worker_name(settings: Settings) -> str:
    return f"planning-{socket.gethostname()}"


async def consume_once(
    settings: Settings,
    database: Database,
    owner: str | None = None,
    primary_provider: ModelProvider | None = None,
    fallback_provider: ModelProvider | None = None,
) -> int:
    if not settings.llm_enabled:
        return 0
    repository = SqlAlchemyPlanningRepository(database.session_factory)
    context_reader = SqlAlchemyConversationContextReader(
        database.session_factory, settings
    )
    claimed = await repository.claim(
        owner or worker_name(settings),
        settings.planning_job_batch_size,
        settings.planning_job_lease_seconds,
    )
    lease_owner = owner or worker_name(settings)
    owns_providers = primary_provider is None
    primary = primary_provider or create_model_provider(
        settings, ProviderId(settings.llm_primary_provider)
    )
    fallback = fallback_provider or (
        create_model_provider(settings, ProviderId(settings.llm_fallback_provider))
        if settings.llm_fallback_provider
        else None
    )
    try:
        for job in claimed:
            context = await context_reader.build_for_message(job.message_id)
            if context is None:
                await repository.complete(
                    job.id,
                    lease_owner,
                    None,
                    None,
                    None,
                    None,
                    job.prompt_version,
                    job.response_schema_version,
                )
                continue
            async with database.session_factory() as session:
                conversation = await session.get(ConversationModel, job.conversation_id)
            if conversation is None:
                await repository.complete(
                    job.id,
                    lease_owner,
                    None,
                    None,
                    None,
                    None,
                    job.prompt_version,
                    job.response_schema_version,
                )
                continue
            request = build_generation_request(
                planning_job_id=job.id,
                context=context,
                prompt_version=job.prompt_version,
                response_schema_version=job.response_schema_version,
                maximum_output_tokens=settings.llm_max_output_tokens,
                conversation_type=conversation.conversation_type.value,
                response_mode=conversation.response_mode.value,
            )
            policy = ResponsePlanPolicy(
                settings.response_plan_text_limit, frozenset(StickerIntent)
            )

            async def record(
                provider: ModelProvider,
                succeeded: bool,
                error: object,
                correction: int,
                planning_job_id: UUID = job.id,
            ) -> None:
                from app.application.model_provider import ProviderError

                provider_error = error if isinstance(error, ProviderError) else None
                await repository.record_attempt(
                    planning_job_id,
                    provider.provider_id,
                    provider.model,
                    GenerationAttemptKind.CORRECTION
                    if correction
                    else GenerationAttemptKind.PRIMARY,
                    GenerationAttemptStatus.SUCCEEDED
                    if succeeded
                    else GenerationAttemptStatus.FAILED,
                    provider_error.category if provider_error else None,
                )

            outcome = await generate_validated_plan(
                request,
                policy,
                primary,
                fallback,
                settings.llm_max_transport_attempts,
                settings.llm_max_correction_attempts,
                on_attempt=record,
            )
            provider = outcome.provider
            await repository.complete(
                job.id,
                lease_owner,
                outcome.candidate,
                provider.provider_id if provider else None,
                provider.model if provider else None,
                outcome.provider_error.category if outcome.provider_error else None,
                job.prompt_version,
                job.response_schema_version,
            )
        return len(claimed)
    finally:
        if owns_providers:
            await primary.aclose()
            if fallback is not None:
                await fallback.aclose()


async def run() -> None:
    settings = Settings()
    database = Database(settings)
    await database.start()
    try:
        while True:
            processed = await consume_once(settings, database)
            if processed == 0:
                await asyncio.sleep(settings.planning_job_poll_interval_seconds)
    except asyncio.CancelledError:
        raise
    finally:
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
