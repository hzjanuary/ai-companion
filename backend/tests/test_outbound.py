import asyncio
from uuid import uuid4

from app.application.outbound import compile_outbound_actions
from app.application.ports.platform import PlatformAdapterError, PlatformErrorCategory
from app.application.response_plan import ResponsePlanCandidate
from app.core.config import Settings
from app.domain.outbound import DeliveryCertainty
from app.domain.planning import PlanReasonCode, StickerIntent
from app.infrastructure.telegram.rendering import (
    MentionTarget,
    render_text_with_mentions,
)
from app.runtime.outbound_delivery_worker import _record_error


def test_compile_orders_text_then_sticker_with_stable_keys() -> None:
    plan_id = uuid4()
    candidate = ResponsePlanCandidate(
        should_respond=True,
        reason_code=PlanReasonCode.ANSWER,
        text="hi",
        sticker_intent=StickerIntent.LAUGH,
        confidence=1,
    )
    first = compile_outbound_actions(plan_id, candidate)
    second = compile_outbound_actions(plan_id, candidate)
    assert [item.kind.value for item in first] == ["text", "sticker"]
    assert [item.sequence_number for item in first] == [1, 2]
    assert [item.idempotency_key for item in first] == [
        item.idempotency_key for item in second
    ]


def test_silence_compiles_no_action() -> None:
    candidate = ResponsePlanCandidate(
        should_respond=False, reason_code=PlanReasonCode.SILENCE, confidence=1
    )
    assert compile_outbound_actions(uuid4(), candidate) == ()


def test_sticker_only_compiles_one_sticker_action() -> None:
    candidate = ResponsePlanCandidate(
        should_respond=True,
        reason_code=PlanReasonCode.SOCIAL_REPLY,
        sticker_intent=StickerIntent.LAUGH,
        confidence=1,
    )
    actions = compile_outbound_actions(uuid4(), candidate)
    assert len(actions) == 1
    assert actions[0].kind.value == "sticker"
    assert actions[0].text is None


def test_telegram_mentions_use_utf16_offsets_and_omit_missing_usernames() -> None:
    first, second = uuid4(), uuid4()
    text, entities = render_text_with_mentions(
        "Xin chao 😀",
        (
            MentionTarget(first, "lan"),
            MentionTarget(second, None),
            MentionTarget(first, "lan"),
        ),
    )
    assert text == "Xin chao 😀\n@lan"
    assert entities[0].offset == len("Xin chao 😀\n".encode("utf-16-le")) // 2
    assert entities[0].length == 4


def test_unknown_delivery_is_terminal_and_rejection_can_retry() -> None:
    class Repository:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def finalize(self, *args: object, **kwargs: object) -> bool:
            self.calls.append((args, kwargs))
            return True

    async def scenario() -> None:
        repository = Repository()
        await _record_error(  # type: ignore[arg-type]
            repository,
            uuid4(),
            "worker",
            1,
            Settings(_env_file=None),
            PlatformAdapterError(
                PlatformErrorCategory.TIMEOUT,
                "sendMessage",
                delivery_certainty=DeliveryCertainty.UNKNOWN,
            ),
        )
        assert repository.calls[0][0][2].value == "delivery_unknown"  # type: ignore[union-attr]
        await _record_error(  # type: ignore[arg-type]
            repository,
            uuid4(),
            "worker",
            1,
            Settings(_env_file=None),
            PlatformAdapterError(
                PlatformErrorCategory.RATE_LIMITED,
                "sendMessage",
                retryable=True,
                retry_after_seconds=2,
                delivery_certainty=DeliveryCertainty.REJECTED,
            ),
        )
        assert repository.calls[1][0][2].value == "pending"  # type: ignore[union-attr]

    asyncio.run(scenario())
