from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.agent.interpreter import MeetingCommand
from app.agent.service import AssistantReply, ChatContext, MeetingAssistant
from app.domain.models import Actor, MeetingDraft, MeetingPatch
from app.domain.room_ranking import RankedRoom, Room, RoomBusyInterval, rank_rooms
from app.integrations.errors import IntegrationError
from app.integrations.models import FreeBusyResponse, UserBusyIntervals
from app.repositories.meetings import MeetingRepository

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 14, 9, 0, tzinfo=SHANGHAI)


class FreeCalendar:
    async def freebusy(self, request):
        return FreeBusyResponse(
            busy_by_user=tuple(
                UserBusyIntervals(attendee_id=value) for value in request.attendee_ids
            )
        )


class AvailableRooms:
    async def search(self, topic, attendee_count, required_features, start_at, end_at):
        del topic, attendee_count, required_features, start_at, end_at
        return (
            RankedRoom(
                room=Room(id="room-orchid", name="Orchid", capacity=6, features=("whiteboard",)),
                score=3,
                reason="容量和设备匹配",
            ),
            RankedRoom(
                room=Room(id="room-bamboo", name="Bamboo", capacity=12),
                score=1,
                reason="容量匹配",
            ),
        )


class SlotAwareRooms:
    def __init__(self) -> None:
        self._rooms = (
            Room(
                id="room-orchid",
                name="Orchid",
                capacity=6,
                features=("whiteboard",),
                busy_intervals=(
                    RoomBusyInterval(
                        start_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI),
                        end_at=datetime(2026, 8, 15, 17, tzinfo=SHANGHAI),
                    ),
                ),
            ),
            Room(
                id="room-bamboo",
                name="Bamboo",
                capacity=12,
                features=("whiteboard",),
            ),
        )

    async def search(self, topic, attendee_count, required_features, start_at, end_at):
        return rank_rooms(
            self._rooms,
            topic,
            attendee_count,
            required_features,
            start_at,
            end_at,
        )


class BrokenCalendar:
    async def freebusy(self, request):
        del request
        raise IntegrationError("calendar unavailable")


class UnsafeInterpreter:
    async def interpret(self, message, context):
        del message, context
        return MeetingCommand(operation="unsafe")


class ScriptedInterpreter:
    def __init__(self, *commands: MeetingCommand) -> None:
        self._commands = iter(commands)

    async def interpret(self, message, context):
        del message, context
        return next(self._commands)


@pytest.fixture
def repository(tmp_path: Path) -> MeetingRepository:
    return MeetingRepository(tmp_path / "meetings.db")


def assistant(repository, calendar=None) -> MeetingAssistant:
    return MeetingAssistant(
        repository=repository,
        calendar=calendar or FreeCalendar(),
        rooms=AvailableRooms(),
        clock=lambda: NOW,
    )


def scripted_assistant(repository, *commands: MeetingCommand) -> MeetingAssistant:
    return MeetingAssistant(
        repository=repository,
        calendar=FreeCalendar(),
        rooms=AvailableRooms(),
        clock=lambda: NOW,
        interpreter=ScriptedInterpreter(*commands),
    )


