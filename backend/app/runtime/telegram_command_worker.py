"""Dedicated deterministic Telegram command worker.

It claims durable jobs, performs live authorization only for protected group
changes, and hands replies to the normal outbound delivery worker.
"""

import asyncio
import logging
import socket
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.application.commands import CommandOperation, command_response, parse_command
from app.application.memory import MemoryValidationError, normalize_explicit_memory
from app.application.ports.platform import PlatformAdapter, PlatformAdapterError
from app.application.ports.telemetry import NoOpMetricsRecorder
from app.application.response_plan import ResponsePlanCandidate
from app.core.config import Settings, get_settings
from app.domain.persistence import (
    CommandAuthorizationOutcome,
    ConversationType,
    MemoryDeletionReason,
    MemoryScope,
    PersonalityProfileStatus,
    ResponseMode,
)
from app.domain.planning import PlanReasonCode
from app.infrastructure.database.commands import SqlAlchemyCommandRepository
from app.infrastructure.database.database import Database
from app.infrastructure.database.group_configuration import ConfigurationChange
from app.infrastructure.database.memory import SqlAlchemyMemoryRepository
from app.infrastructure.database.models import (
    AssistantModel,
    ConversationConfigurationRevisionModel,
    ConversationModel,
    ParticipantModel,
    PersonalityProfileModel,
    PersonalityProfileVersionModel,
    PlatformConnectionModel,
)
from app.infrastructure.database.privacy import SqlAlchemyPrivacyRepository
from app.infrastructure.telegram.adapter import TelegramAdapter
from app.infrastructure.telemetry import InMemoryMetricsRecorder

logger = logging.getLogger(__name__)


def worker_name(settings: Settings) -> str:
    return f"{settings.command_owner_name}-{socket.gethostname()}"


async def consume_once(
    settings: Settings,
    database: Database,
    adapter: PlatformAdapter | None = None,
    owner: str | None = None,
) -> int:
    if not settings.command_worker_enabled:
        return 0
    lease_owner = owner or worker_name(settings)
    repository = SqlAlchemyCommandRepository(database.session_factory)
    memory_repository = SqlAlchemyMemoryRepository(database.session_factory)
    jobs = await repository.claim(
        lease_owner, settings.command_batch_size, settings.command_lease_seconds
    )
    owns_adapter = adapter is None
    client: PlatformAdapter | None = None
    try:
        for job in jobs:
            request = parse_command(job.command_name, job.arguments)
            (
                language,
                conversation,
                participant,
                assistant,
                expected_revision,
            ) = await _load_state(database, job.id)
            if conversation is None or participant is None or assistant is None:
                await _finish(repository, job, lease_owner, "safe_failure", language)
                continue
            if request.operation == CommandOperation.USAGE:
                await _finish(repository, job, lease_owner, "usage", language)
                continue
            if request.operation == CommandOperation.UNKNOWN:
                await _finish(repository, job, lease_owner, "unknown", language)
                continue
            if request.operation == CommandOperation.MEMORY:
                await _handle_memory_command(
                    database,
                    repository,
                    memory_repository,
                    job,
                    lease_owner,
                    request,
                    language,
                    conversation,
                    participant,
                    assistant,
                    settings,
                    adapter,
                )
                continue
            protected = request.operation == CommandOperation.CONFIGURATION
            if protected and conversation.conversation_type != ConversationType.PRIVATE:
                if client is None:
                    client = adapter or TelegramAdapter(settings)
                try:
                    member = await client.get_chat_member(
                        conversation.platform_conversation_id,
                        participant.platform_user_id,
                    )
                except PlatformAdapterError as error:
                    if (
                        error.retryable
                        and job.attempt_count
                        < settings.command_max_authorization_attempts
                    ):
                        await repository.retry(
                            job.id,
                            lease_owner,
                            _authorization_retry_delay(settings, job.attempt_count),
                        )
                        continue
                    code = "temporary_failure" if error.retryable else "denied"
                    outcome = (
                        CommandAuthorizationOutcome.RETRYABLE_FAILURE
                        if error.retryable
                        else CommandAuthorizationOutcome.PERMANENT_FAILURE
                    )
                    await _finish(repository, job, lease_owner, code, language, outcome)
                    continue
                if not (member.is_administrator or member.is_owner):
                    await _finish(
                        repository,
                        job,
                        lease_owner,
                        "denied",
                        language,
                        CommandAuthorizationOutcome.DENIED,
                    )
                    continue
                authorization = CommandAuthorizationOutcome.ALLOWED
            else:
                authorization = None
            if request.operation == CommandOperation.PREFERENCE:
                value = request.value
                if not isinstance(value, bool):
                    await _finish(repository, job, lease_owner, "usage", language)
                    continue
                preference = (
                    (value, None) if request.name == "mentions" else (None, value)
                )
                await _finish(
                    repository,
                    job,
                    lease_owner,
                    "success",
                    language,
                    preference=preference,
                )
                continue
            if request.operation == CommandOperation.CONFIGURATION:
                if request.name == "personality":
                    profile_version_id, profile_code = await _resolve_profile_version(
                        database,
                        assistant.id,
                        request.value,
                    )
                    if profile_version_id is None:
                        await _finish(
                            repository,
                            job,
                            lease_owner,
                            profile_code,
                            language,
                            authorization,
                        )
                        continue
                    change = ConfigurationChange(
                        profile_version_id=profile_version_id,
                        source="telegram_command",
                        actor_participant_id=participant.id,
                    )
                    await repository.complete_configuration(
                        job.id,
                        lease_owner,
                        assistant.id,
                        change,
                        _candidate(job.message_id, "success", language),
                        authorization,
                        expected_revision=expected_revision,
                        unchanged_candidate=_candidate(
                            job.message_id, "unchanged", language
                        ),
                        conflict_candidate=_candidate(
                            job.message_id, "conflict", language
                        ),
                    )
                    continue
                code, configuration_change, resume = _configuration_change(
                    settings, participant, request
                )
                if configuration_change is None:
                    await _finish(
                        repository, job, lease_owner, code, language, authorization
                    )
                    continue
                await repository.complete_configuration(
                    job.id,
                    lease_owner,
                    assistant.id,
                    configuration_change,
                    _candidate(job.message_id, code, language),
                    authorization,
                    expected_revision=expected_revision,
                    unchanged_candidate=_candidate(
                        job.message_id, "unchanged", language
                    ),
                    conflict_candidate=_candidate(job.message_id, "conflict", language),
                    resume=resume,
                )
                continue
            code = (
                "help"
                if request.name == "help"
                else "start"
                if request.name == "start"
                else "success"
            )
            if request.name in {
                "status",
                "mode",
                "personality",
                "stickers",
                "mentions",
                "teasing",
            }:
                code = "status"
            detail = await _read_detail(
                database,
                conversation,
                participant,
                assistant,
                request,
                settings.command_max_profiles_shown,
            )
            await _finish(repository, job, lease_owner, code, language, detail=detail)
    finally:
        if owns_adapter and isinstance(client, TelegramAdapter):
            await client.aclose()
    return len(jobs)


