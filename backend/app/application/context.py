"""Pure bounded conversation-context selection."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.application.conversation import TokenEstimator


@dataclass(frozen=True, slots=True)
class ContextMessage:
    id: UUID
    conversation_id: UUID
    participant_id: UUID | None
    platform_thread_id: str | None
    text: str | None
    sent_at: datetime
    reply_to_message_id: UUID | None
    sender_display_name: str
    mention_allowed: bool
    teasing_allowed: bool
    privacy_deleted: bool = False


@dataclass(frozen=True, slots=True)
class ContextMemory:
    """An explicitly stored fact safe to include as untrusted model context."""

    public_id: str
    content: str
    created_at: datetime
    creator_label: str


@dataclass(frozen=True, slots=True)
class ContextSummary:
    """Derived, same-conversation history that remains untrusted context."""

    summary: str
    schema_version: str
    prompt_version: str
    source_ended_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationContext:
    current: ContextMessage
    reply_chain: tuple[ContextMessage, ...]
    recent_history: tuple[ContextMessage, ...]
    explicit_memories: tuple[ContextMemory, ...] = ()
    historical_summary: ContextSummary | None = None


def build_context(
    *,
    current: ContextMessage,
    candidates: tuple[ContextMessage, ...],
    now: datetime,
    recent_limit: int,
    reply_chain_depth: int,
    token_budget: int,
    character_limit: int,
    max_age_days: int,
    estimator: TokenEstimator,
    explicit_memories: tuple[ContextMemory, ...] = (),
    memory_character_budget: int = 1200,
    historical_summary: ContextSummary | None = None,
) -> ConversationContext:
    """Select current, reply ancestors, then newest eligible history under budget."""

    by_id = {message.id: message for message in candidates}
    allowed_after = now - timedelta(days=max_age_days)
    accepted: list[ContextMessage] = [current]
    used = _cost(current, character_limit, estimator)
    chain: list[ContextMessage] = []
    ancestor_id = current.reply_to_message_id
    while ancestor_id is not None and len(chain) < reply_chain_depth:
        ancestor = by_id.get(ancestor_id)
        if ancestor is None or ancestor.sent_at < allowed_after:
            break
        cost = _cost(ancestor, character_limit, estimator)
        if used + cost > token_budget:
            break
        chain.append(ancestor)
        accepted.append(ancestor)
        used += cost
        ancestor_id = ancestor.reply_to_message_id

    summary = historical_summary
    if summary is not None:
        summary_cost = estimator.estimate(summary.summary[:character_limit])
        if used + summary_cost <= token_budget:
            used += summary_cost
        else:
            summary = None

    history: list[ContextMessage] = []
    excluded = {item.id for item in accepted}
    for candidate in sorted(
        candidates, key=lambda item: (item.sent_at, str(item.id)), reverse=True
    ):
        if len(history) >= recent_limit:
            break
        if candidate.id in excluded or candidate.sent_at < allowed_after:
            continue
        if candidate.conversation_id != current.conversation_id:
            continue
        if candidate.platform_thread_id != current.platform_thread_id:
            continue
        if summary is not None and candidate.sent_at <= summary.source_ended_at:
            continue
        cost = _cost(candidate, character_limit, estimator)
        if used + cost > token_budget:
            continue
        history.append(candidate)
        used += cost
    return ConversationContext(
        current=current,
        reply_chain=tuple(chain),
        recent_history=tuple(history),
        explicit_memories=_select_memories(explicit_memories, memory_character_budget),
        historical_summary=summary,
    )


def _cost(
    message: ContextMessage, character_limit: int, estimator: TokenEstimator
) -> int:
    return estimator.estimate((message.text or "")[:character_limit])


def _select_memories(
    memories: tuple[ContextMemory, ...], character_budget: int
) -> tuple[ContextMemory, ...]:
    """Keep a deterministic bounded prefix without consuming message-token budget."""

    selected: list[ContextMemory] = []
    used = 0
    for memory in memories:
        if not memory.content:
            continue
        cost = len(memory.content)
        if used + cost > character_budget:
            continue
        selected.append(memory)
        used += cost
    return tuple(selected)
