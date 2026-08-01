"""Dedicated durable response-planning worker; it never sends platform actions."""

import asyncio
import logging
import socket
from uuid import UUID

from app.application.model_provider import ModelProvider, ProviderError
from app.application.personality import merge_effective
from app.application.planning_service import generate_validated_plan
from app.application.ports.rate_limit import RateLimiter
from app.application.prompting import build_generation_request
from app.application.rate_limit_rules import generation_rules, provider_rule
from app.application.response_plan import ResponsePlanPolicy
from app.core.config import Settings
from app.domain.planning import (
    GenerationAttemptKind,
    GenerationAttemptStatus,
    ProviderErrorCategory,
    ProviderId,
    StickerIntent,
)
from app.domain.rate_limit import RateLimitDecision, RateLimitOperation
from app.domain.safety import (
    SafetyDecision,
    SafetyOutcome,
    SafetyPolicyVersion,
    SafetyReasonCode,
    SafetyStage,
)
from app.infrastructure.database.context import SqlAlchemyConversationContextReader
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import (
    ConversationConfigurationRevisionModel,
    ConversationModel,
    PersonalityProfileModel,
    PersonalityProfileVersionModel,
)
from app.infrastructure.database.personality import revision_overrides, version_values
from app.infrastructure.database.planning import SqlAlchemyPlanningRepository
from app.infrastructure.database.safety import SqlAlchemySafetyRepository
from app.infrastructure.model_providers import create_model_provider
from app.infrastructure.rate_limit import RateLimitUnavailable, RedisRateLimiter

logger = logging.getLogger(__name__)


def worker_name(settings: Settings) -> str:
    return f"{settings.planning_owner_name}-{socket.gethostname()}"


