"""Migration-level proof for the explicit memory/privacy schema."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text

from app.application.memory import normalize_explicit_memory
from app.core.config import Settings
from app.domain.conversation import EligibilityReason, ProcessingOutcome
from app.domain.outbound import OutboundActionKind, OutboundActionStatus
from app.domain.persistence import (
    CommandJobStatus,
    ConversationType,
    IngressSource,
    MemoryScope,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    Platform,
    PlatformConnectionStatus,
)
from app.domain.planning import PlanReasonCode
from app.infrastructure.database.database import Database
from app.infrastructure.database.memory import SqlAlchemyMemoryRepository
from app.infrastructure.database.models import (
    AssistantModel,
    ConversationModel,
    ConversationProcessingRecordModel,
    IncomingPlatformUpdateModel,
    MemoryEventModel,
    MemoryItemModel,
    MessageModel,
    OutboundActionModel,
    ParticipantModel,
    PlatformConnectionModel,
    ResponsePlanModel,
    TelegramCommandJobModel,
)
from app.infrastructure.database.privacy import SqlAlchemyPrivacyRepository
from app.infrastructure.database.retention import SqlAlchemyRetentionRepository
from app.runtime.demo_inspector import inspect_latest


@pytest.mark.integration
@pytest.mark.memory_integration
def test_memory_privacy_retention_schema_is_current() -> None:
    async def scenario() -> None:
        database = Database(Settings(_env_file=None, environment="test"))
        await database.start()
        try:
            async with database.engine.connect() as connection:
                assert await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                ) == ("0009_safety_rate_limiting")
                columns = set(
                    await connection.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'memory_items'"
                        )
                    )
                )
                assert {
                    "public_id",
                    "assistant_id",
                    "platform_connection_id",
                    "conversation_id",
                    "creator_participant_id",
                    "content",
                    "normalized_content_hash",
                    "deletion_reason",
                } <= columns
        finally:
            await database.stop()

    asyncio.run(scenario())


async def _seed_command(
    database: Database,
    *,
    assistant_id: UUID,
    connection_id: UUID,
    suffix: str,
    user_id: str = "user-1",
) -> tuple[ConversationModel, ParticipantModel, MessageModel, TelegramCommandJobModel]:
    async with database.session_factory() as session:
        async with session.begin():
            conversation = ConversationModel(
                platform_connection_id=connection_id,
                platform_conversation_id=f"chat-{suffix}",
                conversation_type=ConversationType.GROUP,
            )
            session.add(conversation)
            await session.flush()
            participant = ParticipantModel(
                conversation_id=conversation.id,
                platform_user_id=user_id,
                username="private-username",
                display_name="Private Name",
                metadata_={"private": "metadata"},
            )
            session.add(participant)
            await session.flush()
            message = MessageModel(
                conversation_id=conversation.id,
                participant_id=participant.id,
                platform_message_id=f"message-{suffix}",
                direction=MessageDirection.INCOMING,
                message_type=MessageType.TEXT,
                text="/memory remember secret fact",
                metadata_={"private": "message-metadata"},
                processing_status=MessageProcessingStatus.PROCESSED,
                platform_sent_at=datetime.now(UTC),
            )
            incoming = IncomingPlatformUpdateModel(
                platform_connection_id=connection_id,
                platform=Platform.TELEGRAM,
                platform_update_id=f"update-{suffix}",
                update_type="message",
                ingress_source=IngressSource.POLLING,
                raw_payload={"private": "payload"},
                received_at=datetime.now(UTC),
            )
            session.add_all([message, incoming])
            await session.flush()
            record = ConversationProcessingRecordModel(
                incoming_update_id=incoming.id,
                outcome=ProcessingOutcome.MESSAGE_CREATED,
                conversation_id=conversation.id,
                message_id=message.id,
                eligible=False,
                eligibility_reason=EligibilityReason.COMMAND_HANDOFF,
            )
            session.add(record)
            await session.flush()
            job = TelegramCommandJobModel(
                conversation_processing_record_id=record.id,
                conversation_id=conversation.id,
                message_id=message.id,
                participant_id=participant.id,
                command_name="memory",
                arguments="remember secret fact",
            )
            session.add(job)
            await session.flush()
            return conversation, participant, message, job


@pytest.mark.integration
@pytest.mark.memory_integration
def test_memory_scope_profile_erasure_and_inspector_are_content_safe() -> None:
    async def scenario() -> None:
        settings = Settings(_env_file=None, environment="test")
        database = Database(settings)
        await database.start()
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    await session.execute(text("TRUNCATE assistants CASCADE"))
                    assistant = AssistantModel(name="January")
                    other_assistant = AssistantModel(name="Other")
                    session.add_all([assistant, other_assistant])
                    await session.flush()
                    connection = PlatformConnectionModel(
                        assistant_id=assistant.id,
                        platform=Platform.TELEGRAM,
                        external_bot_id="memory-primary",
                        status=PlatformConnectionStatus.ACTIVE,
                    )
                    other_connection = PlatformConnectionModel(
                        assistant_id=other_assistant.id,
                        platform=Platform.TELEGRAM,
                        external_bot_id="memory-other",
                        status=PlatformConnectionStatus.ACTIVE,
                    )
                    session.add_all([connection, other_connection])
                    await session.flush()
                    (
                        assistant_id,
                        connection_id,
                        other_assistant_id,
                        other_connection_id,
                    ) = (
                        assistant.id,
                        connection.id,
                        other_assistant.id,
                        other_connection.id,
                    )

            primary = await _seed_command(
                database,
                assistant_id=assistant_id,
                connection_id=connection_id,
                suffix="primary",
            )
            sibling = await _seed_command(
                database,
                assistant_id=assistant_id,
                connection_id=connection_id,
                suffix="sibling",
            )
            other = await _seed_command(
                database,
                assistant_id=other_assistant_id,
                connection_id=other_connection_id,
                suffix="other",
            )
            repository = SqlAlchemyMemoryRepository(database.session_factory)
            primary_memory = await repository.create(
                assistant_id=assistant_id,
                platform_connection_id=connection_id,
                conversation_id=primary[0].id,
                creator_participant_id=primary[1].id,
                source_message_id=primary[2].id,
                source_command_job_id=primary[3].id,
                draft=normalize_explicit_memory(
                    "secret memory primary", MemoryScope.GROUP_CONVERSATION
                ),
            )
            sibling_memory = await repository.create(
                assistant_id=assistant_id,
                platform_connection_id=connection_id,
                conversation_id=sibling[0].id,
                creator_participant_id=sibling[1].id,
                source_message_id=sibling[2].id,
                source_command_job_id=sibling[3].id,
                draft=normalize_explicit_memory(
                    "secret memory sibling", MemoryScope.GROUP_CONVERSATION
                ),
            )
            other_memory = await repository.create(
                assistant_id=other_assistant_id,
                platform_connection_id=other_connection_id,
                conversation_id=other[0].id,
                creator_participant_id=other[1].id,
                source_message_id=other[2].id,
                source_command_job_id=other[3].id,
                draft=normalize_explicit_memory(
                    "secret memory other", MemoryScope.GROUP_CONVERSATION
                ),
            )
            listed = await repository.active_for_conversation(
                assistant_id=assistant_id,
                platform_connection_id=connection_id,
                conversation_id=primary[0].id,
            )
            assert [entry.item.id for entry in listed] == [primary_memory.id]

            erased = await SqlAlchemyPrivacyRepository(
                database.session_factory
            ).erase_subject(
                assistant_id=assistant_id,
                platform_connection_id=connection_id,
                platform_user_id="user-1",
                command_job_id=primary[3].id,
            )
            assert erased.memories == 2
            assert erased.participants == 2
            assert erased.messages == 2
            assert erased.incoming_updates == 2
            assert erased.command_arguments == 2
            assert not erased.already_deleted
            async with database.session_factory() as session:
                primary_after = await session.get(MemoryItemModel, primary_memory.id)
                sibling_after = await session.get(MemoryItemModel, sibling_memory.id)
                other_after = await session.get(MemoryItemModel, other_memory.id)
                primary_participant = await session.get(ParticipantModel, primary[1].id)
                primary_message = await session.get(MessageModel, primary[2].id)
                primary_job = await session.get(TelegramCommandJobModel, primary[3].id)
                primary_update = await session.scalar(
                    select(IncomingPlatformUpdateModel).where(
                        IncomingPlatformUpdateModel.platform_update_id
                        == "update-primary"
                    )
                )
                event_codes = list(
                    await session.scalars(select(MemoryEventModel.action_code))
                )
                assert primary_after is not None
                assert primary_after.content is None
                assert primary_after.normalized_content_hash is None
                assert sibling_after is not None
                assert sibling_after.content is None
                assert other_after is not None
                assert other_after.content == "secret memory other"
                assert primary_participant is not None
                assert primary_participant.display_name == "Deleted user"
                assert primary_message is not None and primary_message.text is None
                assert primary_job is not None and primary_job.arguments == ""
                assert primary_update is not None and primary_update.raw_payload == {}
                assert "profile_deleted" in event_codes
            other_list = await repository.active_for_conversation(
                assistant_id=other_assistant_id,
                platform_connection_id=other_connection_id,
                conversation_id=other[0].id,
            )
            assert [entry.item.content for entry in other_list] == [
                "secret memory other"
            ]
            report = await inspect_latest(settings, conversation_id=primary[0].id)
            report_json = json.dumps(report)
            assert "secret memory primary" not in report_json
            assert "private-username" not in report_json
        finally:
            await database.stop()

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.memory_integration
def test_retention_redacts_terminal_content_at_the_exact_cutoff_idempotently() -> None:
    async def scenario() -> None:
        database = Database(Settings(_env_file=None, environment="test"))
        await database.start()
        try:
            async with database.session_factory() as session:
                async with session.begin():
                    await session.execute(text("TRUNCATE assistants CASCADE"))
                    assistant = AssistantModel(name="January")
                    session.add(assistant)
                    await session.flush()
                    connection = PlatformConnectionModel(
                        assistant_id=assistant.id,
                        platform=Platform.TELEGRAM,
                        external_bot_id="retention-bot",
                        status=PlatformConnectionStatus.ACTIVE,
                    )
                    session.add(connection)
                    await session.flush()
                    assistant_id, connection_id = assistant.id, connection.id
            conversation, participant, message, job = await _seed_command(
                database,
                assistant_id=assistant_id,
                connection_id=connection_id,
                suffix="retention",
            )
            now = datetime(2026, 8, 1, tzinfo=UTC)
            cutoff = now - timedelta(days=30)
            async with database.session_factory() as session:
                async with session.begin():
                    job = await session.get(TelegramCommandJobModel, job.id)
                    assert job is not None
                    job.status = CommandJobStatus.COMPLETED
                    job.completed_at = cutoff
                    plan = ResponsePlanModel(
                        command_job_id=job.id,
                        should_respond=True,
                        reason_code=PlanReasonCode.ACKNOWLEDGEMENT,
                        text="secret response plan",
                        reply_to_message_id=message.id,
                        mention_participant_ids=[],
                        confidence=1.0,
                        language="en",
                        prompt_version="test",
                        schema_version="test",
                        created_at=cutoff,
                    )
                    session.add(plan)
                    await session.flush()
                    action = OutboundActionModel(
                        response_plan_id=plan.id,
                        conversation_id=conversation.id,
                        sequence_number=0,
                        idempotency_key="retention-action",
                        kind=OutboundActionKind.TEXT,
                        status=OutboundActionStatus.DELIVERED,
                        text="secret outbound action",
                        mention_participant_ids=[],
                        created_at=cutoff,
                    )
                    session.add(action)
                    persisted_message = await session.get(MessageModel, message.id)
                    assert persisted_message is not None
                    persisted_message.platform_sent_at = cutoff
                    persisted_message.text = "secret source message"
                    incoming = await session.scalar(
                        select(IncomingPlatformUpdateModel).where(
                            IncomingPlatformUpdateModel.platform_update_id
                            == "update-retention"
                        )
                    )
                    assert incoming is not None
                    incoming.received_at = cutoff
            counts = await SqlAlchemyRetentionRepository(
                database.session_factory
            ).redact_once(now=now, retention_days=30, batch_size=10)
            assert counts.incoming_updates == 1
            assert counts.messages == 1
            assert counts.response_plans == 1
            assert counts.outbound_actions == 1
            assert counts.command_arguments == 1
            assert (
                await SqlAlchemyRetentionRepository(
                    database.session_factory
                ).redact_once(now=now, retention_days=30, batch_size=10)
                == type(counts)()
            )
            async with database.session_factory() as session:
                message_after = await session.get(MessageModel, message.id)
                job_after = await session.get(TelegramCommandJobModel, job.id)
                plan_after = await session.scalar(
                    select(ResponsePlanModel).where(
                        ResponsePlanModel.command_job_id == job.id
                    )
                )
                action_after = await session.scalar(
                    select(OutboundActionModel).where(
                        OutboundActionModel.idempotency_key == "retention-action"
                    )
                )
                assert message_after is not None and message_after.text is None
                assert job_after is not None and job_after.arguments == ""
                assert plan_after is not None and plan_after.text is None
                assert action_after is not None and action_after.text is None
        finally:
            await database.stop()

    asyncio.run(scenario())
