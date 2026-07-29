"""Authoritative SQLAlchemy models for the SPEC-002 schema."""

from enum import Enum as PythonEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.persistence import (
    AssistantStatus,
    ConversationStatus,
    ConversationType,
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
    reply_to: Mapped["MessageModel | None"] = relationship(
        remote_side="MessageModel.id", foreign_keys=[reply_to_message_id]
    )