async def _handle_memory_command(
    database: Database,
    commands: SqlAlchemyCommandRepository,
    memories: SqlAlchemyMemoryRepository,
    job: object,
    owner: str,
    request: object,
    language: str,
    conversation: ConversationModel,
    participant: ParticipantModel,
    assistant: AssistantModel,
    settings: Settings,
    adapter: PlatformAdapter | None,
) -> None:
    """Execute only explicit-memory commands; none construct a provider request."""

    from app.application.commands import CommandRequest
    from app.infrastructure.database.models import TelegramCommandJobModel

    assert isinstance(job, TelegramCommandJobModel)
    assert isinstance(request, CommandRequest)
    scope = (
        MemoryScope.PRIVATE_CONVERSATION
        if conversation.conversation_type == ConversationType.PRIVATE
        else MemoryScope.GROUP_CONVERSATION
    )
    common = {
        "assistant_id": assistant.id,
        "platform_connection_id": conversation.platform_connection_id,
        "conversation_id": conversation.id,
    }
    if request.action == "summary":
        count = await memories.count_active(**common)
        detail = (
            f" active={count}; /memory list; /memory remember <fact>; "
            "/forget <id>; group reset requires an administrator."
        )
        await _finish(commands, job, owner, "memory_summary", language, detail=detail)
        return
    if request.action == "list":
        items = await memories.active_for_conversation(**common, limit=11)
        detail = _memory_list_detail(items[:10], more=len(items) > 10)
        await _finish(commands, job, owner, "memory_summary", language, detail=detail)
        return
    if request.action == "remember":
        if not isinstance(request.value, str):
            await _finish(commands, job, owner, "usage", language)
            return
        try:
            draft = normalize_explicit_memory(request.value, scope)
        except MemoryValidationError:
            await _finish(commands, job, owner, "usage", language)
            return
        await memories.create(
            **common,
            creator_participant_id=participant.id,
            source_message_id=job.message_id,
            source_command_job_id=job.id,
            draft=draft,
        )
        await _finish(commands, job, owner, "memory_saved", language)
        return
    if request.action == "forget":
        if not isinstance(request.value, str):
            await _finish(commands, job, owner, "usage", language)
            return
        target = await memories.resolve_active(**common, public_id=request.value)
        if target is None:
            await _finish(commands, job, owner, "memory_missing", language)
            return
        is_creator = target.creator_participant_id == participant.id
        if (
            not is_creator
            and conversation.conversation_type == ConversationType.PRIVATE
        ):
            await _finish(commands, job, owner, "denied", language)
            return
        if not is_creator:
            authorized = await _fresh_group_admin(
                commands,
                job,
                owner,
                language,
                conversation,
                participant,
                settings,
                adapter,
            )
            if not authorized:
                return
        deleted = await memories.delete(
            **common,
            public_id=request.value,
            actor_id=participant.id,
            reason=(
                MemoryDeletionReason.CREATOR_REQUEST
                if is_creator
                else MemoryDeletionReason.USER_REQUEST
            ),
        )
        await _finish(
            commands,
            job,
            owner,
            "memory_deleted" if deleted else "memory_missing",
            language,
        )
        return
    if request.action == "reset_group":
        if conversation.conversation_type == ConversationType.PRIVATE:
            await _finish(commands, job, owner, "memory_private_reset", language)
            return
        authorized = await _fresh_group_admin(
            commands,
            job,
            owner,
            language,
            conversation,
            participant,
            settings,
            adapter,
        )
        if not authorized:
            return
        count = await memories.reset_group(
            **common,
            actor_id=participant.id,
            command_job_id=job.id,
        )
        await _finish(
            commands, job, owner, "memory_reset", language, detail=f" count={count}"
        )
        return
    if request.action == "warning":
        await _finish(commands, job, owner, "forget_me_warning", language)
        return
    if request.action == "confirm":
        result = await SqlAlchemyPrivacyRepository(
            database.session_factory
        ).erase_subject(
            assistant_id=assistant.id,
            platform_connection_id=conversation.platform_connection_id,
            platform_user_id=participant.platform_user_id,
            command_job_id=job.id,
        )
        await _finish(
            commands,
            job,
            owner,
            "forget_me_unchanged" if result.already_deleted else "forget_me_done",
            language,
        )
        return
    await _finish(commands, job, owner, "safe_failure", language)


