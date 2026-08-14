from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.errors import ConflictError
from app.domain.models import Actor, MeetingDraft, MeetingPatch
from app.repositories import meetings as meetings_module
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


def test_repository_closes_every_sqlite_connection(
    tmp_path: Path, draft: MeetingDraft, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_connect = meetings_module.sqlite3.connect
    connections = []

    class TrackingConnection:
        def __init__(self, *args, **kwargs) -> None:
            self._connection = original_connect(*args, **kwargs)
            self.closed = False

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, *args):
            return self._connection.__exit__(*args)

        def close(self) -> None:
            self.closed = True
            self._connection.close()

        @property
        def row_factory(self):
            return self._connection.row_factory

        @row_factory.setter
        def row_factory(self, value) -> None:
            self._connection.row_factory = value

        def __getattr__(self, name):
            return getattr(self._connection, name)

    def tracking_connect(*args, **kwargs):
        connection = TrackingConnection(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(meetings_module.sqlite3, "connect", tracking_connect)
    repository = MeetingRepository(tmp_path / "connections.db")
    meeting = repository.create("alice", draft, "request-connection")
    actor = Actor(id="alice", display_name="Alice")
    repository.list_for_actor(actor)
    repository.find_visible(actor, meeting.id)
    repository.update("alice", meeting.id, MeetingPatch(title="连接测试"), meeting.version)

    assert connections
    assert all(connection.closed for connection in connections)