async def consume_once(
    settings: Settings,
    database: Database,
    owner: str | None = None,
    primary_provider: ModelProvider | None = None,
    fallback_provider: ModelProvider | None = None,
    rate_limiter: RateLimiter | None = None,
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
    owns_limiter = rate_limiter is None and settings.rate_limit_enabled
    limiter = (
        rate_limiter
        if rate_limiter is not None
        else RedisRateLimiter(settings)
        if settings.rate_limit_enabled
        else None
    )
    safety_repository = SqlAlchemySafetyRepository(database.session_factory)
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
                current_revision = (
                    await session.get(
                        ConversationConfigurationRevisionModel,
                        conversation.current_configuration_revision_id,
                    )
                    if conversation is not None
                    and conversation.current_configuration_revision_id is not None
                    else None
                )
                revision = (
                    await session.get(
                        ConversationConfigurationRevisionModel,
                        job.configuration_revision_id,
                    )
                    if job.configuration_revision_id
                    else None
                )
                version = (
                    await session.get(
                        PersonalityProfileVersionModel,
                        job.personality_profile_version_id,
                    )
                    if job.personality_profile_version_id
                    else None
                )
                profile = (
                    await session.get(PersonalityProfileModel, version.profile_id)
                    if version is not None
                    else None
                )
            if (
                conversation is None
                or current_revision is None
                or revision is None
                or version is None
                or profile is None
            ):
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
            memory_privacy_revision = conversation.memory_privacy_revision
            if (
                conversation.status.value == "paused"
                or current_revision.response_mode.value == "paused"
            ):
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
            effective = merge_effective(
                version_values(version),
                revision_overrides(revision),
                profile_id=profile.id,
                profile_version_id=version.id,
                profile_version_number=version.version_number,
                configuration_revision_id=revision.id,
                configuration_revision_number=revision.revision_number,
            )
            request = build_generation_request(
                planning_job_id=job.id,
                context=context,
                prompt_version=job.prompt_version,
                response_schema_version=job.response_schema_version,
                maximum_output_tokens=settings.llm_max_output_tokens,
                conversation_type=conversation.conversation_type.value,
                response_mode=conversation.response_mode.value,
                effective_personality=effective,
                stickers_enabled=revision.stickers_enabled,
            )
            teasing_level = effective["teasing_level"]
            policy = ResponsePlanPolicy(
                min(
                    settings.response_plan_text_limit,
                    280 if effective["default_length"] == "short" else 500,
                ),
                frozenset(StickerIntent) if revision.stickers_enabled else frozenset(),
                teasing_permitted=isinstance(teasing_level, int | float)
                and teasing_level > 0,
            )

            # Do not send context assembled before a durable privacy/memory change.
            async with database.session_factory() as session:
                fresh_conversation = await session.get(
                    ConversationModel, job.conversation_id
                )
            if (
                fresh_conversation is None
                or fresh_conversation.memory_privacy_revision != memory_privacy_revision
            ):
                await repository.release_for_context_change(job.id, lease_owner)
                continue

            participant_id = context.current.participant_id
            await safety_repository.record_decision(
                planning_job_id=job.id,
                response_plan_id=None,
                conversation_id=job.conversation_id,
                decision=SafetyDecision(
                    SafetyPolicyVersion.V1,
                    SafetyStage.PRE_GENERATION,
                    SafetyOutcome.ALLOW,
                ),
            )
            if limiter is not None:
                try:
                    decision = await limiter.check(
                        RateLimitOperation.GENERATION,
                        generation_rules(
                            settings,
                            connection_id=conversation.platform_connection_id,
                            conversation_id=conversation.id,
                            participant_id=participant_id,
                        ),
                    )
                except RateLimitUnavailable:
                    decision = RateLimitDecision(
                        False,
                        retry_after_seconds=settings.rate_limit_redis_failure_retry_seconds,
                    )
                await safety_repository.record_rate_limit(
                    planning_job_id=job.id,
                    outbound_action_id=None,
                    operation=RateLimitOperation.GENERATION,
                    decision=decision,
                    provider_id=primary.provider_id.value,
                    configuration_version=SafetyPolicyVersion.V1.value,
                )
                if not decision.allowed:
                    logger.info(
                        "rate_limit_denied operation=generation planning_job_id=%s "
                        "scope=%s retry_after_seconds=%s",
                        job.id,
                        decision.limiting_scope,
                        decision.retry_after_seconds,
                    )
                    await safety_repository.record_decision(
                        planning_job_id=job.id,
                        response_plan_id=None,
                        conversation_id=job.conversation_id,
                        decision=SafetyDecision(
                            SafetyPolicyVersion.V1,
                            SafetyStage.PRE_GENERATION,
                            SafetyOutcome.SILENT,
                            SafetyReasonCode.RATE_LIMITED,
                        ),
                    )
                    await repository.release_for_rate_limit(
                        job.id,
                        lease_owner,
                        decision.retry_after_seconds
                        or settings.rate_limit_redis_failure_retry_seconds,
                    )
                    continue

            async def before_provider(
                provider: ModelProvider,
                planning_job_id: UUID = job.id,
            ) -> ProviderError | None:
                if limiter is None:
                    return None
                try:
                    decision = await limiter.check(
                        RateLimitOperation.GENERATION,
                        (provider_rule(settings, provider.provider_id.value),),
                    )
                except RateLimitUnavailable:
                    decision = RateLimitDecision(
                        False,
                        retry_after_seconds=settings.rate_limit_redis_failure_retry_seconds,
                    )
                await safety_repository.record_rate_limit(
                    planning_job_id=planning_job_id,
                    outbound_action_id=None,
                    operation=RateLimitOperation.GENERATION,
                    decision=decision,
                    provider_id=provider.provider_id.value,
                    configuration_version=SafetyPolicyVersion.V1.value,
                )
                if decision.allowed:
                    return None
                logger.info(
                    "rate_limit_denied operation=provider planning_job_id=%s "
                    "scope=%s retry_after_seconds=%s",
                    planning_job_id,
                    decision.limiting_scope,
                    decision.retry_after_seconds,
                )
                return ProviderError(
                    ProviderErrorCategory.RATE_LIMITED,
                    provider.provider_id,
                    provider.model,
                    True,
                    "generate",
                    "distributed rate limit denied provider I/O",
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
                before_provider=before_provider,
            )
            provider = outcome.provider
            if (
                outcome.provider_error is not None
                and outcome.provider_error.category
                == ProviderErrorCategory.RATE_LIMITED
            ):
                await safety_repository.record_decision(
                    planning_job_id=job.id,
                    response_plan_id=None,
                    conversation_id=job.conversation_id,
                    decision=SafetyDecision(
                        SafetyPolicyVersion.V1,
                        SafetyStage.PRE_GENERATION,
                        SafetyOutcome.SILENT,
                        SafetyReasonCode.RATE_LIMITED,
                    ),
                )
                await repository.release_for_rate_limit(
                    job.id,
                    lease_owner,
                    settings.rate_limit_redis_failure_retry_seconds,
                )
                continue
            response_plan_id = await repository.complete(
                job.id,
                lease_owner,
                outcome.candidate,
                provider.provider_id if provider else None,
                provider.model if provider else None,
                outcome.provider_error.category if outcome.provider_error else None,
                job.prompt_version,
                job.response_schema_version,
            )
            await safety_repository.record_decision(
                planning_job_id=job.id,
                response_plan_id=response_plan_id,
                conversation_id=job.conversation_id,
                decision=SafetyDecision(
                    SafetyPolicyVersion.V1,
                    SafetyStage.POST_GENERATION,
                    SafetyOutcome.ALLOW
                    if outcome.candidate is not None
                    else SafetyOutcome.REFUSE,
                    SafetyReasonCode.MODEL_REFUSAL
                    if outcome.provider_error
                    and outcome.provider_error.category.value == "safety_refusal"
                    else None,
                    transformed=outcome.candidate is not None
                    and outcome.candidate.text is not None
                    and outcome.candidate.text.startswith("I will keep"),
                ),
            )
        return len(claimed)
    finally:
        if owns_providers:
            await primary.aclose()
            if fallback is not None:
                await fallback.aclose()
        if owns_limiter and limiter is not None:
            await limiter.aclose()


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