def _memory_list_detail(items: Sequence[object], *, more: bool) -> str:
    from app.infrastructure.database.memory import MemoryListEntry

    lines: list[str] = []
    for entry in items:
        assert isinstance(entry, MemoryListEntry)
        item = entry.item
        preview = (item.content or "")[:80]
        suffix = "..." if item.content and len(item.content) > len(preview) else ""
        created = item.created_at.date().isoformat()
        lines.append(
            f" {item.public_id} [{created}; {entry.creator_label}]: {preview}{suffix}"
        )
    detail = "".join(lines) if lines else " none"
    return f"{detail} more=1" if more else detail


async def _fresh_group_admin(
    commands: SqlAlchemyCommandRepository,
    job: object,
    owner: str,
    language: str,
    conversation: ConversationModel,
    participant: ParticipantModel,
    settings: Settings,
    adapter: PlatformAdapter | None,
) -> bool:
    from app.infrastructure.database.models import TelegramCommandJobModel

    assert isinstance(job, TelegramCommandJobModel)
    client = adapter or TelegramAdapter(settings)
    try:
        member = await client.get_chat_member(
            conversation.platform_conversation_id, participant.platform_user_id
        )
    except PlatformAdapterError as error:
        if adapter is None and isinstance(client, TelegramAdapter):
            await client.aclose()
        if (
            error.retryable
            and job.attempt_count < settings.command_max_authorization_attempts
        ):
            await commands.retry(
                job.id, owner, _authorization_retry_delay(settings, job.attempt_count)
            )
        else:
            await _finish(
                commands,
                job,
                owner,
                "temporary_failure" if error.retryable else "denied",
                language,
                (
                    CommandAuthorizationOutcome.RETRYABLE_FAILURE
                    if error.retryable
                    else CommandAuthorizationOutcome.PERMANENT_FAILURE
                ),
            )
        return False
    if adapter is None and isinstance(client, TelegramAdapter):
        await client.aclose()
    if not (member.is_administrator or member.is_owner):
        await _finish(
            commands,
            job,
            owner,
            "denied",
            language,
            CommandAuthorizationOutcome.DENIED,
        )
        return False
    return True


