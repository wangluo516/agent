from datetime import datetime

import pytest

from app.domain.errors import AuthorizationError, ValidationError
from app.domain.models import Actor, Meeting, MeetingDraft, MeetingPatch
from app.domain.policies import (
    authorize_query,
    authorize_update,
    classify_unsafe_request,
    confirmation_hash,
    validate_draft,
)


def _draft() -> MeetingDraft:
    return MeetingDraft(
        title="设计评审",
        start_at=datetime(2026, 8, 20, 10, 0, tzinfo=None).astimezone(),
        end_at=datetime(2026, 8, 20, 11, 0, tzinfo=None).astimezone(),
        attendee_ids=("bob",),
    )


def _meeting() -> Meeting:
    return Meeting(
        id="m-1",
        organizer_id="alice",
        title="设计评审",
        start_at=_draft().start_at,
        end_at=_draft().end_at,
        attendee_ids=("bob",),
        version=1,
        idempotency_key="key-1",
    )


def test_validate_draft_rejects_empty_attendees() -> None:
    draft = _draft().model_copy(update={"attendee_ids": ()})

    with pytest.raises(ValidationError):
        validate_draft(draft)


def test_only_visible_actor_may_query_meeting() -> None:
    assert authorize_query(Actor(id="bob", display_name="Bob"), _meeting()) is True

    with pytest.raises(AuthorizationError):
        authorize_query(Actor(id="mallory", display_name="Mallory"), _meeting())


def test_only_organizer_may_update_meeting() -> None:
    with pytest.raises(AuthorizationError):
        authorize_update(
            Actor(id="bob", display_name="Bob"), _meeting(), MeetingPatch(title="改期")
        )


@pytest.mark.parametrize(
    "message",
    [
        "删除所有人的会议",
        "执行 DELETE FROM meetings",
        "SELECT * FROM meetings",
        "POST https://calendar.example/api/events",
    ],
)
def test_unsafe_requests_are_classified_before_writes(message: str) -> None:
    assert classify_unsafe_request(message) is not None


@pytest.mark.parametrize("message", ["create a meeting tomorrow", "update my meeting to 3pm"])
def test_normal_meeting_commands_are_not_classified_as_sql(message: str) -> None:
    assert classify_unsafe_request(message) is None


def test_confirmation_hash_changes_when_draft_changes() -> None:
    original = confirmation_hash("alice", "create", _draft())
    changed = confirmation_hash(
        "alice", "create", _draft().model_copy(update={"title": "预算评审"})
    )

    assert original != changed
