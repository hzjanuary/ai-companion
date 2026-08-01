"""PostgreSQL lease and finalization repository for response planning."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.outbound import compile_outbound_actions
from app.application.response_plan import ResponsePlanCandidate
from app.domain.planning import (
    GenerationAttemptKind,
    GenerationAttemptStatus,
    PlanningJobStatus,
    ProviderErrorCategory,
    ProviderId,
)
from app.infrastructure.database.models import (
    MessageModel,
    ModelGenerationAttemptModel,
    OutboundActionModel,
    ResponsePlanModel,
    ResponsePlanningJobModel,
)


class SqlAlchemyPlanningRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(
        self, owner: str, limit: int, lease_seconds: int
    ) -> list[ResponsePlanningJobModel]:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                jobs = list(
                    await session.scalars(
                        select(ResponsePlanningJobModel)
                        .where(
                            or_(
                                (
                                    ResponsePlanningJobModel.status
                                    == PlanningJobStatus.PENDING
                                )
                                & (ResponsePlanningJobModel.available_at <= now),
                                (
                                    ResponsePlanningJobModel.status
                                    == PlanningJobStatus.LEASED
                                )
                                & (ResponsePlanningJobModel.lease_expires_at < now),
                            )
                        )
                        .order_by(
                            ResponsePlanningJobModel.available_at,
                            ResponsePlanningJobModel.created_at,
                            ResponsePlanningJobModel.id,
                        )
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                for job in jobs:
                    job.status = PlanningJobStatus.LEASED
                    job.lease_owner = owner
                    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
                    job.attempt_count += 1
                return jobs

    async def record_attempt(
        self,
        job_id: UUID,
        provider: ProviderId,
        model: str,
        kind: GenerationAttemptKind,
        status: GenerationAttemptStatus,
        error: ProviderErrorCategory | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                previous = await session.scalar(
                    select(func.max(ModelGenerationAttemptModel.attempt_number)).where(
                        ModelGenerationAttemptModel.planning_job_id == job_id
                    )
                )
                number = (previous or 0) + 1
                session.add(
                    ModelGenerationAttemptModel(
                        planning_job_id=job_id,
                        attempt_number=number,
                        provider=provider,
                        model=model,
                        attempt_kind=kind,
                        status=status,
                        error_category=error,
                        retryable=error
                        in {
                            ProviderErrorCategory.RATE_LIMITED,
                            ProviderErrorCategory.TIMEOUT,
                            ProviderErrorCategory.TRANSPORT,
                            ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                        }
                        if error
                        else None,
                    )
                )

    async def release_for_context_change(self, job_id: UUID, owner: str) -> bool:
        """Release a lease when privacy/memory changed before provider I/O."""

        async with self._session_factory() as session:
            async with session.begin():
                job = await session.get(
                    ResponsePlanningJobModel, job_id, with_for_update=True
                )
                if (
                    job is None
                    or job.status != PlanningJobStatus.LEASED
                    or job.lease_owner != owner
                ):
                    return False
                job.status = PlanningJobStatus.PENDING
                job.available_at = datetime.now(UTC)
                job.lease_owner = None
                job.lease_expires_at = None
                return True

    async def complete(
        self,
        job_id: UUID,
        owner: str,
        candidate: ResponsePlanCandidate | None,
        provider: ProviderId | None,
        model: str | None,
        error: ProviderErrorCategory | None,
        prompt_version: str,
        schema_version: str,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                job = await session.get(
                    ResponsePlanningJobModel, job_id, with_for_update=True
                )
                if (
                    job is None
                    or job.status != PlanningJobStatus.LEASED
                    or job.lease_owner != owner
                ):
                    return False
                now = datetime.now(UTC)
                job.selected_provider = provider
                job.selected_model = model
                job.last_error_category = error
                job.completed_at = now
                job.lease_owner = None
                job.lease_expires_at = None
                if candidate is None:
                    job.status = (
                        PlanningJobStatus.NO_RESPONSE
                        if error == ProviderErrorCategory.SAFETY_REFUSAL
                        else PlanningJobStatus.FAILED
                    )
                    return True
                plan = ResponsePlanModel(
                    planning_job_id=job.id,
                    should_respond=candidate.should_respond,
                    reason_code=candidate.reason_code,
                    text=candidate.text,
                    reply_to_message_id=candidate.reply_to_message_id,
                    mention_participant_ids=[
                        str(value) for value in candidate.mentions
                    ],
                    sticker_intent=candidate.sticker_intent,
                    confidence=candidate.confidence,
                    language=candidate.language,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                )
                session.add(plan)
                await session.flush()
                for action in compile_outbound_actions(plan.id, candidate):
                    source_message = await session.get(MessageModel, job.message_id)
                    session.add(
                        OutboundActionModel(
                            response_plan_id=plan.id,
                            conversation_id=job.conversation_id,
                            sequence_number=action.sequence_number,
                            idempotency_key=action.idempotency_key,
                            kind=action.kind,
                            reply_to_message_id=action.reply_to_message_id,
                            message_thread_id=source_message.platform_thread_id
                            if source_message is not None
                            else None,
                            mention_participant_ids=[
                                str(value) for value in action.mention_participant_ids
                            ],
                            text=action.text,
                            sticker_intent=action.sticker_intent,
                        )
                    )
                job.status = (
                    PlanningJobStatus.COMPLETED
                    if candidate.should_respond
                    else PlanningJobStatus.NO_RESPONSE
                )
                return True