async def _load_state(
    database: Database, job_id: UUID
) -> tuple[
    str,
    ConversationModel | None,
    ParticipantModel | None,
    AssistantModel | None,
    int | None,
]:
    from app.infrastructure.database.models import TelegramCommandJobModel

    async with database.session_factory() as session:
        row = await session.execute(
            select(
                TelegramCommandJobModel,
                ConversationModel,
                ParticipantModel,
                AssistantModel,
                ConversationConfigurationRevisionModel,
            )
            .join(
                ConversationModel,
                TelegramCommandJobModel.conversation_id == ConversationModel.id,
            )
            .join(
                ParticipantModel,
                TelegramCommandJobModel.participant_id == ParticipantModel.id,
            )
            .join(
                PlatformConnectionModel,
                ConversationModel.platform_connection_id == PlatformConnectionModel.id,
            )
            .join(
                AssistantModel,
                PlatformConnectionModel.assistant_id == AssistantModel.id,
            )
            .outerjoin(
                ConversationConfigurationRevisionModel,
                ConversationModel.current_configuration_revision_id
                == ConversationConfigurationRevisionModel.id,
            )
            .where(TelegramCommandJobModel.id == job_id)
        )
        value = row.first()
        if value is None:
            return "vi", None, None, None, None
        _, conversation, participant, assistant, revision = value
        version = (
            await session.get(
                PersonalityProfileVersionModel,
                revision.personality_profile_version_id,
            )
            if revision is not None
            else None
        )
    language = (
        "en" if version is not None and version.primary_language == "en" else "vi"
    )
    return (
        language,
        conversation,
        participant,
        assistant,
        revision.revision_number if revision is not None else None,
    )


async def _resolve_profile_version(
    database: Database,
    assistant_id: UUID,
    value: object,
) -> tuple[UUID | None, str]:
    if not isinstance(value, str):
        return None, "profile_not_found"
    slug, separator, raw_version = value.partition("@")
    version_number = int(raw_version) if separator else None
    async with database.session_factory() as session:
        profile = await session.scalar(
            select(PersonalityProfileModel).where(
                PersonalityProfileModel.assistant_id == assistant_id,
                PersonalityProfileModel.slug == slug,
            )
        )
        if profile is None:
            exists_elsewhere = await session.scalar(
                select(PersonalityProfileModel.id).where(
                    PersonalityProfileModel.slug == slug
                )
            )
            return (
                None,
                "profile_not_owned"
                if exists_elsewhere is not None
                else "profile_not_found",
            )
        if profile.conversation_id is not None:
            return None, "profile_not_owned"
        if profile.status != PersonalityProfileStatus.ACTIVE:
            return None, "profile_not_found"
        query = select(PersonalityProfileVersionModel.id).where(
            PersonalityProfileVersionModel.profile_id == profile.id
        )
        if version_number is not None:
            query = query.where(
                PersonalityProfileVersionModel.version_number == version_number
            )
        else:
            query = query.order_by(
                PersonalityProfileVersionModel.version_number.desc()
            ).limit(1)
        result = await session.scalar(query)
        return (
            (result, "success")
            if isinstance(result, UUID)
            else (None, "profile_not_found")
        )


async def _read_detail(
    database: Database,
    conversation: ConversationModel,
    participant: ParticipantModel,
    assistant: AssistantModel,
    request: object,
    profile_limit: int,
) -> str | None:
    from app.application.commands import CommandRequest

    assert isinstance(request, CommandRequest)
    async with database.session_factory() as session:
        current = await session.get(ConversationModel, conversation.id)
        revision = (
            await session.get(
                ConversationConfigurationRevisionModel,
                current.current_configuration_revision_id,
            )
            if current is not None
            and current.current_configuration_revision_id is not None
            else None
        )
        latest_participant = await session.get(ParticipantModel, participant.id)
        version = (
            await session.get(
                PersonalityProfileVersionModel,
                revision.personality_profile_version_id,
            )
            if revision is not None
            else None
        )
        profile = (
            await session.get(PersonalityProfileModel, version.profile_id)
            if version is not None
            else None
        )
        if request.name == "status" and current and revision and latest_participant:
            state = (
                "paused" if revision.response_mode == ResponseMode.PAUSED else "active"
            )
            personality = (
                f"{profile.display_name} v{version.version_number}"
                if profile is not None and version is not None
                else "unavailable"
            )
            return (
                f"state={state}; "
                f"mode={revision.response_mode.value}; "
                f"stickers={'on' if revision.stickers_enabled else 'off'}; "
                f"mentions={'on' if latest_participant.mention_allowed else 'off'}; "
                f"teasing={'on' if latest_participant.teasing_allowed else 'off'}; "
                f"personality={personality}"
            )
        if (
            request.name == "personality"
            and profile is not None
            and version is not None
        ):
            if request.action == "list":
                profiles = list(
                    await session.scalars(
                        select(PersonalityProfileModel)
                        .where(
                            PersonalityProfileModel.assistant_id == assistant.id,
                            PersonalityProfileModel.status
                            == PersonalityProfileStatus.ACTIVE,
                            PersonalityProfileModel.conversation_id.is_(None),
                        )
                        .order_by(PersonalityProfileModel.slug)
                        .limit(profile_limit)
                    )
                )
                return ", ".join(item.slug for item in profiles) or "none"
            return (
                f"{profile.display_name} ({profile.slug}) v{version.version_number}; "
                f"language={version.primary_language}; tone={version.formality}"
            )
        if request.name == "mode" and revision:
            return revision.response_mode.value
        if request.name == "stickers" and revision:
            return "on" if revision.stickers_enabled else "off"
        if request.name == "mentions" and latest_participant:
            return "on" if latest_participant.mention_allowed else "off"
        if request.name == "teasing" and latest_participant:
            return "on" if latest_participant.teasing_allowed else "off"
    return None


