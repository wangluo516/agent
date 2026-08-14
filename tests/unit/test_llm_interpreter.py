from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.interpreter import AvailabilityQuery, InterpretContext, MeetingCommand
from app.agent.llm_interpreter import LLMInterpreter
from app.domain.models import ConversationState, MeetingCandidate, MeetingPatch, PendingAction

SHANGHAI = ZoneInfo("Asia/Shanghai")


class CapturingStructuredModel:
    def __init__(self) -> None:
        self.prompt = ""

    async def ainvoke(self, prompt: str) -> MeetingCommand:
        self.prompt = prompt
        return MeetingCommand(operation="unknown")


class ReturningStructuredModel:
    def __init__(self, result) -> None:
        self.result = result
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str):
        self.prompts.append(prompt)
        return self.result


def test_llm_interpreter_uses_function_calling_for_structured_output(monkeypatch) -> None:
    captured = {"schemas": [], "structured_outputs": []}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            captured["schemas"].append(schema)
            captured["structured_outputs"].append(kwargs)
            return CapturingStructuredModel()

    monkeypatch.setenv("MEETING_ASSISTANT_LLM_API_KEY", "test-key")
    monkeypatch.setattr("app.agent.llm_interpreter.ChatOpenAI", FakeChatOpenAI)

    LLMInterpreter(model="deepseek-v4-flash", base_url="https://api.deepseek.com")

    assert captured["schemas"] == [MeetingCommand, MeetingPatch]
    assert captured["structured_outputs"] == [
        {"method": "function_calling"},
        {"method": "function_calling"},
    ]
    assert captured["init"]["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_llm_prompt_contains_selected_meeting_and_candidates() -> None:
    candidate = MeetingCandidate(
        id="meeting-1",
        title="设计评审",
        start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
    )
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="chat-1",
            selected_meeting_id=candidate.id,
            meeting_candidates=(candidate,),
        ),
    )
    model = CapturingStructuredModel()
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = model

    await interpreter.interpret("把时间改到下午3点", context)

    assert "meeting-1" in model.prompt
    assert "设计评审" in model.prompt
    assert "2026-08-15T10:00:00+08:00" in model.prompt


@pytest.mark.asyncio
async def test_llm_prompt_limits_delete_target_and_keeps_authorization_server_side() -> None:
    candidate = MeetingCandidate(
        id="meeting-1",
        title="设计评审",
        start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
    )
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="delete-chat",
            meeting_candidates=(candidate,),
            status="done",
        ),
    )
    model = CapturingStructuredModel()
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = model

    await interpreter.interpret("删除第一个会议", context)

    assert "delete" in model.prompt
    assert "meeting_id" in model.prompt
    assert "候选会议" in model.prompt
    assert "权限" in model.prompt
    assert "批量删除" in model.prompt
    assert "operation=unsafe" in model.prompt


@pytest.mark.asyncio
async def test_collecting_create_routes_field_only_follow_up_to_patch_extractor() -> None:
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="chat-1",
            draft=MeetingPatch(title="开发会议"),
            status="collecting",
        ),
    )
    command_model = ReturningStructuredModel(
        MeetingCommand(
            operation="availability",
            availability=AvailabilityQuery(
                attendee_ids=("jack", "bob", "alice"),
                window_start=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
                window_end=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
            ),
        )
    )
    patch_model = ReturningStructuredModel(
        MeetingPatch(
            attendee_ids=("jack", "bob", "alice"),
        )
    )
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = command_model
    interpreter._patch_model = patch_model

    command = await interpreter.interpret(
        "明天下午4点半到5点半，参会人：jack、bob、alice，需要投影仪",
        context,
    )

    assert command == MeetingCommand(
        operation="create",
        patch=MeetingPatch(
            start_at=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
            attendee_ids=("jack", "bob", "alice"),
            required_features=("display",),
        ),
    )
    assert command_model.prompts == []
    assert len(patch_model.prompts) == 1


@pytest.mark.asyncio
async def test_explicit_availability_query_can_interrupt_a_collecting_draft() -> None:
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="chat-1",
            draft=MeetingPatch(title="开发会议"),
            status="collecting",
        ),
    )
    expected = MeetingCommand(
        operation="availability",
        availability=AvailabilityQuery(
            attendee_ids=("bob",),
            window_start=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
            window_end=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
        ),
    )
    command_model = ReturningStructuredModel(expected)
    patch_model = ReturningStructuredModel(MeetingPatch())
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = command_model
    interpreter._patch_model = patch_model

    command = await interpreter.interpret("查询 bob 明天下午4点半是否空闲", context)

    assert command == expected
    assert len(command_model.prompts) == 1
    assert patch_model.prompts == []


@pytest.mark.asyncio
async def test_delete_synonym_interrupts_collecting_draft_and_uses_command_model() -> None:
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="delete-interrupt",
            draft=MeetingPatch(title="开发会议"),
            status="collecting",
        ),
    )
    expected = MeetingCommand(operation="delete")
    command_model = ReturningStructuredModel(expected)
    patch_model = ReturningStructuredModel(MeetingPatch())
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = command_model
    interpreter._patch_model = patch_model

    command = await interpreter.interpret("删掉这个会议", context)

    assert command == expected
    assert len(command_model.prompts) == 1
    assert patch_model.prompts == []


@pytest.mark.asyncio
async def test_collecting_update_without_date_preserves_selected_meeting_day() -> None:
    candidate = MeetingCandidate(
        id="meeting-1",
        title="设计评审",
        start_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 20, 11, tzinfo=SHANGHAI),
    )
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="chat-1",
            draft=MeetingPatch(title="设计评审"),
            selected_meeting_id=candidate.id,
            meeting_candidates=(candidate,),
            status="collecting",
        ),
    )
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = ReturningStructuredModel(MeetingCommand(operation="unknown"))
    interpreter._patch_model = ReturningStructuredModel(MeetingPatch())

    command = await interpreter.interpret("下午3点到4点", context)

    assert command.operation == "update"
    assert command.patch.start_at == datetime(2026, 8, 20, 15, tzinfo=SHANGHAI)
    assert command.patch.end_at == datetime(2026, 8, 20, 16, tzinfo=SHANGHAI)


@pytest.mark.asyncio
async def test_pending_create_attendee_addition_keeps_create_and_merges_attendees() -> None:
    context = InterpretContext(
        actor_id="alice",
        now=datetime(2026, 8, 14, 9, tzinfo=SHANGHAI),
        state=ConversationState(
            actor_id="alice",
            conversation_id="chat-1",
            draft=MeetingPatch(
                title="开发会议",
                start_at=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
                attendee_ids=("jack", "bob", "alice"),
                required_features=("display",),
                room_id="room-orchid",
            ),
            pending_action=PendingAction(action="create", confirmation_hash="old-hash"),
            status="needs_confirmation",
        ),
    )
    command_model = ReturningStructuredModel(
        MeetingCommand(operation="update", patch=MeetingPatch(attendee_ids=("adam",)))
    )
    patch_model = ReturningStructuredModel(MeetingPatch(attendee_ids=("adam",)))
    interpreter = LLMInterpreter.__new__(LLMInterpreter)
    interpreter._model = command_model
    interpreter._patch_model = patch_model

    command = await interpreter.interpret("参会人再加一个adam", context)

    assert command.operation == "create"
    assert command.patch.attendee_ids == ("jack", "bob", "alice", "adam")
    assert command_model.prompts == []
    assert len(patch_model.prompts) == 1
