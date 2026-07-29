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


def test_personality_snapshot_changes_prompt_deterministically() -> None:
    value = context()
    profile_id, version_id, revision_id = uuid4(), uuid4(), uuid4()
    personality = {
        "profile_id": profile_id,
        "profile_version_id": version_id,
        "profile_version_number": 1,
        "personality_schema_version": "personality-profile-v1",
        "configuration_revision_id": revision_id,
        "configuration_revision_number": 2,
        "role": "friendly_group_companion",
        "primary_language": "auto",
        "self_reference": "minh",
        "default_length": "short",
        "formality": "casual",
        "humor_level": 0.5,
        "teasing_level": 0.2,
        "emoji_frequency": 0.2,
        "sticker_frequency": 0.1,
        "use_member_names": True,
        "use_inside_jokes": False,
        "ask_follow_up_questions": "sometimes",
        "allow_sensitive_teasing": False,
        "stop_teasing_on_request": True,
        "reveal_private_memory_in_groups": False,
    }
    kwargs = {
        "planning_job_id": uuid4(),
        "context": value,
        "prompt_version": "v1",
        "response_schema_version": "s1",
        "maximum_output_tokens": 100,
        "conversation_type": "group",
        "response_mode": "mention_only",
        "effective_personality": personality,
        "stickers_enabled": False,
    }
    first = build_generation_request(**kwargs)
    second = build_generation_request(**kwargs)
    changed = build_generation_request(
        **{**kwargs, "effective_personality": {**personality, "humor_level": 0.1}}
    )
    assert first.user_content == second.user_content
    assert first.user_content != changed.user_content
    assert '"sticker_intent":false' in first.user_content
