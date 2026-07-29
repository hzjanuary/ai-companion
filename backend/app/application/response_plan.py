"""Strict local response-plan schema and deterministic post-generation policy."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.context import ConversationContext
from app.domain.planning import PlanReasonCode, StickerIntent


class ResponsePlanCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    should_respond: bool
    reason_code: PlanReasonCode
    text: str | None = None
    reply_to_message_id: UUID | None = None
    mentions: list[UUID] = Field(default_factory=list, max_length=20)
    sticker_intent: StickerIntent | None = None
    confidence: float = Field(ge=0, le=1)
    language: str | None = Field(default=None, min_length=2, max_length=16)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "ResponsePlanCandidate":
        if self.text is not None and not self.text.strip():
            raise ValueError("text must be nonblank when present")
        has_action = self.text is not None or self.sticker_intent is not None
        if self.should_respond and not has_action:
            raise ValueError("a response requires text or sticker intent")
        if not self.should_respond and (
            has_action or self.reply_to_message_id is not None or self.mentions
        ):
            raise ValueError("silence cannot contain action fields")
        return self


@dataclass(frozen=True, slots=True)
class ResponsePlanPolicy:
    text_limit: int
    supported_stickers: frozenset[StickerIntent]

    def apply(
        self, candidate: ResponsePlanCandidate, context: ConversationContext
    ) -> ResponsePlanCandidate:
        allowed_messages = {
            item.id
            for item in (context.current, *context.reply_chain, *context.recent_history)
        }
        allowed_participants = {
            item.participant_id: item
            for item in (context.current, *context.reply_chain, *context.recent_history)
            if item.participant_id is not None
        }
        if (
            candidate.reply_to_message_id is not None
            and candidate.reply_to_message_id not in allowed_messages
        ):
            raise ValueError("reply target is outside context")
        mentions = tuple(dict.fromkeys(candidate.mentions))
        if any(identifier not in allowed_participants for identifier in mentions):
            raise ValueError("mention target is outside context")
        mentions = tuple(
            identifier
            for identifier in mentions
            if allowed_participants[identifier].mention_allowed
        )
        text = candidate.text
        if text is not None:
            text = text[: self.text_limit].strip() or None
        sticker = candidate.sticker_intent
        if sticker is not None and sticker not in self.supported_stickers:
            sticker = None
        if candidate.should_respond and text is None and sticker is None:
            return ResponsePlanCandidate(
                should_respond=False,
                reason_code=PlanReasonCode.SILENCE,
                confidence=candidate.confidence,
                language=candidate.language,
            )
        return ResponsePlanCandidate(
            should_respond=candidate.should_respond,
            reason_code=candidate.reason_code,
            text=text,
            reply_to_message_id=(
                candidate.reply_to_message_id
                if candidate.reply_to_message_id is not None
                else context.current.id
                if candidate.should_respond
                else None
            ),
            mentions=list(mentions),
            sticker_intent=sticker,
            confidence=candidate.confidence,
            language=candidate.language,
        )


def response_plan_json_schema() -> dict[str, object]:
    """Stable strict schema sent to providers and checked locally again."""

    return ResponsePlanCandidate.model_json_schema()
