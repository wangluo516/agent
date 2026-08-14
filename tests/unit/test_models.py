from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.domain.models import Actor, ConversationState, MeetingDraft, MeetingPatch


def test_meeting_draft_requires_timezone_aware_future_interval() -> None:
    with pytest.raises(ValidationError):
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 20, 10, 0),  # noqa: DTZ001
            end_at=datetime(2026, 8, 20, 9, 0),  # noqa: DTZ001
            attendee_ids=("alice",),
        )


def test_conversation_state_merge_returns_new_state_without_mutating_original() -> None:
    state = ConversationState(actor_id="alice", conversation_id="c-1")
    updated = state.with_draft(MeetingPatch(title="新的主题"))

    assert state.draft is None
    assert updated.draft is not None
    assert updated.draft.title == "新的主题"
    assert updated is not state


def test_actor_is_immutable() -> None:
    actor = Actor(id="alice", display_name="Alice")

    with pytest.raises(ValidationError):
        actor.id = "bob"


def test_meeting_times_are_normalized_to_asia_shanghai() -> None:
    draft = MeetingDraft(
        title="跨时区评审",
        start_at=datetime(2026, 8, 20, 2, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 20, 3, 0, tzinfo=UTC),
        attendee_ids=("alice",),
    )

    assert isinstance(draft.start_at.tzinfo, ZoneInfo)
    assert draft.start_at.tzinfo.key == "Asia/Shanghai"
    assert draft.start_at.hour == 10


def test_patch_preserves_explicit_none_for_optional_times() -> None:
    patch = MeetingPatch(start_at=None, end_at=None)

    assert patch.start_at is None
    assert patch.end_at is None
