import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.context import ContextMessage, ConversationContext
from app.application.model_provider import (
    GenerationRequest,
    ModelProvider,
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


def test_retry_exhaustion_returns_the_retryable_error_after_bounded_fallback() -> None:
    value = request()
    primary_error = ProviderError(
        ProviderErrorCategory.TRANSPORT,
        ProviderId.OPENAI,
        "fake-primary",
        True,
        "generate",
        "safe",
    )
    fallback_error = ProviderError(
        ProviderErrorCategory.RATE_LIMITED,
        ProviderId.OLLAMA,
        "fake-fallback",
        True,
        "generate",
        "safe",
    )
    primary = FakeProvider(ProviderId.OPENAI, [primary_error, primary_error])
    fallback = FakeProvider(ProviderId.OLLAMA, [fallback_error, fallback_error])
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
            0,
            sleep,
        )
    )

    assert result.candidate is None
    assert result.provider_error == fallback_error
    assert result.provider == fallback
    assert primary.calls == 2
    assert fallback.calls == 2
    assert sleeps == [0.25, 0.25]


def test_pre_provider_gate_prevents_model_io_and_attempt_recording() -> None:
    value = request()
    primary = FakeProvider(ProviderId.OPENAI, [payload(value)])
    attempts: list[object] = []

    async def before_provider(provider: ModelProvider) -> ProviderError:
        return ProviderError(
            ProviderErrorCategory.RATE_LIMITED,
            provider.provider_id,
            provider.model,
            True,
            "generate",
            "bounded retry",
        )

    async def record(
        provider: ModelProvider,
        succeeded: bool,
        error: ProviderError | None,
        correction: int,
    ) -> None:
        attempts.append((provider, succeeded, error, correction))

    result = asyncio.run(
        generate_validated_plan(
            value,
            ResponsePlanPolicy(100, frozenset(StickerIntent)),
            primary,
            None,
            1,
            1,
            on_attempt=record,
            before_provider=before_provider,
        )
    )
    assert result.provider_error is not None
    assert result.provider_error.category == ProviderErrorCategory.RATE_LIMITED
    assert primary.calls == 0
    assert attempts == []
