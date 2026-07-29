"""Pure conversation eligibility and context contracts."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.conversation import EligibilityDecision, EligibilityReason
from app.domain.persistence import (
    AssistantStatus,
    ConversationStatus,
    PlatformConnectionStatus,
    ResponseMode,
)


@dataclass(frozen=True, slots=True)
class EligibilityInput:
    assistant_status: AssistantStatus
    connection_status: PlatformConnectionStatus
    conversation_status: ConversationStatus
    conversation_type: str
    response_mode: ResponseMode
    assistant_platform_user_id: str
    assistant_display_name: str
    sender_platform_user_id: str
    sender_is_bot: bool
    message_type: str
    message_text: str | None
    mentions_assistant: bool
    replies_to_assistant: bool
    is_edit: bool
    is_membership_event: bool


def evaluate_eligibility(value: EligibilityInput) -> EligibilityDecision:
    """Apply deterministic pre-LLM response eligibility rules."""

    if value.is_membership_event:
        return EligibilityDecision(
            False, EligibilityReason.MEMBERSHIP_EVENT_NO_RESPONSE
        )
    if value.assistant_status != AssistantStatus.ACTIVE:
        return EligibilityDecision(False, EligibilityReason.ASSISTANT_INACTIVE)
    if value.connection_status != PlatformConnectionStatus.ACTIVE:
        return EligibilityDecision(False, EligibilityReason.CONNECTION_INACTIVE)
    if (
        value.conversation_status != ConversationStatus.ACTIVE
        or value.response_mode == ResponseMode.PAUSED
    ):
        return EligibilityDecision(False, EligibilityReason.CONVERSATION_PAUSED)
    if value.sender_platform_user_id == value.assistant_platform_user_id:
        return EligibilityDecision(False, EligibilityReason.SENDER_IS_ASSISTANT)
    if value.sender_is_bot:
        return EligibilityDecision(False, EligibilityReason.SENDER_IS_BOT)
    if value.message_type != "text" or not value.message_text:
        return EligibilityDecision(False, EligibilityReason.UNSUPPORTED_MESSAGE_TYPE)
    if value.is_edit:
        return EligibilityDecision(False, EligibilityReason.EDITED_MESSAGE_NO_RESPONSE)
    if value.conversation_type == "private":
        return EligibilityDecision(True, EligibilityReason.ELIGIBLE_PRIVATE_MESSAGE)
    if value.response_mode == ResponseMode.MENTION_ONLY:
        if value.mentions_assistant:
            return EligibilityDecision(
                True, EligibilityReason.ELIGIBLE_ASSISTANT_MENTIONED
            )
        if value.replies_to_assistant:
            return EligibilityDecision(
                True, EligibilityReason.ELIGIBLE_REPLY_TO_ASSISTANT
            )
        return EligibilityDecision(False, EligibilityReason.NOT_ADDRESSED_TO_ASSISTANT)
    if value.response_mode == ResponseMode.MENTION_AND_NAME:
        if value.mentions_assistant:
            return EligibilityDecision(
                True, EligibilityReason.ELIGIBLE_ASSISTANT_MENTIONED
            )
        if value.replies_to_assistant:
            return EligibilityDecision(
                True, EligibilityReason.ELIGIBLE_REPLY_TO_ASSISTANT
            )
        name = value.assistant_display_name.casefold().strip()
        if name and name in value.message_text.casefold():
            return EligibilityDecision(True, EligibilityReason.ELIGIBLE_ASSISTANT_NAME)
        return EligibilityDecision(False, EligibilityReason.NOT_ADDRESSED_TO_ASSISTANT)
    if value.response_mode == ResponseMode.AMBIENT_SELECTIVE:
        return EligibilityDecision(True, EligibilityReason.ELIGIBLE_AMBIENT_CANDIDATE)


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int: ...


class CharacterTokenEstimator:
    """Deterministic development estimate; it is not provider-tokenizer exact."""

    def estimate(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4) if text else 0


@dataclass(frozen=True, slots=True)
class ConversationProcessResult:
    incoming_update_id: UUID
    duplicate: bool
    outcome: str
    conversation_id: UUID | None
    message_id: UUID | None
    eligibility: EligibilityDecision | None
