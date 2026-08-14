from app.agent.interpreter import MeetingCommand
from app.agent.state import reduce_command
from app.domain.models import ConversationState, MeetingPatch, PendingAction


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
