"""Authoritative SQLAlchemy models for the SPEC-002 schema."""

from datetime import datetime
from enum import Enum as PythonEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.conversation import (
    EligibilityReason,
    MembershipStatus,
    ProcessingOutcome,
)
from app.domain.persistence import (
    AssistantStatus,
    ConversationStatus,
    ConversationType,
    IncomingUpdateStatus,
    IngressOutboxStatus,
    IngressSource,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    ParticipantRole,
    Platform,
    PlatformConnectionStatus,
    ResponseMode,
)
from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def string_enum(enum_type: type[PythonEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [str(member.value) for member in values],
        name=name,
    )


class AssistantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assistants"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AssistantStatus] = mapped_column(
        string_enum(AssistantStatus, "assistant_status"),
        default=AssistantStatus.ACTIVE,
        nullable=False,
    )


class PlatformConnectionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_connections"
    __table_args__ = (UniqueConstraint("platform", "external_bot_id"),)

    assistant_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(
        string_enum(Platform, "platform"), nullable=False
    )
    external_bot_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PlatformConnectionStatus] = mapped_column(
        string_enum(PlatformConnectionStatus, "platform_connection_status"),
        default=PlatformConnectionStatus.ACTIVE,
        nullable=False,
    )
    credential_reference: Mapped[str | None] = mapped_column(String(255))
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )


class ConversationModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("platform_connection_id", "platform_conversation_id"),
    )

    platform_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    platform_conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_type: Mapped[ConversationType] = mapped_column(
        string_enum(ConversationType, "conversation_type"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ConversationStatus] = mapped_column(
        string_enum(ConversationStatus, "conversation_status"),
        default=ConversationStatus.ACTIVE,
        nullable=False,
    )
    response_mode: Mapped[ResponseMode] = mapped_column(
        string_enum(ResponseMode, "response_mode"),
        default=ResponseMode.MENTION_ONLY,
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )
    assistant_membership_status: Mapped[MembershipStatus | None] = mapped_column(
        string_enum(MembershipStatus, "assistant_membership_status")
    )
    assistant_membership_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_platform_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class ParticipantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("conversation_id", "platform_user_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[ParticipantRole] = mapped_column(
        string_enum(ParticipantRole, "participant_role"),
        default=ParticipantRole.MEMBER,
        nullable=False,
    )
    mention_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    teasing_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
        nullable=False,
    )
    membership_status: Mapped[MembershipStatus] = mapped_column(
        string_enum(MembershipStatus, "participant_membership_status"),
        default=MembershipStatus.MEMBER,
        nullable=False,
    )
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_membership_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class MessageModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "platform_message_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    participant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    platform_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(
        string_enum(MessageDirection, "message_direction"), nullable=False
    )
    message_type: Mapped[MessageType] = mapped_column(
        string_enum(MessageType, "message_type"), nullable=False
    )
    text: Mapped[str | None] = mapped_column(Text)
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), index=True
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
        nullable=False,
    )
    processing_status: Mapped[MessageProcessingStatus] = mapped_column(
        string_enum(MessageProcessingStatus, "message_processing_status"),
        default=MessageProcessingStatus.PENDING,
        nullable=False,
    )
    platform_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform_thread_id: Mapped[str | None] = mapped_column(String(255))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mentions_assistant: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    replies_to_assistant: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    eligible: Mapped[bool | None] = mapped_column(Boolean)
    eligibility_reason: Mapped[EligibilityReason | None] = mapped_column(
        string_enum(EligibilityReason, "message_eligibility_reason")
    )
    reply_to: Mapped["MessageModel | None"] = relationship(
        remote_side="MessageModel.id", foreign_keys=[reply_to_message_id]
    )


class IncomingPlatformUpdateModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incoming_platform_updates"
    __table_args__ = (
        UniqueConstraint("platform_connection_id", "platform_update_id"),
        Index("ix_incoming_platform_updates_pending", "status", "received_at"),
        Index(
            "ix_incoming_platform_updates_connection_received",
            "platform_connection_id",
            "received_at",
        ),
    )

    platform_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(
        string_enum(Platform, "incoming_platform"), nullable=False
    )
    platform_update_id: Mapped[str] = mapped_column(String(255), nullable=False)
    update_type: Mapped[str] = mapped_column(String(64), nullable=False)
    ingress_source: Mapped[IngressSource] = mapped_column(
        string_enum(IngressSource, "ingress_source"), nullable=False
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[IncomingUpdateStatus] = mapped_column(
        string_enum(IncomingUpdateStatus, "incoming_update_status"),
        default=IncomingUpdateStatus.RECEIVED,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngressOutboxEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingress_outbox_events"
    __table_args__ = (
        UniqueConstraint("incoming_update_id"),
        Index(
            "ix_ingress_outbox_events_pending", "status", "available_at", "created_at"
        ),
    )

    incoming_update_id: Mapped[UUID] = mapped_column(
        ForeignKey("incoming_platform_updates.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(64), default="ingress.received", nullable=False
    )
    schema_version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[IngressOutboxStatus] = mapped_column(
        string_enum(IngressOutboxStatus, "ingress_outbox_status"),
        default=IngressOutboxStatus.PENDING,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[str | None] = mapped_column(String(64))


class PollingCursorModel(Base):
    __tablename__ = "polling_cursors"

    platform_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"), primary_key=True
    )
    next_offset: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConversationProcessingRecordModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_processing_records"
    __table_args__ = (UniqueConstraint("incoming_update_id"),)

    incoming_update_id: Mapped[UUID] = mapped_column(
        ForeignKey("incoming_platform_updates.id", ondelete="RESTRICT"), nullable=False
    )
    outcome: Mapped[ProcessingOutcome] = mapped_column(
        string_enum(ProcessingOutcome, "conversation_processing_outcome"),
        nullable=False,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), index=True
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), index=True
    )
    eligible: Mapped[bool | None] = mapped_column(Boolean)
    eligibility_reason: Mapped[EligibilityReason | None] = mapped_column(
        string_enum(EligibilityReason, "processing_eligibility_reason")
    )
    permanent_error: Mapped[str | None] = mapped_column(String(64))
