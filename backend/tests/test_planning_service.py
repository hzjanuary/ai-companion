import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.context import ContextMessage, ConversationContext
from app.application.model_provider import (
    GenerationRequest,
    ProviderCapabilities,
    ProviderError,
    ProviderResult,
    ProviderUsage,
)
from app.application.planning_service import generate_validated_plan
from app.application.response_plan import ResponsePlanPolicy, response_plan_json_schema
from app.domain.planning import ProviderErrorCategory, ProviderId, StickerIntent


class FakeProvider:
    capabilities = ProviderCapabilities(True, False, "max_tokens", True, True)

    def __init__(self, provider_id: ProviderId, values: list[object]) -> None:
        self.provider_id, self.model, self.values = provider_id, "fake", values
        self.calls = 0

    async def generate(self, _: GenerationRequest) -> ProviderResult:
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, ProviderError):
            raise value
        return ProviderResult(
            self.provider_id,
            self.model,
            str(value),
            None,
            ProviderUsage(None, None, None),
            timedelta(),
            "stop",
        )

    async def aclose(self) -> None:
        return None


def request() -> GenerationRequest:
    current = ContextMessage(
        uuid4(),
        uuid4(),
        uuid4(),
        None,
        "hello",
        datetime.now(UTC),
        None,
        "Mai",
        True,
        False,
    )
    return GenerationRequest(
        uuid4(),
        ConversationContext(current, (), ()),
        "v1",
        "s1",
        "vi",
        100,
        "system",
        "user",
        response_plan_json_schema(),
    )


def payload(value: GenerationRequest) -> str:
    return json.dumps(
        {
            "should_respond": True,
            "reason_code": "social_reply",
            "text": "ok",
            "reply_to_message_id": str(value.context.current.id),
            "mentions": [],
            "sticker_intent": None,
            "confidence": 0.7,
            "language": "vi",
        }
    )


def test_retry_correction_and_fallback_are_bounded() -> None:
    value = request()
    retryable = ProviderError(
        ProviderErrorCategory.TRANSPORT,
        ProviderId.OPENAI,
        "fake",
        True,
        "generate",
        "safe",
    )
    primary = FakeProvider(ProviderId.OPENAI, [retryable, "{}", "{}"])
    fallback = FakeProvider(ProviderId.OLLAMA, [payload(value)])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    result = asyncio.run(
        generate_validated_plan(
            value,
            ResponsePlanPolicy(100, frozenset(StickerIntent)),
            primary,
            fallback,
            2,
            1,
            sleep,
        )
    )
    assert result.candidate is not None
    assert primary.calls == 3 and fallback.calls == 1
    assert sleeps == [0.25]


def test_safety_refusal_does_not_fallback() -> None:
    value = request()
    refusal = ProviderError(
        ProviderErrorCategory.SAFETY_REFUSAL,
        ProviderId.OPENAI,
        "fake",
        False,
        "generate",
        "safe",
    )
    primary = FakeProvider(ProviderId.OPENAI, [refusal])
    fallback = FakeProvider(ProviderId.OLLAMA, [payload(value)])
    result = asyncio.run(
        generate_validated_plan(
            value,
            ResponsePlanPolicy(100, frozenset(StickerIntent)),
            primary,
            fallback,
            1,
            1,
        )
    )
    assert result.candidate is None
    assert fallback.calls == 0
