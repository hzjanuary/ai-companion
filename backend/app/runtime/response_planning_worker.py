"""Dedicated durable response-planning worker; it never sends platform actions."""

import asyncio
import logging
import socket
from datetime import UTC, datetime
from uuid import UUID

from app.application.ambient import apply_ambient_post_policy
from app.application.model_provider import ModelProvider, ProviderError
from app.application.personality import merge_effective
from app.application.planning_service import generate_validated_plan
from app.application.ports.concurrency import ConcurrencyLimiter
from app.application.ports.rate_limit import RateLimiter
from app.application.ports.telemetry import MetricsRecorder, NoOpMetricsRecorder
from app.application.prompting import build_generation_request
from app.application.rate_limit_rules import generation_rules, provider_rule
from app.application.response_plan import ResponsePlanCandidate, ResponsePlanPolicy
from app.core.config import Settings
from app.domain.ambient import (
    AMBIENT_POLICY_VERSION,
    AMBIENT_PROFILES,
    AmbientReason,
    ParticipationTrigger,
    is_sampled,
)
from app.domain.planning import (
    GenerationAttemptKind,
    GenerationAttemptStatus,
    PlanReasonCode,
    ProviderErrorCategory,
    ProviderId,
    StickerIntent,
)
from app.domain.rate_limit import RateLimitDecision, RateLimitOperation
from app.domain.recovery import RecoveryDisposition, RecoveryKind, RecoveryReason
from app.domain.safety import (
    SafetyDecision,
    SafetyOutcome,
    SafetyPolicyVersion,
    SafetyReasonCode,
    SafetyStage,
)
from app.infrastructure.concurrency import RedisConcurrencyLimiter
from app.infrastructure.concurrency_provider import ConcurrencyLimitedProvider
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
from app.infrastructure.database.recovery import SqlAlchemyRecoveryRepository
from app.infrastructure.database.safety import SqlAlchemySafetyRepository
from app.infrastructure.model_providers import create_model_provider
from app.infrastructure.rate_limit import RateLimitUnavailable, RedisRateLimiter
from app.infrastructure.telemetry import InMemoryMetricsRecorder
from app.runtime.lifecycle import RuntimeLifecycle

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
    concurrency_limiter: ConcurrencyLimiter | None = None,
    telemetry: MetricsRecorder | None = None,
) -> int:
    if not settings.llm_enabled:
        return 0
    repository = SqlAlchemyPlanningRepository(database.session_factory)
    recorder = telemetry or NoOpMetricsRecorder()
    context_reader = SqlAlchemyConversationContextReader(
        database.session_factory, settings, recorder
    )
    claimed = await repository.claim(
        owner or worker_name(settings),
        settings.planning_job_batch_size,
        settings.planning_job_lease_seconds,
    )
    lease_owner = owner or worker_name(settings)
    owns_providers = primary_provider is None
    owns_limiter = rate_limiter is None and settings.rate_limit_enabled
    owns_concurrency = (
        concurrency_limiter is None and settings.provider_concurrency_enabled
    )
    limiter = (
        rate_limiter
        if rate_limiter is not None
        else RedisRateLimiter(settings)
        if settings.rate_limit_enabled
        else None
    )
    concurrency = (
        concurrency_limiter
        if concurrency_limiter is not None
        else RedisConcurrencyLimiter(settings)
        if settings.provider_concurrency_enabled
        else None
    )
    safety_repository = SqlAlchemySafetyRepository(database.session_factory)
    for _ in claimed:
        recorder.increment("january_planning_jobs_total", outcome="claimed")
    primary = primary_provider or create_model_provider(
        settings, ProviderId(settings.llm_primary_provider)
    )
    fallback = fallback_provider or (
        create_model_provider(settings, ProviderId(settings.llm_fallback_provider))
        if settings.llm_fallback_provider
        else None
    )
    if concurrency is not None:
        primary = ConcurrencyLimitedProvider(primary, concurrency, recorder)
        if fallback is not None:
            fallback = ConcurrencyLimitedProvider(fallback, concurrency, recorder)
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
            if context.historical_summary is not None:
                recorder.increment(
                    "january_summary_context_usage_total",
                    outcome="used",
                    schema=context.historical_summary.schema_version,
                )
            else:
                recorder.increment(
                    "january_summary_context_usage_total",
                    outcome="raw_fallback",
                    schema="none",
                )
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
            ambient = job.trigger == ParticipationTrigger.AMBIENT
            ambient_profile = current_revision.ambient_frequency.value

            async def complete_ambient_silence(
                reason: AmbientReason,
                job_id: UUID = job.id,
                prompt_version: str = job.prompt_version,
                schema_version: str = job.response_schema_version,
                profile: str = ambient_profile,
            ) -> None:
                await repository.complete(
                    job_id,
                    lease_owner,
                    ResponsePlanCandidate(
                        should_respond=False,
                        reason_code=PlanReasonCode.SILENCE,
                        confidence=1.0,
                    ),
                    None,
                    None,
                    None,
                    prompt_version,
                    schema_version,
                    reason.value,
                )
                recorder.increment(
                    "january_ambient_decisions_total",
                    outcome=reason.value,
                    profile=profile,
                    policy=AMBIENT_POLICY_VERSION,
                )

            if ambient and (
                not settings.ambient_selective_enabled
                or current_revision.response_mode.value != "ambient_selective"
            ):
                await complete_ambient_silence(AmbientReason.FEATURE_DISABLED)
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
                trigger=job.trigger.value,
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

            if ambient:
                if job.configuration_revision_id is None or not is_sampled(
                    context.current.id,
                    job.configuration_revision_id,
                    current_revision.ambient_frequency,
                    job.ambient_policy_version or AMBIENT_POLICY_VERSION,
                ):
                    await complete_ambient_silence(AmbientReason.NOT_SAMPLED)
                    continue
                last_ambient = await repository.latest_confirmed_ambient_response(
                    conversation.id
                )
                profile_policy = AMBIENT_PROFILES[current_revision.ambient_frequency]
                if (
                    last_ambient is not None
                    and (datetime.now(UTC) - last_ambient).total_seconds()
                    < profile_policy.cooldown_seconds
                ):
                    await complete_ambient_silence(AmbientReason.COOLDOWN)
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
                    recorder.increment(
                        "january_rate_limit_events_total",
                        operation="generation",
                        scope=decision.limiting_scope.value
                        if decision.limiting_scope
                        else "unavailable",
                        result="denied",
                    )
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
                recorder.increment(
                    "january_rate_limit_events_total",
                    operation="generation",
                    scope=decision.limiting_scope.value
                    if decision.limiting_scope
                    else "unavailable",
                    result="denied",
                )
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
                telemetry=recorder,
                pricing=settings.metrics_provider_pricing,
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
            if (
                outcome.provider_error is not None
                and outcome.provider_error.category
                == ProviderErrorCategory.CONCURRENCY_LIMITED
            ):
                await repository.release_for_rate_limit(
                    job.id,
                    lease_owner,
                    settings.rate_limit_redis_failure_retry_seconds,
                )
                continue
            candidate = outcome.candidate
            ambient_reason: str | None = None
            if ambient and candidate is not None:
                profile_policy = AMBIENT_PROFILES[current_revision.ambient_frequency]
                candidate, ambient_decision = apply_ambient_post_policy(
                    candidate, profile_policy.minimum_confidence
                )
                ambient_reason = ambient_decision.value
                recorder.increment(
                    "january_ambient_decisions_total",
                    outcome=ambient_reason,
                    profile=current_revision.ambient_frequency.value,
                    policy=AMBIENT_POLICY_VERSION,
                )
            response_plan_id = await repository.complete(
                job.id,
                lease_owner,
                candidate,
                provider.provider_id if provider else None,
                provider.model if provider else None,
                outcome.provider_error.category if outcome.provider_error else None,
                job.prompt_version,
                job.response_schema_version,
                ambient_reason,
            )
            if outcome.candidate is None and outcome.provider_error is not None:
                await SqlAlchemyRecoveryRepository(database.session_factory).classify(
                    RecoveryKind.PLANNING,
                    job.id,
                    RecoveryDisposition.DEAD_LETTER,
                    RecoveryReason.PROVIDER_RETRY_EXHAUSTED
                    if outcome.provider_error.retryable
                    else RecoveryReason.INVALID_TERMINAL_PLAN,
                )
                recorder.increment(
                    "january_dead_letter_events_total",
                    work_kind="planning",
                    reason=(
                        "provider_retry_exhausted"
                        if outcome.provider_error.retryable
                        else "invalid_terminal_plan"
                    ),
                )
                recorder.increment(
                    "january_recovery_events_total",
                    work_kind="planning",
                    operation="classify",
                    outcome="dead_letter",
                    reason=(
                        "provider_retry_exhausted"
                        if outcome.provider_error.retryable
                        else "invalid_terminal_plan"
                    ),
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
        if owns_concurrency and concurrency is not None:
            await concurrency.aclose()


async def run() -> None:
    settings = Settings()
    database = Database(settings)
    telemetry = (
        InMemoryMetricsRecorder() if settings.metrics_enabled else NoOpMetricsRecorder()
    )
    await database.start()
    lifecycle = RuntimeLifecycle("response_planning_worker")
    lifecycle.install()
    try:
        while not lifecycle.stopping:
            processed = await consume_once(settings, database, telemetry=telemetry)
            if processed == 0:
                await lifecycle.wait(settings.planning_job_poll_interval_seconds)
    except asyncio.CancelledError:
        raise
    finally:
        lifecycle.close()
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
