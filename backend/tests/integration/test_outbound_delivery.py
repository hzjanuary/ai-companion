import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.application.ports.platform import PlatformCapability, SentMessage
from app.core.config import Settings
from app.domain.conversation import ProcessingOutcome
from app.domain.outbound import OutboundActionKind, OutboundActionStatus
from app.domain.persistence import (
    ConversationStatus,
    ConversationType,
    IngressSource,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    Platform,
    PlatformConnectionStatus,
    ResponseMode,
)
from app.domain.planning import PlanReasonCode
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import (
    AssistantModel,
    ConversationModel,
    ConversationProcessingRecordModel,
    IncomingPlatformUpdateModel,
    MessageModel,
    OutboundActionModel,
    OutboundDeliveryAttemptModel,
    ParticipantModel,
    PlatformConnectionModel,
    ResponsePlanModel,
    ResponsePlanningJobModel,
)
from app.infrastructure.database.outbound import SqlAlchemyOutboundRepository
from app.runtime.outbound_delivery_worker import consume_once


@pytest.mark.integration
@pytest.mark.delivery_integration
@pytest.mark.demo_integration
def test_confirmed_delivery_persists_one_outgoing_message_and_is_idempotent() -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.requests: list[object] = []

        @property
        def capabilities(self) -> frozenset[PlatformCapability]:
            return frozenset({PlatformCapability.SEND_TEXT})

        async def send_text(self, request: object) -> SentMessage:
            self.requests.append(request)
            return SentMessage(
                Platform.TELEGRAM,
                "900",
                "chat-1",
                "bot-1",
                "thread-1",
                datetime.now(UTC),
            )

        async def send_sticker(self, request: object) -> SentMessage:
            raise AssertionError("sticker was not expected")

        async def aclose(self) -> None:
            return None

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            environment="test",
            telegram_enabled=True,
            telegram_bot_token="fake-token",
            telegram_platform_connection_id=uuid4(),
            telegram_delivery_mode="polling",
            outbound_delivery_enabled=True,
            llm_enabled=True,
            llm_primary_provider="ollama",
            llm_ollama_model="synthetic",
            demo_live_enabled=True,
            demo_allowed_chat_ids=("4000000001",),
        )
        database = Database(settings)
        await database.start()
        async with database.engine.begin() as connection:
            await connection.execute(text("TRUNCATE assistants CASCADE"))
        async with database.session_factory() as session:
            async with session.begin():
                assistant = AssistantModel(name="test")
                session.add(assistant)
                await session.flush()
                connection = PlatformConnectionModel(
                    assistant_id=assistant.id,
                    platform=Platform.TELEGRAM,
                    external_bot_id="bot-1",
                    status=PlatformConnectionStatus.ACTIVE,
                )
                session.add(connection)
                await session.flush()
                conversation = ConversationModel(
                    platform_connection_id=connection.id,
                    platform_conversation_id="4000000001",
                    conversation_type=ConversationType.GROUP,
                    status=ConversationStatus.ACTIVE,
                    response_mode=ResponseMode.AMBIENT_SELECTIVE,
                )
                session.add(conversation)
                await session.flush()
                participant = ParticipantModel(
                    conversation_id=conversation.id,
                    platform_user_id="user-1",
                    username="lan",
                    display_name="Lan",
                )
                incoming = MessageModel(
                    conversation_id=conversation.id,
                    participant_id=participant.id,
                    platform_message_id="42",
                    direction=MessageDirection.INCOMING,
                    message_type=MessageType.TEXT,
                    text="hello",
                    processing_status=MessageProcessingStatus.PROCESSED,
                    platform_thread_id="thread-1",
                )
                session.add_all([participant, incoming])
                await session.flush()
                update = IncomingPlatformUpdateModel(
                    platform_connection_id=connection.id,
                    platform=Platform.TELEGRAM,
                    platform_update_id="update-1",
                    update_type="message",
                    ingress_source=IngressSource.WEBHOOK,
                    raw_payload={},
                    received_at=datetime.now(UTC),
                )
                session.add(update)
                await session.flush()
                record = ConversationProcessingRecordModel(
                    incoming_update_id=update.id,
                    outcome=ProcessingOutcome.MESSAGE_CREATED,
                    conversation_id=conversation.id,
                    message_id=incoming.id,
                )
                session.add(record)
                await session.flush()
                job = ResponsePlanningJobModel(
                    conversation_processing_record_id=record.id,
                    conversation_id=conversation.id,
                    message_id=incoming.id,
                    prompt_version="test",
                    response_schema_version="test",
                )
                session.add(job)
                await session.flush()
                plan = ResponsePlanModel(
                    planning_job_id=job.id,
                    should_respond=True,
                    reason_code=PlanReasonCode.ANSWER,
                    text="xin chao",
                    reply_to_message_id=incoming.id,
                    mention_participant_ids=[str(participant.id)],
                    confidence=1,
                    prompt_version="test",
                    schema_version="test",
                )
                session.add(plan)
                await session.flush()
                action = OutboundActionModel(
                    response_plan_id=plan.id,
                    conversation_id=conversation.id,
                    sequence_number=1,
                    idempotency_key="a" * 64,
                    kind=OutboundActionKind.TEXT,
                    reply_to_message_id=incoming.id,
                    message_thread_id="thread-1",
                    text="xin chao",
                    mention_participant_ids=[str(participant.id)],
                )
                session.add(action)
        fake = FakeAdapter()
        assert await consume_once(settings, database, fake) == 1  # type: ignore[arg-type]
        assert await consume_once(settings, database, fake) == 0  # type: ignore[arg-type]
        assert len(fake.requests) == 1
        request = fake.requests[0]
        assert request.conversation_id == "4000000001"  # type: ignore[attr-defined]
        assert request.reply_to_message_id == "42"  # type: ignore[attr-defined]
        assert request.message_thread_id == "thread-1"  # type: ignore[attr-defined]
        async with database.session_factory() as session:
            action = await session.scalar(select(OutboundActionModel))
            assert (
                action is not None and action.status == OutboundActionStatus.DELIVERED
            )
            assert await session.scalar(select(func.count(MessageModel.id))) == 2
            assert (
                await session.scalar(
                    select(func.count(OutboundDeliveryAttemptModel.id))
                )
                == 1
            )
            assert action.response_plan_id is not None
            retry = OutboundActionModel(
                response_plan_id=action.response_plan_id,
                conversation_id=action.conversation_id,
                sequence_number=2,
                idempotency_key="b" * 64,
                kind=OutboundActionKind.TEXT,
                text="retry",
                mention_participant_ids=[],
            )
            session.add(retry)
            await session.commit()
            retry_id = retry.id
        repository = SqlAlchemyOutboundRepository(database.session_factory)
        assert [item.id for item in await repository.claim("first", 1, 60)] == [
            retry_id
        ]
        async with database.session_factory() as session:
            async with session.begin():
                lease = await session.get(OutboundActionModel, retry_id)
                assert lease is not None
                lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert await repository.claim("reclaimer", 1, 60) == []
        assert [item.id for item in await repository.claim("reclaimer", 1, 60)] == [
            retry_id
        ]
        assert await repository.mark_external_started(retry_id, "reclaimer")
        async with database.session_factory() as session:
            async with session.begin():
                lease = await session.get(OutboundActionModel, retry_id)
                assert lease is not None
                lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert await repository.claim("later", 1, 60) == []
        async with database.session_factory() as session:
            lease = await session.get(OutboundActionModel, retry_id)
            assert lease is not None
            assert lease.status == OutboundActionStatus.DELIVERY_UNKNOWN
            skipped = OutboundActionModel(
                response_plan_id=action.response_plan_id,
                conversation_id=action.conversation_id,
                sequence_number=3,
                idempotency_key="c" * 64,
                kind=OutboundActionKind.TEXT,
                text="must not send",
                mention_participant_ids=[],
            )
            session.add(skipped)
            await session.commit()
            skipped_id = skipped.id
        denied_settings = settings.model_copy(
            update={"demo_allowed_chat_ids": ("4000000002",)}
        )
        assert await consume_once(denied_settings, database, fake) == 1  # type: ignore[arg-type]
        assert len(fake.requests) == 1
        async with database.session_factory() as session:
            skipped = await session.get(OutboundActionModel, skipped_id)
            assert skipped is not None
            assert skipped.status == OutboundActionStatus.SKIPPED
            assert skipped.last_error_category == "conversation_not_allowed"
        await database.stop()

    asyncio.run(scenario())
