from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import Field

from app.agent.demo_interpreter import DemoInterpreter
from app.agent.graph import WorkflowData, build_workflow
from app.agent.interpreter import InterpretContext, Interpreter, MeetingCommand
from app.agent.state import reduce_command
from app.agent.tools import CalendarPort, MeetingTools, RepositoryPort, RoomPort
from app.domain.availability import find_common_free_slots
from app.domain.errors import AttendeeBusyError, ConflictError, DomainError
from app.domain.models import (
    Actor,
    ConversationState,
    ImmutableModel,
    MeetingCandidate,
    MeetingDraft,
    MeetingPatch,
    PendingAction,
)
from app.domain.policies import classify_unsafe_request, confirmation_hash
from app.integrations.errors import IntegrationError
from app.integrations.models import FreeBusyRequest


class ChatContext(ImmutableModel):
    actor: Actor
    conversation_id: str = Field(min_length=1)
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)


class AssistantReply(ImmutableModel):
    reply: str
    status: str
    meeting_draft: MeetingDraft | MeetingPatch | None = None
    needs_confirmation: bool = False
    request_id: str


class UpdateSnapshot(ImmutableModel):
    meeting_id: str
    expected_version: int = Field(ge=1)
    patch: MeetingPatch


class MeetingAssistant:
    def __init__(
        self,
        repository: RepositoryPort,
        calendar: CalendarPort,
        rooms: RoomPort,
        clock: Callable[[], datetime],
        interpreter: Interpreter | None = None,
    ) -> None:
        self._tools = MeetingTools(repository, calendar, rooms)
        self._clock = clock
        self._interpreter = interpreter or DemoInterpreter()
        self._states: dict[tuple[str, str], ConversationState] = {}
        self._update_snapshots: dict[tuple[str, str], UpdateSnapshot] = {}
        self._graph = build_workflow(self._nodes())

    async def handle(self, context: ChatContext, message: str) -> AssistantReply:
        key = (context.conversation_id, context.actor.id)
        state = self._states.get(
            key,
            ConversationState(actor_id=context.actor.id, conversation_id=context.conversation_id),
        )
        try:
            result = await self._graph.ainvoke(
                {"context": context, "message": message, "state": state}
            )
        except AttendeeBusyError as error:
            rejected = state.model_copy(update={"status": "rejected", "pending_action": None})
            attendees = ", ".join(error.attendee_ids)
            reply = self._reply(
                context, rejected, f"参会人 {attendees} 在该时间段忙碌，请调整时间。"
            )
            result = {"state": rejected, "reply": reply}
        except ConflictError:
            rejected = state.model_copy(update={"status": "rejected", "pending_action": None})
            reply = self._reply(context, rejected, "预览已过期，请重新预览。")
            result = {"state": rejected, "reply": reply}
            self._discard_snapshot(key)
        except (DomainError, IntegrationError, ValueError):
            rejected = state.model_copy(update={"status": "rejected", "pending_action": None})
            reply = self._reply(context, rejected, "会议服务暂时不可用，请稍后重试。")
            result = {"state": rejected, "reply": reply}
        self._states = {**self._states, key: result["state"]}
        return result["reply"]

    def _nodes(self):
        return {
            "precheck": self._precheck,
            "interpret": self._interpret,
            "reduce_resolve": self._reduce_resolve,
            "validate": self._validate,
            "query_integrations": self._query_integrations,
            "preview": self._preview,
            "confirm": self._confirm,
            "execute": self._execute,
        }

    async def _precheck(self, data: WorkflowData) -> dict:
        reason = classify_unsafe_request(data["message"])
        if not reason:
            return {}
        state = data["state"].model_copy(update={"status": "rejected", "pending_action": None})
        return {
            "state": state,
            "reply": self._reply(data["context"], state, f"请求已拒绝：{reason}。"),
        }

    async def _interpret(self, data: WorkflowData) -> dict:
        if data.get("reply"):
            return {}
        context = InterpretContext(
            actor_id=data["context"].actor.id,
            now=self._clock(),
            state=data["state"],
        )
        return {"command": await self._interpreter.interpret(data["message"], context)}

    async def _reduce_resolve(self, data: WorkflowData) -> dict:
        if data.get("reply"):
            return {}
        command = data["command"]
        if command.operation == "select":
            candidate = next(
                (
                    meeting
                    for meeting in data["state"].meeting_candidates
                    if meeting.id == command.meeting_id
                ),
                None,
            )
            if candidate is None or data["state"].draft is None:
                state = data["state"].model_copy(update={"status": "needs_clarification"})
                return {
                    "state": state,
                    "reply": self._reply(
                        data["context"], state, "没有匹配到唯一会议，请重新选择。"
                    ),
                }
            if self._tools.repository.find_visible(data["context"].actor, candidate.id) is None:
                state = data["state"].model_copy(update={"status": "rejected"})
                return {
                    "state": state,
                    "reply": self._reply(data["context"], state, "所选会议已不可用。"),
                }
            state = data["state"].model_copy(
                update={"selected_meeting_id": candidate.id, "status": "collecting"}
            )
            return {
                "state": state,
                "command": MeetingCommand(
                    operation="update", patch=state.draft, meeting_id=candidate.id
                ),
            }
        state = reduce_command(data["state"], command)
        if command.operation in {"create", "update"}:
            self._discard_snapshot(self._state_key(data["context"]))
        if command.operation != "update" or state.selected_meeting_id:
            return {"state": state}
        meetings = self._tools.query(data["context"].actor)
        if len(meetings) == 1:
            return {"state": state.model_copy(update={"selected_meeting_id": meetings[0].id})}
        state = state.model_copy(update={"meeting_candidates": self._candidates(meetings)})
        status = "needs_clarification"
        text = "找到多个会议，请先明确要修改哪一个。" if meetings else "没有找到可修改的会议。"
        state = state.model_copy(update={"status": status})
        return {"state": state, "reply": self._reply(data["context"], state, text)}

    async def _validate(self, data: WorkflowData) -> dict:
        if data.get("reply"):
            return {}
        command, state = data["command"], data["state"]
        if command.operation in {"confirm", "cancel", "query", "update"}:
            return {}
        if command.operation == "availability":
            query = command.availability
            missing: list[str] = []
            if query is None or not query.attendee_ids:
                missing.append("参会人")
            if query is None or query.window_start is None or query.window_end is None:
                missing.append("查询日期和时间")
            if not missing:
                return {}
            state = state.model_copy(update={"status": "needs_clarification"})
            return {
                "state": state,
                "reply": self._reply(data["context"], state, f"还需要提供：{'、'.join(missing)}。"),
            }
        if command.operation == "unsafe":
            state = state.model_copy(update={"status": "rejected", "pending_action": None})
            return {
                "state": state,
                "reply": self._reply(data["context"], state, "请求已拒绝：不支持该操作。"),
            }
        if command.operation == "unknown":
            state = state.model_copy(update={"status": "needs_clarification"})
            return {
                "state": state,
                "reply": self._reply(data["context"], state, "请说明要创建、查询还是修改会议。"),
            }
        missing = self._missing_fields(state.draft)
        if missing:
            state = state.model_copy(update={"status": "collecting"})
            return {
                "state": state,
                "reply": self._reply(
                    data["context"], state, f"还需要提供：{'、'.join(missing)}。", state.draft
                ),
            }
        return {}

    async def _query_integrations(self, data: WorkflowData) -> dict:
        if data.get("reply"):
            return {}
        command, state, context = data["command"], data["state"], data["context"]
        if command.operation == "availability":
            query = command.availability
            response = await self._tools.availability(
                FreeBusyRequest(
                    attendee_ids=query.attendee_ids,
                    window_start=query.window_start,
                    window_end=query.window_end,
                )
            )
            busy_attendees = tuple(
                attendee_id
                for attendee_id in query.attendee_ids
                if response.intervals_for(attendee_id)
            )
            state = state.model_copy(
                update={
                    "status": "done",
                    "last_tool_results": (response.model_dump(mode="json"),),
                }
            )
            if query.window_end - query.window_start > timedelta(minutes=query.duration_minutes):
                free_slots = find_common_free_slots(
                    {
                        attendee_id: tuple(
                            (interval.start_at, interval.end_at)
                            for interval in response.intervals_for(attendee_id)
                        )
                        for attendee_id in query.attendee_ids
                    },
                    query.window_start,
                    query.window_end,
                    query.duration_minutes,
                )
                if free_slots:
                    slots = "；".join(
                        f"{start:%m月%d日 %H:%M}-{end:%H:%M}" for start, end in free_slots
                    )
                    text = f"共同空闲时间：{slots}。"
                else:
                    text = "该时间窗口内没有满足时长要求的共同空闲时间。"
                return {"state": state, "reply": self._reply(context, state, text)}
            if busy_attendees:
                text = f"参会人 {', '.join(busy_attendees)} 在该时间段忙碌。"
            else:
                text = f"参会人 {', '.join(query.attendee_ids)} 在该时间段均空闲。"
            return {"state": state, "reply": self._reply(context, state, text)}
        if command.operation == "query":
            meetings = self._tools.query(context.actor)
            selected = meetings[0].id if len(meetings) == 1 else None
            candidates = self._candidates(meetings)
            state = state.model_copy(
                update={
                    "selected_meeting_id": selected,
                    "meeting_candidates": candidates,
                    "status": "done",
                    "last_tool_results": tuple(
                        meeting.model_dump(mode="json") for meeting in meetings
                    ),
                }
            )
            text = "；".join(
                f"{index}. {meeting.title}（{meeting.start_at:%m月%d日 %H:%M}）"
                for index, meeting in enumerate(meetings, start=1)
            )
            return {
                "state": state,
                "reply": self._reply(context, state, text or "没有找到可见会议。"),
            }
        if command.operation == "create":
            draft = await self._tools.prepare_create(state.draft)
            return {
                "state": state.model_copy(update={"draft": MeetingPatch(**draft.model_dump())}),
                "prepared": draft,
            }
        if command.operation == "update":
            meeting = self._tools.repository.find_visible(context.actor, state.selected_meeting_id)
            if meeting is None:
                raise ValueError("selected meeting is unavailable")
            patch = await self._tools.prepare_update(context.actor, meeting, state.draft)
            return {
                "state": state.model_copy(update={"draft": patch}),
                "prepared": patch,
                "expected_version": meeting.version,
            }
        return {}

    async def _preview(self, data: WorkflowData) -> dict:
        if data.get("reply") or "prepared" not in data:
            return {}
        command, state, context = data["command"], data["state"], data["context"]
        payload = data["prepared"]
        if command.operation == "update":
            payload = UpdateSnapshot(
                meeting_id=state.selected_meeting_id,
                expected_version=data["expected_version"],
                patch=data["prepared"],
            )
            self._update_snapshots = {
                **self._update_snapshots,
                self._state_key(context): payload,
            }
        pending = PendingAction(
            action=command.operation,
            meeting_id=state.selected_meeting_id,
            confirmation_hash=confirmation_hash(context.actor.id, command.operation, payload),
        )
        state = state.model_copy(update={"pending_action": pending, "status": "needs_confirmation"})
        return {
            "state": state,
            "reply": self._reply(context, state, "请确认以下会议变更。", data["prepared"], True),
        }

    async def _confirm(self, data: WorkflowData) -> dict:
        if data.get("reply"):
            return {}
        command, state, context = data["command"], data["state"], data["context"]
        if command.operation == "cancel":
            self._discard_snapshot(self._state_key(context))
            state = state.model_copy(update={"pending_action": None, "status": "done"})
            return {
                "state": state,
                "reply": self._reply(context, state, "已取消，未写入任何会议。"),
            }
        if command.operation != "confirm":
            return {}
        pending = state.pending_action
        if pending is None or state.draft is None:
            state = state.model_copy(update={"status": "rejected"})
            return {
                "state": state,
                "reply": self._reply(context, state, "确认已失效，请重新预览。"),
            }
        payload = state.draft
        if pending.action == "update":
            payload = self._update_snapshots.get(self._state_key(context))
            if payload is None:
                state = state.model_copy(update={"pending_action": None, "status": "rejected"})
                return {
                    "state": state,
                    "reply": self._reply(context, state, "确认已失效，请重新预览。"),
                }
        expected = confirmation_hash(context.actor.id, pending.action, payload)
        if expected != pending.confirmation_hash:
            state = state.model_copy(update={"pending_action": None, "status": "rejected"})
            return {
                "state": state,
                "reply": self._reply(context, state, "确认已失效，请重新预览。"),
            }
        return {"confirmed": True}

    async def _execute(self, data: WorkflowData) -> dict:
        if data.get("reply") or not data.get("confirmed"):
            return {}
        state, context, pending = data["state"], data["context"], data["state"].pending_action
        if pending.action == "create":
            meeting = self._tools.repository.create(
                context.actor.id,
                MeetingDraft(**state.draft.model_dump(exclude_none=True)),
                context.request_id,
            )
        else:
            snapshot = self._update_snapshots.get(self._state_key(context))
            if snapshot is None or snapshot.meeting_id != pending.meeting_id:
                raise ValueError("meeting is unavailable")
            meeting = self._tools.repository.update(
                context.actor.id,
                snapshot.meeting_id,
                snapshot.patch,
                expected_version=snapshot.expected_version,
            )
            self._discard_snapshot(self._state_key(context))
        state = state.model_copy(
            update={"pending_action": None, "status": "done", "selected_meeting_id": meeting.id}
        )
        return {"state": state, "reply": self._reply(context, state, "会议已保存。")}

    @staticmethod
    def _missing_fields(patch: MeetingPatch | None) -> tuple[str, ...]:
        if patch is None:
            return ("主题", "开始时间", "结束时间", "参会人")
        labels = (
            ("title", "主题"),
            ("start_at", "开始时间"),
            ("end_at", "结束时间"),
            ("attendee_ids", "参会人"),
        )
        return tuple(label for field, label in labels if not getattr(patch, field))

    @staticmethod
    def _reply(context, state, text, draft=None, confirmation=False) -> AssistantReply:
        return AssistantReply(
            reply=text,
            status=state.status,
            meeting_draft=draft,
            needs_confirmation=confirmation,
            request_id=context.request_id,
        )

    @staticmethod
    def _state_key(context: ChatContext) -> tuple[str, str]:
        return context.conversation_id, context.actor.id

    def _discard_snapshot(self, key: tuple[str, str]) -> None:
        self._update_snapshots = {
            stored_key: snapshot
            for stored_key, snapshot in self._update_snapshots.items()
            if stored_key != key
        }

    @staticmethod
    def _candidates(meetings) -> tuple[MeetingCandidate, ...]:
        return tuple(
            MeetingCandidate(
                id=meeting.id,
                title=meeting.title,
                start_at=meeting.start_at,
                end_at=meeting.end_at,
            )
            for meeting in meetings
        )
