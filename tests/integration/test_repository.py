from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.errors import ConflictError
from app.domain.models import Actor, MeetingDraft, MeetingPatch
from app.repositories.meetings import MeetingRepository


@pytest.fixture
def repository(tmp_path: Path) -> MeetingRepository:
    return MeetingRepository(tmp_path / "meetings.db")


@pytest.fixture
def draft() -> MeetingDraft:
    return MeetingDraft(
        title="设计评审",
        start_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
        attendee_ids=("bob",),
    )


def test_create_is_idempotent_for_same_key(
    repository: MeetingRepository, draft: MeetingDraft
) -> None:
    first = repository.create("alice", draft, "request-1")
    second = repository.create("alice", draft, "request-1")

    assert second == first
    assert len(repository.list_for_actor(Actor(id="alice", display_name="Alice"))) == 1


def test_idempotency_key_is_scoped_to_organizer(
    repository: MeetingRepository, draft: MeetingDraft
) -> None:
    alice_meeting = repository.create("alice", draft, "request-1")
    bob_meeting = repository.create("bob", draft, "request-1")

    assert bob_meeting.id != alice_meeting.id
    assert bob_meeting.organizer_id == "bob"


def test_list_and_find_visible_hide_other_peoples_meetings(
    repository: MeetingRepository, draft: MeetingDraft
) -> None:
    meeting = repository.create("alice", draft, "request-1")

    assert repository.find_visible(Actor(id="bob", display_name="Bob"), meeting.id) == meeting
    assert repository.find_visible(Actor(id="mallory", display_name="Mallory"), meeting.id) is None


def test_update_uses_optimistic_version_lock(
    repository: MeetingRepository, draft: MeetingDraft
) -> None:
    meeting = repository.create("alice", draft, "request-1")
    updated = repository.update(
        "alice", meeting.id, MeetingPatch(title="预算评审"), expected_version=1
    )

    assert updated.title == "预算评审"
    assert updated.version == 2
    with pytest.raises(ConflictError):
        repository.update("alice", meeting.id, MeetingPatch(title="过期写入"), expected_version=1)


def test_empty_patch_is_rejected_without_version_increment(
    repository: MeetingRepository, draft: MeetingDraft
) -> None:
    meeting = repository.create("alice", draft, "request-1")

    with pytest.raises(ConflictError):
        repository.update("alice", meeting.id, MeetingPatch(), expected_version=1)

    assert repository.find_visible(Actor(id="alice", display_name="Alice"), meeting.id).version == 1
