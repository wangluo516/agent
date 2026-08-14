from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.interpreter import InterpretContext, MeetingCommand
from app.agent.llm_interpreter import LLMInterpreter
from app.domain.models import ConversationState, MeetingCandidate

SHANGHAI = ZoneInfo("Asia/Shanghai")


class CapturingStructuredModel:
    def __init__(self) -> None:
        self.prompt = ""

    async def ainvoke(self, prompt: str) -> MeetingCommand:
        self.prompt = prompt
        return MeetingCommand(operation="unknown")


def test_llm_interpreter_uses_function_calling_for_structured_output(monkeypatch) -> None:
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["structured_output"] = kwargs
            return CapturingStructuredModel()

    monkeypatch.setenv("MEETING_ASSISTANT_LLM_API_KEY", "test-key")
    monkeypatch.setattr("app.agent.llm_interpreter.ChatOpenAI", FakeChatOpenAI)

    LLMInterpreter(model="deepseek-v4-flash", base_url="https://api.deepseek.com")

    assert captured["schema"] is MeetingCommand
    assert captured["structured_output"] == {"method": "function_calling"}
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
