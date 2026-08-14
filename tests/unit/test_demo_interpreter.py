from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.demo_interpreter import DemoInterpreter
from app.agent.interpreter import InterpretContext
from app.domain.models import ConversationState, MeetingPatch

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 14, 9, 0, tzinfo=SHANGHAI)


def context(draft: MeetingPatch | None = None) -> InterpretContext:
    return InterpretContext(
        actor_id="alice",
        now=NOW,
        state=ConversationState(actor_id="alice", conversation_id="chat-1", draft=draft),
    )


@pytest.mark.asyncio
async def test_interprets_incomplete_create_without_inventing_missing_fields() -> None:
    command = await DemoInterpreter().interpret("创建设计评审会议", context())

    assert command.operation == "create"
    assert command.patch == MeetingPatch(title="设计评审")


@pytest.mark.asyncio
async def test_interprets_follow_up_relative_time_and_attendees_using_injected_now() -> None:
    command = await DemoInterpreter().interpret(
        "明天下午3点，持续1小时，参会人 bob 和 carol，需要白板",
        context(MeetingPatch(title="设计评审")),
    )

    assert command.operation == "create"
    assert command.patch == MeetingPatch(
        start_at=datetime(2026, 8, 15, 15, 0, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 15, 16, 0, tzinfo=SHANGHAI),
        attendee_ids=("bob", "carol"),
        required_features=("whiteboard",),
    )


@pytest.mark.asyncio
async def test_interprets_query_update_confirmation_and_cancellation() -> None:
    interpreter = DemoInterpreter()

    assert (await interpreter.interpret("查询我的会议", context())).operation == "query"
    update = await interpreter.interpret("把刚才那个会改到明天下午4点", context())
    assert update.operation == "update"
    assert update.patch.start_at == datetime(2026, 8, 15, 16, 0, tzinfo=SHANGHAI)
    assert (await interpreter.interpret("确认", context())).operation == "confirm"
    assert (await interpreter.interpret("取消", context())).operation == "cancel"


@pytest.mark.asyncio
async def test_interprets_exact_attendee_availability_query() -> None:
    command = await DemoInterpreter().interpret("查询 bob 明天下午3点是否空闲", context())

    assert command.operation == "availability"
    assert command.availability is not None
    assert command.availability.attendee_ids == ("bob",)
    assert command.availability.window_start == datetime(2026, 8, 15, 15, 0, tzinfo=SHANGHAI)
    assert command.availability.window_end == datetime(2026, 8, 15, 16, 0, tzinfo=SHANGHAI)


@pytest.mark.asyncio
async def test_interprets_common_free_time_query_for_an_afternoon() -> None:
    command = await DemoInterpreter().interpret("查询 bob 和 carol 明天下午什么时候有空", context())

    assert command.operation == "availability"
    assert command.availability is not None
    assert command.availability.attendee_ids == ("bob", "carol")
    assert command.availability.window_start == datetime(2026, 8, 15, 13, 0, tzinfo=SHANGHAI)
    assert command.availability.window_end == datetime(2026, 8, 15, 18, 0, tzinfo=SHANGHAI)