def chat(actor_id="alice", conversation_id="chat-1", request_id="request-1") -> ChatContext:
    return ChatContext(
        actor=Actor(id=actor_id, display_name=actor_id.title()),
        conversation_id=conversation_id,
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_incomplete_create_collects_fields_then_previews_before_explicit_confirmation(
    repository,
) -> None:
    service = assistant(repository)

    incomplete = await service.handle(chat(), "创建设计评审会议")
    preview = await service.handle(
        chat(request_id="request-2"), "明天下午3点，持续1小时，参会人 bob，需要白板"
    )

    assert incomplete.status == "collecting"
    assert "时间" in incomplete.reply and "参会人" in incomplete.reply
    assert preview.status == "needs_confirmation"
    assert preview.needs_confirmation is True
    assert preview.meeting_draft.start_at == datetime(2026, 8, 15, 15, 0, tzinfo=SHANGHAI)
    assert preview.meeting_draft.room_id == "room-orchid"
    assert repository.list_for_actor(chat().actor) == []

    created = await service.handle(chat(request_id="request-3"), "确认")
    persisted = repository.list_for_actor(chat().actor)[0]

    assert created.status == "done"
    assert created.needs_confirmation is False
    assert created.meeting_draft == MeetingDraft(
        **persisted.model_dump(include=set(MeetingDraft.model_fields))
    )
    assert len(repository.list_for_actor(chat().actor)) == 1


@pytest.mark.asyncio
async def test_editing_pending_create_cannot_be_redirected_to_existing_meeting(repository) -> None:
    existing = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 15, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI),
            attendee_ids=("jack", "bob", "alice"),
            required_features=("whiteboard",),
        ),
        "seed-existing",
    )
    service = scripted_assistant(
        repository,
        MeetingCommand(operation="create", patch=MeetingPatch(title="开发会议")),
        MeetingCommand(
            operation="create",
            patch=MeetingPatch(
                start_at=datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 15, 17, 30, tzinfo=SHANGHAI),
                attendee_ids=("jack", "bob", "alice"),
                required_features=("display",),
            ),
        ),
        # 模拟真实模型误把“再加 adam”分类为 update；状态机必须以待确认动作 create 为准。
        MeetingCommand(
            operation="update",
            patch=MeetingPatch(attendee_ids=("jack", "bob", "alice", "adam")),
        ),
        MeetingCommand(operation="confirm"),
    )

    await service.handle(chat(), "再创建一个开发会议")
    first_preview = await service.handle(
        chat(request_id="request-2"),
        "明天下午4点半到5点半，参会人：jack、bob、alice，需要投影仪",
    )
    amended_preview = await service.handle(chat(request_id="request-3"), "参会人再加一个adam")
    confirmed = await service.handle(chat(request_id="request-4"), "确认")

    meetings = repository.list_for_actor(chat().actor)
    persisted_existing = repository.find_visible(chat().actor, existing.id)
    created = next(meeting for meeting in meetings if meeting.title == "开发会议")

    assert first_preview.status == "needs_confirmation"
    assert amended_preview.status == "needs_confirmation"
    assert amended_preview.meeting_draft.title == "开发会议"
    assert amended_preview.meeting_draft.attendee_ids == ("jack", "bob", "alice", "adam")
    assert amended_preview.meeting_draft.required_features == ("display",)
    assert confirmed.status == "done"
    assert len(meetings) == 2
    assert created.start_at == datetime(2026, 8, 15, 16, 30, tzinfo=SHANGHAI)
    assert persisted_existing.title == "设计评审"
    assert persisted_existing.attendee_ids == ("jack", "bob", "alice")


@pytest.mark.asyncio
async def test_editing_pending_update_cannot_turn_into_a_new_create(repository) -> None:
    meeting = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-update",
    )
    service = scripted_assistant(
        repository,
        MeetingCommand(operation="query"),
        MeetingCommand(
            operation="update",
            patch=MeetingPatch(start_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI)),
        ),
        # 模拟模型把后续字段补充误分类为 create；状态机必须继续原 update。
        MeetingCommand(
            operation="create",
            patch=MeetingPatch(attendee_ids=("bob", "adam")),
        ),
        MeetingCommand(operation="confirm"),
    )

    await service.handle(chat(), "查询我的会议")
    await service.handle(chat(request_id="request-2"), "把会议改到下午4点")
    amended_preview = await service.handle(chat(request_id="request-3"), "参会人再加 adam")
    confirmed = await service.handle(chat(request_id="request-4"), "确认")
    persisted = repository.find_visible(chat().actor, meeting.id)

    assert amended_preview.status == "needs_confirmation"
    assert amended_preview.meeting_draft.title == "设计评审"
    assert amended_preview.meeting_draft.start_at.hour == 16
    assert amended_preview.meeting_draft.attendee_ids == ("bob", "adam")
    assert confirmed.status == "done"
    assert len(repository.list_for_actor(chat().actor)) == 1
    assert persisted.start_at.hour == 16
    assert persisted.attendee_ids == ("bob", "adam")


@pytest.mark.asyncio
async def test_query_invalidates_an_unconfirmed_preview(repository) -> None:
    service = scripted_assistant(
        repository,
        MeetingCommand(
            operation="create",
            patch=MeetingPatch(
                title="开发会议",
                start_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 15, 17, tzinfo=SHANGHAI),
                attendee_ids=("bob",),
            ),
        ),
        MeetingCommand(operation="query"),
        MeetingCommand(operation="confirm"),
    )

    preview = await service.handle(chat(), "创建开发会议")
    queried = await service.handle(chat(request_id="request-2"), "查询我的会议")
    stale_confirmation = await service.handle(chat(request_id="request-3"), "确认")

    assert preview.status == "needs_confirmation"
    assert queried.status == "done"
    assert stale_confirmation.status == "rejected"
    assert "确认已失效" in stale_confirmation.reply
    assert repository.list_for_actor(chat().actor) == []


@pytest.mark.asyncio
async def test_saved_meeting_can_be_updated_without_querying_again(repository) -> None:
    service = assistant(repository)

    await service.handle(chat(), "创建设计评审会议")
    await service.handle(chat(request_id="request-2"), "明天下午3点，持续1小时，参会人 bob")
    await service.handle(chat(request_id="request-3"), "确认")
    preview = await service.handle(chat(request_id="request-4"), "把时间改到下午4点")

    assert preview.status == "needs_confirmation"
    assert preview.meeting_draft.start_at == datetime(2026, 8, 15, 16, tzinfo=SHANGHAI)
    assert preview.meeting_draft.end_at == datetime(2026, 8, 15, 17, tzinfo=SHANGHAI)


