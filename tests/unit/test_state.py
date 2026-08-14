from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent.interpreter import MeetingCommand
from app.agent.state import reduce_command
from app.domain.models import ConversationState, MeetingPatch, PendingAction

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_reducer_returns_new_state_and_merges_partial_draft() -> None:
    original = ConversationState(
        actor_id="alice",
        conversation_id="chat-1",
        draft=MeetingPatch(title="设计评审", attendee_ids=("bob",)),
    )

    updated = reduce_command(
        original, MeetingCommand(operation="create", patch=MeetingPatch(room_id="room-1"))
    )

    assert updated is not original
    assert original.draft.room_id is None
    assert updated.draft == MeetingPatch(title="设计评审", attendee_ids=("bob",), room_id="room-1")


def test_reducer_invalidates_confirmation_when_draft_changes() -> None:
    original = ConversationState(
        actor_id="alice",
        conversation_id="chat-1",
        draft=MeetingPatch(title="设计评审"),
        pending_action=PendingAction(action="create", confirmation_hash="old-hash"),
        status="needs_confirmation",
    )

    updated = reduce_command(
        original,
        MeetingCommand(operation="create", patch=MeetingPatch(title="预算评审")),
    )

    assert updated.pending_action is None
    assert updated.status == "collecting"


def test_update_replaces_prior_draft_and_switches_to_explicit_target() -> None:
    original = ConversationState(
        actor_id="alice",
        conversation_id="chat-1",
        draft=MeetingPatch(title="会议 A", attendee_ids=("carol",), room_id="room-a"),
        selected_meeting_id="meeting-a",
    )

    updated = reduce_command(
        original,
        MeetingCommand(
            operation="update",
            meeting_id="meeting-b",
            patch=MeetingPatch(title="会议 B"),
        ),
    )

    assert updated.selected_meeting_id == "meeting-b"
    assert updated.draft == MeetingPatch(title="会议 B")


def test_pending_update_edit_merges_with_preview_and_keeps_target() -> None:
    original = ConversationState(
        actor_id="alice",
        conversation_id="chat-1",
        draft=MeetingPatch(
            title="设计评审",
            attendee_ids=("bob",),
            room_id="room-a",
        ),
        selected_meeting_id="meeting-a",
        pending_action=PendingAction(
            action="update",
            meeting_id="meeting-a",
            confirmation_hash="old-hash",
        ),
        status="needs_confirmation",
    )

    updated = reduce_command(
        original,
        MeetingCommand(
            operation="update",
            patch=MeetingPatch(attendee_ids=("bob", "adam")),
        ),
    )

    assert updated.selected_meeting_id == "meeting-a"
    assert updated.draft == MeetingPatch(
        title="设计评审",
        attendee_ids=("bob", "adam"),
        room_id="room-a",
    )
    assert updated.pending_action is None
    assert updated.status == "collecting"


def test_pending_edit_of_start_time_preserves_existing_duration() -> None:
    original = ConversationState(
        actor_id="alice",
        conversation_id="chat-1",
        draft=MeetingPatch(
            title="开发会议",
            start_at=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        pending_action=PendingAction(action="create", confirmation_hash="old-hash"),
        status="needs_confirmation",
    )

    updated = reduce_command(
        original,
        MeetingCommand(
            operation="create",
            patch=MeetingPatch(start_at=datetime(2026, 8, 15, 15, tzinfo=SHANGHAI)),
        ),
    )

    assert updated.draft.start_at == datetime(2026, 8, 15, 15, tzinfo=SHANGHAI)
    assert updated.draft.end_at == datetime(2026, 8, 15, 16, tzinfo=SHANGHAI)
