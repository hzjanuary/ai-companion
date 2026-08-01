from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.context import ContextMessage, ConversationContext
from app.application.prompting import build_generation_request
from app.application.rate_limiting import InMemoryRateLimiter
from app.application.response_plan import (
    InteractionMetadata,
    ResponsePlanCandidate,
    ResponsePlanPolicy,
)
from app.domain.planning import PlanReasonCode
from app.domain.rate_limit import RateLimitOperation, RateLimitRule, RateLimitScope
from app.domain.safety import (
    InteractionKind,
    SensitiveTopicCategory,
    safe_fallback,
)


def _context(
    *,
    mention_allowed: bool = True,
    teasing_allowed: bool = True,
    privacy_deleted: bool = False,
) -> ConversationContext:
    participant_id = uuid4()
    message = ContextMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        participant_id=participant_id,
        platform_thread_id=None,
        text="untrusted fixture message",
        sent_at=datetime.now(UTC),
        reply_to_message_id=None,
        sender_display_name="Fixture",
        mention_allowed=mention_allowed,
        teasing_allowed=teasing_allowed,
        privacy_deleted=privacy_deleted,
    )
    return ConversationContext(message, (), ())


def _candidate(context: ConversationContext) -> ResponsePlanCandidate:
    return ResponsePlanCandidate(
        should_respond=True,
        reason_code=PlanReasonCode.ACKNOWLEDGEMENT,
        text="fixture text",
        reply_to_message_id=context.current.id,
        confidence=0.9,
        interaction=InteractionMetadata(
            kind=InteractionKind.TEASING,
            teasing_target_participant_ids=[context.current.participant_id],
        ),
    )


def test_response_plan_v2_rejects_invalid_teasing_shape() -> None:
    with pytest.raises(ValueError):
        ResponsePlanCandidate.model_validate(
            {
                "should_respond": True,
                "reason_code": "acknowledgement",
                "text": "x",
                "confidence": 1.0,
                "interaction": {"kind": "teasing"},
            }
        )


@pytest.mark.parametrize("field", ["teasing_allowed", "privacy_deleted"])
def test_opted_out_or_deleted_teasing_is_replaced_with_safe_neutral_fallback(
    field: str,
) -> None:
    context = _context(**{field: False if field == "teasing_allowed" else True})
    result = ResponsePlanPolicy(500, frozenset()).apply(_candidate(context), context)
    assert result.interaction.kind == InteractionKind.NEUTRAL
    assert result.text == safe_fallback(None)
    assert result.sticker_intent is None


def test_sensitive_teasing_and_personality_boundary_cannot_be_weakened() -> None:
    context = _context()
    sensitive = _candidate(context).model_copy(
        update={
            "interaction": InteractionMetadata(
                kind=InteractionKind.TEASING,
                teasing_target_participant_ids=[context.current.participant_id],
                sensitive_topic_categories=[SensitiveTopicCategory.BODY],
            )
        }
    )
    assert ResponsePlanPolicy(500, frozenset()).apply(
        sensitive, context
    ).text == safe_fallback(None)
    assert ResponsePlanPolicy(500, frozenset(), teasing_permitted=False).apply(
        _candidate(context), context
    ).text == safe_fallback(None)


def test_prompt_safety_policy_is_deterministic_and_context_stays_untrusted() -> None:
    context = _context()
    request = build_generation_request(
        planning_job_id=uuid4(),
        context=context,
        prompt_version="test",
        response_schema_version="response-plan-v2",
        maximum_output_tokens=100,
        conversation_type="group",
        response_mode="mention_only",
    )
    assert "safety-policy-v1" in request.system_instructions
    assert "untrusted" in request.system_instructions
    assert '"response_schema_version":"response-plan-v2"' in request.user_content
    assert "untrusted fixture message" in request.user_content


def test_fake_multi_scope_limiter_is_atomic_and_returns_deterministic_retry() -> None:
    now = [100.0]
    limiter = InMemoryRateLimiter(lambda: now[0])
    rules = (
        RateLimitRule(RateLimitScope.DEPLOYMENT, "deployment", 2, 60),
        RateLimitRule(RateLimitScope.CONVERSATION, "conversation", 1, 60),
    )

    async def scenario() -> None:
        assert (await limiter.check(RateLimitOperation.GENERATION, rules)).allowed
        denied = await limiter.check(RateLimitOperation.GENERATION, rules)
        assert not denied.allowed
        assert denied.limiting_scope == RateLimitScope.CONVERSATION
        assert denied.retry_after_seconds == 60
        now[0] += 60
        assert (await limiter.check(RateLimitOperation.GENERATION, rules)).allowed

    import asyncio

    asyncio.run(scenario())