def _configuration_change(
    settings: Settings,
    participant: ParticipantModel,
    request: object,
) -> tuple[str, ConfigurationChange | None, bool]:
    from app.application.commands import CommandRequest

    assert isinstance(request, CommandRequest)
    if (
        request.name == "mode"
        and request.value == "ambient_selective"
        and not settings.command_ambient_selective_enabled
    ):
        return "ambient_disabled", None, False
    if (
        request.name == "stickers"
        and request.value is True
        and not settings.telegram_sticker_mapping
    ):
        return "sticker_mapping_unavailable", None, False
    change = ConfigurationChange(
        source="telegram_command", actor_participant_id=participant.id
    )
    if request.name == "mode":
        change = ConfigurationChange(
            response_mode=ResponseMode(str(request.value)),
            source="telegram_command",
            actor_participant_id=participant.id,
        )
    elif request.name == "quiet":
        change = ConfigurationChange(
            response_mode=ResponseMode.PAUSED,
            source="telegram_command",
            actor_participant_id=participant.id,
        )
    elif request.name == "resume":
        change = ConfigurationChange(
            response_mode=ResponseMode.MENTION_ONLY,
            source="telegram_command",
            actor_participant_id=participant.id,
        )
    elif request.name == "stickers":
        change = ConfigurationChange(
            stickers_enabled=bool(request.value),
            source="telegram_command",
            actor_participant_id=participant.id,
        )
    else:
        return "usage", None, False
    return "success", change, request.name == "resume"


async def _finish(
    repository: SqlAlchemyCommandRepository,
    job: object,
    owner: str,
    code: str,
    language: str,
    authorization: CommandAuthorizationOutcome | None = None,
    preference: tuple[bool | None, bool | None] | None = None,
    detail: str | None = None,
) -> None:
    from app.infrastructure.database.models import TelegramCommandJobModel

    assert isinstance(job, TelegramCommandJobModel)
    await repository.complete(
        job.id,
        owner,
        _candidate(job.message_id, code, language, detail),
        code,
        authorization,
        preference,
        _candidate(job.message_id, "unchanged", language)
        if preference is not None
        else None,
    )


def _candidate(
    message_id: UUID, code: str, language: str, detail: str | None = None
) -> ResponsePlanCandidate:
    return ResponsePlanCandidate(
        should_respond=True,
        reason_code=PlanReasonCode.ACKNOWLEDGEMENT,
        text=command_response(code, language=language, detail=detail),
        reply_to_message_id=message_id,
        confidence=1,
        language=language,
    )


def _authorization_retry_delay(settings: Settings, attempt_count: int) -> float:
    """Apply bounded exponential backoff after the durable claim count."""

    return float(
        min(
            settings.command_retry_max_delay_seconds,
            settings.command_retry_min_delay_seconds * (2 ** max(0, attempt_count - 1)),
        )
    )


async def run() -> None:
    settings = get_settings()
    database = Database(settings)
    telemetry = (
        InMemoryMetricsRecorder() if settings.metrics_enabled else NoOpMetricsRecorder()
    )
    await database.start()
    try:
        while True:
            count = await consume_once(settings, database)
            if count:
                telemetry.increment(
                    "january_worker_operations_total",
                    count,
                    runtime="commands",
                    operation="command_job",
                    outcome="completed",
                )
            if count == 0:
                await asyncio.sleep(settings.command_poll_interval_seconds)
    finally:
        await database.stop()


if __name__ == "__main__":
    asyncio.run(run())