@pytest.mark.asyncio
async def test_query_visibility_and_update_by_unique_conversation_context(repository) -> None:
    visible = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-visible",
    )
    repository.create(
        "mallory",
        MeetingDraft(
            title="秘密会议",
            start_at=datetime(2026, 8, 15, 12, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 13, tzinfo=SHANGHAI),
            attendee_ids=("eve",),
        ),
        "seed-hidden",
    )
    service = assistant(repository)

    queried = await service.handle(chat(), "查询我的会议")
    preview = await service.handle(chat(request_id="request-2"), "把刚才那个会改到明天下午4点")

    assert queried.status == "done"
    assert "设计评审" in queried.reply
    assert "秘密会议" not in queried.reply
    assert preview.status == "needs_confirmation"
    assert repository.find_visible(chat().actor, visible.id).start_at.hour == 10

    updated = await service.handle(chat(request_id="request-3"), "确认")

    assert updated.status == "done"
    assert updated.needs_confirmation is False
    assert updated.meeting_draft.title == "设计评审"
    assert updated.meeting_draft.start_at.hour == 16
    assert updated.meeting_draft.end_at.hour == 17
    assert repository.find_visible(chat().actor, visible.id).start_at.hour == 16


@pytest.mark.asyncio
async def test_update_preview_replaces_room_that_is_busy_in_the_new_slot(repository) -> None:
    meeting = repository.create(
        "alice",
        MeetingDraft(
            title="Design review",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
            room_id="room-orchid",
            required_features=("whiteboard",),
        ),
        "seed-room-revalidation",
    )
    service = MeetingAssistant(
        repository=repository,
        calendar=FreeCalendar(),
        rooms=SlotAwareRooms(),
        clock=lambda: NOW,
    )
    await service.handle(chat(), "查询我的会议")

    preview = await service.handle(chat(request_id="request-2"), "把刚才那个会改到明天下午4点")
    confirmed = await service.handle(chat(request_id="request-3"), "确认")
    persisted = repository.find_visible(chat().actor, meeting.id)

    assert preview.status == "needs_confirmation"
    assert preview.meeting_draft.room_id == "room-bamboo"
    assert confirmed.status == "done"
    assert persisted.room_id == "room-bamboo"


@pytest.mark.asyncio
async def test_update_confirmation_rejects_preview_after_external_version_change(
    repository,
) -> None:
    meeting = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-visible",
    )
    service = assistant(repository)
    await service.handle(chat(), "查询我的会议")
    preview = await service.handle(chat(request_id="request-2"), "把刚才那个会改到明天下午4点")
    repository.update("alice", meeting.id, MeetingPatch(title="外部已修改"), expected_version=1)

    result = await service.handle(chat(request_id="request-3"), "确认")
    persisted = repository.find_visible(chat().actor, meeting.id)

    assert preview.status == "needs_confirmation"
    assert result.status == "rejected"
    assert "重新预览" in result.reply
    assert persisted.title == "外部已修改"
    assert persisted.start_at.hour == 10
    assert persisted.version == 2


@pytest.mark.asyncio
async def test_update_patch_does_not_inherit_fields_from_prior_create_intent(repository) -> None:
    meeting = repository.create(
        "alice",
        MeetingDraft(
            title="会议 B",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
            room_id="room-bamboo",
        ),
        "seed-b",
    )
    service = assistant(repository)
    await service.handle(chat(), "创建会议 A会议")
    await service.handle(
        chat(request_id="request-2"),
        "明天下午3点，持续1小时，参会人 carol，需要白板",
    )
    await service.handle(chat(request_id="request-3"), "查询我的会议")

    preview = await service.handle(chat(request_id="request-4"), "把刚才那个会改到明天下午4点")
    result = await service.handle(chat(request_id="request-5"), "确认")
    persisted = repository.find_visible(chat().actor, meeting.id)

    assert preview.status == "needs_confirmation"
    assert result.status == "done"
    assert persisted.title == "会议 B"
    assert persisted.attendee_ids == ("bob",)
    assert persisted.room_id == "room-bamboo"
    assert persisted.start_at.hour == 16


