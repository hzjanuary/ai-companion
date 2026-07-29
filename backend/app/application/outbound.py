"""Compile approved response plans into deterministic outbound action specs."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from app.application.response_plan import ResponsePlanCandidate
from app.domain.outbound import (
    DeliveryCertainty,
    OutboundActionKind,
    OutboundActionStatus,
)
from app.domain.planning import StickerIntent


@dataclass(frozen=True, slots=True)
class OutboundActionSpec:
    sequence_number: int
    kind: OutboundActionKind
    idempotency_key: str
    text: str | None
    reply_to_message_id: UUID | None
    mention_participant_ids: tuple[UUID, ...]
    sticker_intent: StickerIntent | None


@dataclass(frozen=True, slots=True)
class OutboundAction:
    id: UUID
    response_plan_id: UUID
    conversation_id: UUID
    sequence_number: int
    kind: OutboundActionKind
    status: OutboundActionStatus
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class OutboundActionClaim:
    action_id: UUID
    owner: str
    attempt_number: int
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryRequest:
    action_id: UUID
    conversation_id: UUID
    kind: OutboundActionKind


@dataclass(frozen=True, slots=True)
class ConfirmedDelivery:
    platform_message_id: str
    platform_thread_id: str | None


@dataclass(frozen=True, slots=True)
class DeliveryFailure:
    certainty: DeliveryCertainty
    category: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ActionCompletion:
    action_id: UUID
    status: OutboundActionStatus
    certainty: DeliveryCertainty


def compile_outbound_actions(
    response_plan_id: UUID, candidate: ResponsePlanCandidate
) -> tuple[OutboundActionSpec, ...]:
    """Create stable action records without importing platform concerns."""

    if not candidate.should_respond:
        return ()
    actions: list[OutboundActionSpec] = []
    if candidate.text is not None:
        actions.append(
            _action(
                response_plan_id, len(actions) + 1, OutboundActionKind.TEXT, candidate
            )
        )
    if candidate.sticker_intent is not None:
        actions.append(
            _action(
                response_plan_id,
                len(actions) + 1,
                OutboundActionKind.STICKER,
                candidate,
            )
        )
    return tuple(actions)


def _action(
    response_plan_id: UUID,
    sequence_number: int,
    kind: OutboundActionKind,
    candidate: ResponsePlanCandidate,
) -> OutboundActionSpec:
    key_material = f"{response_plan_id}:{sequence_number}:{kind.value}".encode()
    return OutboundActionSpec(
        sequence_number=sequence_number,
        kind=kind,
        idempotency_key=sha256(key_material).hexdigest(),
        text=candidate.text if kind == OutboundActionKind.TEXT else None,
        reply_to_message_id=candidate.reply_to_message_id,
        mention_participant_ids=tuple(candidate.mentions),
        sticker_intent=candidate.sticker_intent
        if kind == OutboundActionKind.STICKER
        else None,
    )
