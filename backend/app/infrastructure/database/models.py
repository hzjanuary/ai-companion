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

from app.domain.ambient import AmbientFrequency, ParticipationTrigger
from app.domain.conversation import (
    EligibilityReason,
    MembershipStatus,
    ProcessingOutcome,
)
from app.domain.outbound import (
    DeliveryAttemptStatus,
    DeliveryCertainty,
    OutboundActionKind,
    OutboundActionStatus,
)
from app.domain.persistence import (
    AssistantStatus,
    CommandAuthorizationOutcome,
    CommandJobStatus,
    ConversationStatus,
    ConversationType,
    IncomingUpdateStatus,
    IngressOutboxStatus,
    IngressSource,
    MemoryDeletionReason,
    MemoryKind,
    MemoryScope,
    MemoryStatus,
    MemoryVisibility,
    MessageDirection,
    MessageProcessingStatus,
    MessageType,
    ParticipantRole,
    PersonalityProfileStatus,
    Platform,
    PlatformConnectionStatus,
    ResponseMode,
    SemanticMemoryIndexJobStatus,
    SemanticMemoryIndexOperation,
)
from app.domain.planning import (
    GenerationAttemptKind,
    GenerationAttemptStatus,
    PlanningJobStatus,
    PlanReasonCode,
    ProviderErrorCategory,
    ProviderId,
    StickerIntent,
)
from app.domain.rate_limit import RateLimitOperation, RateLimitScope
from app.domain.recovery import RecoveryDisposition, RecoveryKind, RecoveryReason
from app.domain.safety import (
    InteractionKind,
    ProtectionAction,
    ReviewAction,
    ReviewItemStatus,
    SafetyLevel,
    SafetyOutcome,
    SafetyPolicyVersion,
    SafetyReasonCode,
    SafetySignalType,
    SafetyStage,
)
from app.domain.summary import ConversationSummaryStatus
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
    default_personality_profile_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personality_profile_versions.id", ondelete="RESTRICT"), index=True
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


class PersonalityProfileModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "personality_profiles"
    __table_args__ = (UniqueConstraint("assistant_id", "slug"),)

    assistant_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[PersonalityProfileStatus] = mapped_column(
        string_enum(PersonalityProfileStatus, "personality_profile_status"),
        default=PersonalityProfileStatus.ACTIVE,
        nullable=False,
    )


class PersonalityProfileVersionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "personality_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version_number"),)

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("personality_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_actor: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_language: Mapped[str] = mapped_column(String(16), nullable=False)
    self_reference: Mapped[str] = mapped_column(String(32), nullable=False)
    default_length: Mapped[str] = mapped_column(String(16), nullable=False)
    formality: Mapped[str] = mapped_column(String(16), nullable=False)
    humor_level: Mapped[float] = mapped_column(nullable=False)
    teasing_level: Mapped[float] = mapped_column(nullable=False)
    emoji_frequency: Mapped[float] = mapped_column(nullable=False)
    sticker_frequency: Mapped[float] = mapped_column(nullable=False)
    use_member_names: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_inside_jokes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ask_follow_up_questions: Mapped[str] = mapped_column(String(16), nullable=False)
    allow_sensitive_teasing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stop_teasing_on_request: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reveal_private_memory_in_groups: Mapped[bool] = mapped_column(
        Boolean, nullable=False
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
    current_configuration_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation_configuration_revisions.id", ondelete="RESTRICT"),
        index=True,
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
    memory_privacy_revision: Mapped[int] = mapped_column(default=0, nullable=False)


class ConversationConfigurationRevisionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_configuration_revisions"
    __table_args__ = (UniqueConstraint("conversation_id", "revision_number"),)

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(nullable=False)
    personality_profile_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("personality_profile_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    response_mode: Mapped[ResponseMode] = mapped_column(
        string_enum(ResponseMode, "configuration_response_mode"), nullable=False
    )
    stickers_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ambient_frequency: Mapped[AmbientFrequency] = mapped_column(
        string_enum(AmbientFrequency, "ambient_frequency"),
        default=AmbientFrequency.NORMAL,
        nullable=False,
    )
    safety_level: Mapped[SafetyLevel] = mapped_column(
        string_enum(SafetyLevel, "configuration_safety_level"),
        default=SafetyLevel.STANDARD,
        nullable=False,
    )
    teasing_cap: Mapped[int] = mapped_column(default=3, nullable=False)
    default_length: Mapped[str | None] = mapped_column(String(16))
    formality: Mapped[str | None] = mapped_column(String(16))
    humor_level: Mapped[float | None] = mapped_column()
    teasing_level: Mapped[float | None] = mapped_column()
    emoji_frequency: Mapped[float | None] = mapped_column()
    sticker_frequency: Mapped[float | None] = mapped_column()
    use_member_names: Mapped[bool | None] = mapped_column(Boolean)
    ask_follow_up_questions: Mapped[str | None] = mapped_column(String(16))
    change_source: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_participant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(64))


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
    protected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    outbound_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("outbound_actions.id", ondelete="RESTRICT"), unique=True, index=True
    )
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
    content_redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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


class ConversationSummaryModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = (
        UniqueConstraint("conversation_id", "source_window_hash", "schema_version"),
        Index(
            "ix_conversation_summaries_active",
            "conversation_id",
            "platform_thread_id",
            "status",
            "expires_at",
        ),
        Index("ix_conversation_summaries_expiry", "status", "expires_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform_thread_id: Mapped[str | None] = mapped_column(String(255))
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[ProviderId | None] = mapped_column(
        string_enum(ProviderId, "conversation_summary_provider")
    )
    model: Mapped[str | None] = mapped_column(String(255))
    source_first_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    source_last_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    source_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_count: Mapped[int] = mapped_column(nullable=False)
    source_window_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ConversationSummaryStatus] = mapped_column(
        string_enum(ConversationSummaryStatus, "conversation_summary_status"),
        default=ConversationSummaryStatus.COMPLETED,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(64))


class ConversationSummaryJobModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_summary_jobs"
    __table_args__ = (
        UniqueConstraint("conversation_id", "source_window_hash", "schema_version"),
        Index(
            "ix_conversation_summary_jobs_claim", "status", "available_at", "created_at"
        ),
        Index("ix_conversation_summary_jobs_lease", "status", "lease_expires_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform_thread_id: Mapped[str | None] = mapped_column(String(255))
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_first_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    source_last_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    source_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_count: Mapped[int] = mapped_column(nullable=False)
    source_window_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[ConversationSummaryStatus] = mapped_column(
        string_enum(ConversationSummaryStatus, "conversation_summary_job_status"),
        default=ConversationSummaryStatus.PENDING,
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[ProviderErrorCategory | None] = mapped_column(
        string_enum(ProviderErrorCategory, "conversation_summary_error_category")
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
    payload_redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


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


class ResponsePlanningJobModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "response_planning_jobs"
    __table_args__ = (
        UniqueConstraint("conversation_processing_record_id"),
        Index(
            "ix_response_planning_jobs_claim", "status", "available_at", "created_at"
        ),
        Index("ix_response_planning_jobs_lease", "status", "lease_expires_at"),
    )

    conversation_processing_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_processing_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    personality_profile_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("personality_profile_versions.id", ondelete="RESTRICT"), index=True
    )
    configuration_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation_configuration_revisions.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[PlanningJobStatus] = mapped_column(
        string_enum(PlanningJobStatus, "response_planning_job_status"),
        default=PlanningJobStatus.PENDING,
        nullable=False,
    )
    trigger: Mapped[ParticipationTrigger] = mapped_column(
        string_enum(ParticipationTrigger, "planning_participation_trigger"),
        default=ParticipationTrigger.ADDRESSED,
        nullable=False,
    )
    ambient_policy_version: Mapped[str | None] = mapped_column(String(64))
    ambient_reason: Mapped[str | None] = mapped_column(String(64))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_provider: Mapped[ProviderId | None] = mapped_column(
        string_enum(ProviderId, "response_planning_provider")
    )
    selected_model: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[ProviderErrorCategory | None] = mapped_column(
        string_enum(ProviderErrorCategory, "response_planning_error_category")
    )
    safety_policy_version: Mapped[SafetyPolicyVersion] = mapped_column(
        string_enum(SafetyPolicyVersion, "response_planning_safety_policy_version"),
        default=SafetyPolicyVersion.V1,
        nullable=False,
    )


class TelegramCommandJobModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_command_jobs"
    __table_args__ = (
        UniqueConstraint("conversation_processing_record_id"),
        Index("ix_telegram_command_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_telegram_command_jobs_lease", "status", "lease_expires_at"),
    )

    conversation_processing_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_processing_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    participant_id: Mapped[UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    command_name: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[CommandJobStatus] = mapped_column(
        string_enum(CommandJobStatus, "telegram_command_job_status"),
        default=CommandJobStatus.PENDING,
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_outcome: Mapped[CommandAuthorizationOutcome | None] = mapped_column(
        string_enum(CommandAuthorizationOutcome, "command_authorization_outcome")
    )
    result_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arguments_redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class MemoryItemModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint("public_id"),
        UniqueConstraint("source_command_job_id"),
        Index("ix_memory_items_active_conversation", "conversation_id", "status"),
    )

    public_id: Mapped[str] = mapped_column(String(24), nullable=False)
    assistant_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    platform_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    creator_participant_id: Mapped[UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[MemoryKind] = mapped_column(
        string_enum(MemoryKind, "memory_kind"), nullable=False
    )
    scope: Mapped[MemoryScope] = mapped_column(
        string_enum(MemoryScope, "memory_scope"), nullable=False
    )
    visibility: Mapped[MemoryVisibility] = mapped_column(
        string_enum(MemoryVisibility, "memory_visibility"), nullable=False
    )
    status: Mapped[MemoryStatus] = mapped_column(
        string_enum(MemoryStatus, "memory_status"),
        default=MemoryStatus.ACTIVE,
        nullable=False,
    )
    content: Mapped[str | None] = mapped_column(Text)
    normalized_content_hash: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(nullable=False)
    source_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    source_command_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("telegram_command_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_reason: Mapped[MemoryDeletionReason | None] = mapped_column(
        string_enum(MemoryDeletionReason, "memory_deletion_reason")
    )


class MemoryEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Content-free audit trail for memory mutations."""

    __tablename__ = "memory_events"

    memory_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("memory_items.id", ondelete="RESTRICT"), index=True
    )
    command_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("telegram_command_jobs.id", ondelete="RESTRICT"), index=True
    )
    actor_participant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    deletion_reason: Mapped[str | None] = mapped_column(String(32))
    affected_count: Mapped[int | None] = mapped_column()


class ExplicitMemorySemanticIndexJobModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable derived-index work; canonical memory text never enters this row."""

    __tablename__ = "explicit_memory_semantic_index_jobs"
    __table_args__ = (
        UniqueConstraint("memory_id", "operation", "embedding_version"),
        Index("ix_semantic_memory_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_semantic_memory_jobs_lease", "status", "lease_expires_at"),
    )

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    operation: Mapped[SemanticMemoryIndexOperation] = mapped_column(
        string_enum(SemanticMemoryIndexOperation, "semantic_memory_index_operation"),
        nullable=False,
    )
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_collection: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[SemanticMemoryIndexJobStatus] = mapped_column(
        string_enum(SemanticMemoryIndexJobStatus, "semantic_memory_index_job_status"),
        default=SemanticMemoryIndexJobStatus.PENDING,
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExplicitMemorySemanticIndexCollectionModel(
    UUIDPrimaryKeyMixin, TimestampMixin, Base
):
    """Active physical Qdrant collection for one compatible embedding version."""

    __tablename__ = "explicit_memory_semantic_index_collections"
    __table_args__ = (UniqueConstraint("embedding_version"),)

    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False)


class ParticipantPreferenceEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participant_preference_events"
    __table_args__ = (UniqueConstraint("command_job_id"),)

    participant_id: Mapped[UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    command_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("telegram_command_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    previous_mention_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mention_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    previous_teasing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    teasing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)


class ModelGenerationAttemptModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_generation_attempts"
    __table_args__ = (UniqueConstraint("planning_job_id", "attempt_number"),)

    planning_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("response_planning_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    provider: Mapped[ProviderId] = mapped_column(
        string_enum(ProviderId, "generation_attempt_provider"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_kind: Mapped[GenerationAttemptKind] = mapped_column(
        string_enum(GenerationAttemptKind, "generation_attempt_kind"), nullable=False
    )
    status: Mapped[GenerationAttemptStatus] = mapped_column(
        string_enum(GenerationAttemptStatus, "generation_attempt_status"),
        nullable=False,
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()
    total_tokens: Mapped[int | None] = mapped_column()
    latency_milliseconds: Mapped[int | None] = mapped_column()
    error_category: Mapped[ProviderErrorCategory | None] = mapped_column(
        string_enum(ProviderErrorCategory, "generation_attempt_error_category")
    )
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    diagnostic_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )


class ResponsePlanModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "response_plans"
    __table_args__ = (
        UniqueConstraint("planning_job_id"),
        UniqueConstraint("command_job_id"),
    )

    planning_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("response_planning_jobs.id", ondelete="RESTRICT")
    )
    command_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("telegram_command_jobs.id", ondelete="RESTRICT")
    )
    should_respond: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[PlanReasonCode] = mapped_column(
        string_enum(PlanReasonCode, "response_plan_reason_code"), nullable=False
    )
    text: Mapped[str | None] = mapped_column(Text)
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), index=True
    )
    mention_participant_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sticker_intent: Mapped[StickerIntent | None] = mapped_column(
        string_enum(StickerIntent, "response_plan_sticker_intent")
    )
    confidence: Mapped[float] = mapped_column(nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    interaction_kind: Mapped[InteractionKind] = mapped_column(
        string_enum(InteractionKind, "response_plan_interaction_kind"),
        default=InteractionKind.NEUTRAL,
        nullable=False,
    )
    teasing_target_participant_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb"), nullable=False
    )


class SafetyPolicyDecisionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Content-free record of a deterministic safety gate outcome."""

    __tablename__ = "safety_policy_decisions"

    planning_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("response_planning_jobs.id", ondelete="RESTRICT"), index=True
    )
    response_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("response_plans.id", ondelete="RESTRICT"), index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    policy_version: Mapped[SafetyPolicyVersion] = mapped_column(
        string_enum(SafetyPolicyVersion, "safety_decision_policy_version"),
        nullable=False,
    )
    stage: Mapped[SafetyStage] = mapped_column(
        string_enum(SafetyStage, "safety_decision_stage"), nullable=False
    )
    outcome: Mapped[SafetyOutcome] = mapped_column(
        string_enum(SafetyOutcome, "safety_decision_outcome"), nullable=False
    )
    reason_code: Mapped[SafetyReasonCode | None] = mapped_column(
        string_enum(SafetyReasonCode, "safety_decision_reason_code")
    )
    transformed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RateLimitEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Content-free result of a distributed generation or delivery check."""

    __tablename__ = "rate_limit_events"

    planning_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("response_planning_jobs.id", ondelete="RESTRICT"), index=True
    )
    outbound_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("outbound_actions.id", ondelete="RESTRICT"), index=True
    )
    operation: Mapped[RateLimitOperation] = mapped_column(
        string_enum(RateLimitOperation, "rate_limit_operation"), nullable=False
    )
    limiting_scope: Mapped[RateLimitScope | None] = mapped_column(
        string_enum(RateLimitScope, "rate_limit_scope")
    )
    provider_id: Mapped[str | None] = mapped_column(String(32))
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retry_after_seconds: Mapped[int | None] = mapped_column()
    configuration_version: Mapped[str] = mapped_column(String(64), nullable=False)


class SafetyReviewItemModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bounded, content-free SPEC-024 moderation review queue item.

    Carries categories, stage, outcome counts, opaque references, protection
    state, and status only. Never message text, prompts, memories, usernames,
    or raw platform identifiers (NFR-01/FR-12).
    """

    __tablename__ = "safety_review_items"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    participant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    category: Mapped[SafetySignalType] = mapped_column(
        string_enum(SafetySignalType, "safety_signal_type"), nullable=False
    )
    stage: Mapped[SafetyStage] = mapped_column(
        string_enum(SafetyStage, "safety_decision_stage"), nullable=False
    )
    outcome_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )
    protection_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )
    status: Mapped[ReviewItemStatus] = mapped_column(
        string_enum(ReviewItemStatus, "safety_review_status"),
        default=ReviewItemStatus.OPEN,
        nullable=False,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action: Mapped[ReviewAction | None] = mapped_column(
        string_enum(ReviewAction, "safety_review_action")
    )
    actor_participant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(64))
    protection_action: Mapped[ProtectionAction | None] = mapped_column(
        string_enum(ProtectionAction, "safety_protection_action")
    )


class OutboundActionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbound_actions"
    __table_args__ = (
        UniqueConstraint("response_plan_id", "sequence_number"),
        UniqueConstraint("idempotency_key"),
        Index("ix_outbound_actions_claim", "status", "available_at", "created_at"),
        Index("ix_outbound_actions_lease", "status", "lease_expires_at"),
    )

    response_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("response_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[OutboundActionKind] = mapped_column(
        string_enum(OutboundActionKind, "outbound_action_kind"), nullable=False
    )
    origin: Mapped[ParticipationTrigger] = mapped_column(
        string_enum(ParticipationTrigger, "outbound_participation_origin"),
        default=ParticipationTrigger.ADDRESSED,
        nullable=False,
    )
    status: Mapped[OutboundActionStatus] = mapped_column(
        string_enum(OutboundActionStatus, "outbound_action_status"),
        default=OutboundActionStatus.PENDING,
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    reply_to_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), index=True
    )
    message_thread_id: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    mention_participant_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sticker_intent: Mapped[StickerIntent | None] = mapped_column(
        string_enum(StickerIntent, "outbound_sticker_intent")
    )
    delivered_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), unique=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_unknown_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_error_category: Mapped[str | None] = mapped_column(String(64))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_redacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class OutboundDeliveryAttemptModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbound_delivery_attempts"
    __table_args__ = (UniqueConstraint("outbound_action_id", "attempt_number"),)

    outbound_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbound_actions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    platform: Mapped[str] = mapped_column(
        String(32), default="telegram", nullable=False
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    external_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_milliseconds: Mapped[int | None] = mapped_column()
    status: Mapped[DeliveryAttemptStatus] = mapped_column(
        string_enum(DeliveryAttemptStatus, "outbound_delivery_attempt_status"),
        nullable=False,
    )
    certainty: Mapped[DeliveryCertainty] = mapped_column(
        string_enum(DeliveryCertainty, "outbound_delivery_certainty"), nullable=False
    )
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    retry_after_seconds: Mapped[float | None] = mapped_column()
    migration_conversation_id: Mapped[str | None] = mapped_column(String(255))


class OutboundRecoveryEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbound_recovery_events"

    outbound_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbound_actions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class OperationalRecoveryItemModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Generic recovery classification; deliberately contains no business content."""

    __tablename__ = "operational_recovery_items"
    __table_args__ = (
        UniqueConstraint("work_kind", "work_id"),
        Index("ix_operational_recovery_items_disposition", "disposition", "created_at"),
    )

    work_kind: Mapped[RecoveryKind] = mapped_column(
        string_enum(RecoveryKind, "recovery_work_kind"), nullable=False
    )
    work_id: Mapped[UUID] = mapped_column(nullable=False)
    disposition: Mapped[RecoveryDisposition] = mapped_column(
        string_enum(RecoveryDisposition, "recovery_disposition"), nullable=False
    )
    reason: Mapped[RecoveryReason] = mapped_column(
        string_enum(RecoveryReason, "recovery_reason"), nullable=False
    )
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalRecoveryEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operational_recovery_events"

    recovery_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("operational_recovery_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)


class ControlTenantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_tenants"
    __table_args__ = (UniqueConstraint("slug"),)

    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class ControlOperatorIdentityModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_operator_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlOperatorMembershipModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_operator_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "identity_id"),)

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_operator_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlAssistantBindingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_assistant_bindings"
    __table_args__ = (UniqueConstraint("tenant_id", "assistant_id"),)

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assistant_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ControlConnectionBindingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_connection_bindings"
    __table_args__ = (UniqueConstraint("tenant_id", "connection_id"),)

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class ControlGroupBindingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_group_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connection_id", "external_group_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_group_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )
    current_revision: Mapped[int] = mapped_column(default=0, nullable=False)


class ControlGroupRevisionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_group_configuration_revisions"
    __table_args__ = (UniqueConstraint("group_id", "revision"),)

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_group_bindings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    parent_revision: Mapped[int | None] = mapped_column()
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_operator_identities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(255))


class ControlAuditEventModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_audit_events"

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_identity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("control_operator_identities.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
        nullable=False,
    )


class ControlIdempotencyKeyModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "control_idempotency_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "identity_id", "operation", "key"),)

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    identity_id: Mapped[UUID] = mapped_column(
        ForeignKey("control_operator_identities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
