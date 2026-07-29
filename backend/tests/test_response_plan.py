from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.context import ContextMessage, ConversationContext
from app.application.prompting import build_generation_request
from app.application.response_plan import ResponsePlanCandidate, ResponsePlanPolicy
from app.domain.planning import PlanReasonCode, StickerIntent


def context() -> ConversationContext:
    participant = uuid4()
    current = ContextMessage(
        uuid4(),
        uuid4(),
        participant,
        None,
        "hello",
        datetime.now(UTC),
        None,
        "Mai",
        True,
        False,
    )
    blocked = ContextMessage(
        uuid4(),
        current.conversation_id,
        uuid4(),
        None,
        "old",
        datetime.now(UTC),
        None,
        "Nam",
        False,
        False,
    )
    return ConversationContext(current, (), (blocked,))


def test_response_plan_rejects_invalid_shapes() -> None:
    with pytest.raises(ValidationError):
        ResponsePlanCandidate.model_validate(
            {"should_respond": True, "reason_code": "social_reply", "confidence": 2}
        )
    with pytest.raises(ValidationError):
        ResponsePlanCandidate.model_validate(
            {
                "should_respond": False,
                "reason_code": "silence",
                "text": "no",
                "confidence": 0.1,
            }
        )


def test_policy_normalizes_mentions_and_unsupported_sticker() -> None:
    value = context()
    candidate = ResponsePlanCandidate(
        should_respond=True,
        reason_code=PlanReasonCode.SOCIAL_REPLY,
        text=" xin chao ",
        mentions=[
            value.current.participant_id,
            value.current.participant_id,
            value.recent_history[0].participant_id,
        ],
        sticker_intent=StickerIntent.LAUGH,
        confidence=0.7,
    )
    result = ResponsePlanPolicy(20, frozenset()).apply(candidate, value)
    assert result.text == "xin chao"
    assert result.mentions == [value.current.participant_id]
    assert result.sticker_intent is None
    assert result.reply_to_message_id == value.current.id


def test_prompt_is_deterministic_and_delimits_untrusted_content() -> None:
    value = context()
    first = build_generation_request(
        planning_job_id=uuid4(),
        context=value,
        prompt_version="v1",
        response_schema_version="s1",
        maximum_output_tokens=100,
        conversation_type="private",
        response_mode="mention_only",
    )
    second = build_generation_request(
        planning_job_id=first.planning_job_id,
        context=value,
        prompt_version="v1",
        response_schema_version="s1",
        maximum_output_tokens=100,
        conversation_type="private",
        response_mode="mention_only",
    )
    assert first.user_content == second.user_content
    assert "platform actions" in first.system_instructions
    assert str(value.current.participant_id) in first.user_content
