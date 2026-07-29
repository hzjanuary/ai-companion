from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.context import ContextMessage, build_context
from app.application.conversation import CharacterTokenEstimator


def message(
    *,
    conversation_id: UUID,
    minutes: int,
    text: str = "hello",
    thread: str | None = None,
    reply_to: UUID | None = None,
) -> ContextMessage:
    identifier = uuid4()
    return ContextMessage(
        id=identifier,
        conversation_id=conversation_id,
        participant_id=uuid4(),
        platform_thread_id=thread,
        text=text,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes),
        reply_to_message_id=reply_to,
        sender_display_name="Tester",
        mention_allowed=True,
        teasing_allowed=False,
    )


def test_context_keeps_current_reply_chain_and_bounded_thread_history() -> None:
    conversation_id = uuid4()
    root = message(conversation_id=conversation_id, minutes=1, text="root")
    reply = message(
        conversation_id=conversation_id, minutes=2, text="reply", reply_to=root.id
    )
    current = message(
        conversation_id=conversation_id, minutes=3, text="current", reply_to=reply.id
    )
    same_thread = message(conversation_id=conversation_id, minutes=4, text="recent")
    other_thread = message(
        conversation_id=conversation_id, minutes=5, text="other", thread="topic"
    )
    result = build_context(
        current=current,
        candidates=(root, reply, same_thread, other_thread),
        now=datetime(2026, 1, 2, tzinfo=UTC),
        recent_limit=2,
        reply_chain_depth=2,
        token_budget=20,
        character_limit=100,
        max_age_days=30,
        estimator=CharacterTokenEstimator(),
    )
    assert result.current == current
    assert result.reply_chain == (reply, root)
    assert result.recent_history == (same_thread,)


def test_context_does_not_include_cross_conversation_or_over_budget_content() -> None:
    conversation_id = uuid4()
    current = message(conversation_id=conversation_id, minutes=3, text="current")
    foreign = message(conversation_id=uuid4(), minutes=4, text="foreign")
    oversized = message(conversation_id=conversation_id, minutes=5, text="x" * 100)
    result = build_context(
        current=current,
        candidates=(foreign, oversized),
        now=datetime(2026, 1, 2, tzinfo=UTC),
        recent_limit=2,
        reply_chain_depth=0,
        token_budget=3,
        character_limit=100,
        max_age_days=30,
        estimator=CharacterTokenEstimator(),
    )
    assert result.recent_history == ()
