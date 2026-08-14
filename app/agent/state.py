from app.agent.interpreter import MeetingCommand
from app.domain.models import ConversationState


def reduce_command(state: ConversationState, command: MeetingCommand) -> ConversationState:
    if command.operation not in {"create", "update"}:
        return state
    if command.operation == "update":
        pending_update = state.pending_action and state.pending_action.action == "update"
        target_id = (
            command.meeting_id
            or (state.pending_action.meeting_id if pending_update else None)
            or state.selected_meeting_id
        )
        if pending_update:
            updated = state.with_draft(command.patch).model_copy(
                update={"selected_meeting_id": target_id}
            )
        else:
            updated = state.model_copy(
                update={"draft": command.patch, "selected_meeting_id": target_id}
            )
    elif state.selected_meeting_id or (
        state.pending_action and state.pending_action.action != "create"
    ):
        updated = state.model_copy(update={"draft": command.patch, "selected_meeting_id": None})
    else:
        updated = state.with_draft(command.patch)
    return updated.model_copy(update={"pending_action": None, "status": "collecting"})