@pytest.mark.asyncio
async def test_query_with_multiple_results_requires_unique_meeting_resolution(repository) -> None:
    for index, hour in enumerate((10, 12), start=1):
        repository.create(
            "alice",
            MeetingDraft(
                title=f"评审 {index}",
                start_at=datetime(2026, 8, 15, hour, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 15, hour + 1, tzinfo=SHANGHAI),
                attendee_ids=("bob",),
            ),
            f"seed-{index}",
        )
    service = assistant(repository)

    await service.handle(chat(), "查询我的会议")
    reply = await service.handle(chat(request_id="request-2"), "把刚才那个会改到明天下午4点")

    assert reply.status == "needs_clarification"
    assert "多个" in reply.reply


@pytest.mark.asyncio
async def test_select_first_candidate_continues_pending_update(repository) -> None:
    first = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-first",
    )
    second = repository.create(
        "alice",
        MeetingDraft(
            title="预算评审",
            start_at=datetime(2026, 8, 15, 12, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 13, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-second",
    )
    service = assistant(repository)

    queried = await service.handle(chat(), "查询我的会议")
    clarify = await service.handle(chat(request_id="request-2"), "把会议改到明天下午4点")
    preview = await service.handle(chat(request_id="request-3"), "第一个")
    confirmed = await service.handle(chat(request_id="request-4"), "确认")

    assert "1." in queried.reply and "2." in queried.reply
    assert clarify.status == "needs_clarification"
    assert preview.status == "needs_confirmation"
    assert confirmed.status == "done"
    assert repository.find_visible(chat().actor, first.id).start_at.hour == 16
    assert repository.find_visible(chat().actor, second.id).start_at.hour == 12


@pytest.mark.asyncio
async def test_state_is_isolated_by_conversation_and_actor(repository) -> None:
    service = assistant(repository)

    await service.handle(chat(actor_id="alice", conversation_id="shared"), "创建设计评审会议")
    other_actor = await service.handle(
        chat(actor_id="bob", conversation_id="shared", request_id="request-2"),
        "明天下午3点，持续1小时，参会人 carol",
    )
    other_conversation = await service.handle(
        chat(actor_id="alice", conversation_id="other", request_id="request-3"),
        "明天下午3点，持续1小时，参会人 carol",
    )

    assert other_actor.status == "collecting" and "主题" in other_actor.reply
    assert other_conversation.status == "collecting" and "主题" in other_conversation.reply


@pytest.mark.asyncio
async def test_unsafe_request_is_rejected_before_tools_and_produces_zero_writes(repository) -> None:
    service = assistant(repository, calendar=BrokenCalendar())

    result = await service.handle(chat(), "删除所有人的会议")

    assert result.status == "rejected"
    assert repository.list_for_actor(chat().actor) == []


@pytest.mark.asyncio
async def test_interpreter_unsafe_command_is_rejected_even_when_text_precheck_misses(
    repository,
) -> None:
    service = MeetingAssistant(
        repository=repository,
        calendar=BrokenCalendar(),
        rooms=AvailableRooms(),
        clock=lambda: NOW,
        interpreter=UnsafeInterpreter(),
    )

    result = await service.handle(chat(), "执行不受支持的操作")

    assert result.status == "rejected"
    assert repository.list_for_actor(chat().actor) == []


@pytest.mark.asyncio
async def test_stale_or_cancelled_confirmation_produces_zero_writes(repository) -> None:
    service = assistant(repository)
    await service.handle(chat(), "创建设计评审会议")
    await service.handle(chat(request_id="request-2"), "明天下午3点，持续1小时，参会人 bob")

    cancelled = await service.handle(chat(request_id="request-3"), "取消")
    stale = await service.handle(chat(request_id="request-4"), "确认")

    assert cancelled.status == "done"
    assert stale.status == "rejected"
    assert repository.list_for_actor(chat().actor) == []


@pytest.mark.asyncio
async def test_integration_failure_is_controlled_and_never_writes(repository) -> None:
    service = assistant(repository, calendar=BrokenCalendar())
    await service.handle(chat(), "创建设计评审会议")

    result = await service.handle(
        chat(request_id="request-2"),
        "明天下午3点，持续1小时，参会人 bob",
    )

    assert isinstance(result, AssistantReply)
    assert result.status == "rejected"
    assert "暂时不可用" in result.reply
    assert repository.list_for_actor(chat().actor) == []


@pytest.mark.asyncio
async def test_exact_attendee_availability_query_returns_calendar_result(repository) -> None:
    service = assistant(repository)

    result = await service.handle(chat(), "查询 bob 明天下午3点是否空闲")

    assert result.status == "done"
    assert "bob" in result.reply
    assert "均空闲" in result.reply
    assert "会议" not in result.reply


@pytest.mark.asyncio
async def test_common_free_time_query_returns_free_slots(repository) -> None:
    service = assistant(repository)

    result = await service.handle(chat(), "查询 bob 和 carol 明天下午什么时候有空")

    assert result.status == "done"
    assert "共同空闲时间" in result.reply
    assert "13:00-18:00" in result.reply
