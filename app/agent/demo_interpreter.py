import re
from datetime import datetime, timedelta

from app.agent.interpreter import AvailabilityQuery, InterpretContext, MeetingCommand
from app.domain.models import MeetingPatch


class DemoInterpreter:
    """Deterministic parser for the documented Chinese demo journeys."""

    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand:
        normalized = message.strip()
        if normalized in {"确认", "确认执行", "是的，确认"}:
            return MeetingCommand(operation="confirm")
        if normalized in {"取消", "取消操作", "不确认"}:
            return MeetingCommand(operation="cancel")
        selected_meeting_id = self._selected_candidate_id(normalized, context)
        if selected_meeting_id is not None:
            return MeetingCommand(operation="select", meeting_id=selected_meeting_id)
        if any(token in normalized for token in ("空闲", "有空", "忙不忙")):
            return MeetingCommand(
                operation="availability",
                availability=self._availability_query(normalized, context.now),
            )
        if "查询" in normalized or "有哪些会议" in normalized:
            return MeetingCommand(operation="query")
        operation = self._operation(normalized, context)
        reference_date = None
        if operation == "update" and not any(day in normalized for day in ("今天", "明天")):
            selected = next(
                (
                    meeting
                    for meeting in context.state.meeting_candidates
                    if meeting.id == context.state.selected_meeting_id
                ),
                None,
            )
            reference_date = selected.start_at.date() if selected is not None else None
        return MeetingCommand(
            operation=operation,
            patch=self._patch(normalized, context.now, reference_date=reference_date),
        )

    @staticmethod
    def _selected_candidate_id(message: str, context: InterpretContext) -> str | None:
        if context.state.status != "needs_clarification":
            return None
        candidates = context.state.meeting_candidates
        ordinal = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*个", message)
        if ordinal:
            numbers = {
                "一": 1,
                "二": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
                "九": 9,
                "十": 10,
            }
            token = ordinal.group(1)
            index = int(token) if token.isdigit() else numbers.get(token)
            if index is not None and 1 <= index <= len(candidates):
                return candidates[index - 1].id
        matching_ids = tuple(candidate.id for candidate in candidates if candidate.id in message)
        if len(matching_ids) == 1:
            return matching_ids[0]
        matching_titles = tuple(
            candidate.id for candidate in candidates if candidate.title in message
        )
        return matching_titles[0] if len(matching_titles) == 1 else None

    @staticmethod
    def _operation(message: str, context: InterpretContext) -> str:
        if any(token in message for token in ("改到", "改成", "修改", "改期")):
            return "update"
        if (
            "创建" in message
            or context.state.draft is not None
            or any(token in message for token in ("参会人", "持续", "点"))
        ):
            return "create"
        return "unknown"

    def _patch(self, message: str, now: datetime, reference_date=None) -> MeetingPatch:
        values: dict[str, object] = {}
        title = re.search(r"创建(.+?)(?:会议|$)", message)
        if title:
            values["title"] = title.group(1).strip()
        start = self._start_time(message, now, reference_date=reference_date)
        duration = re.search(r"持续\s*(\d+)\s*小时", message)
        if start:
            values["start_at"] = start
            if duration:
                values["end_at"] = start + timedelta(hours=int(duration.group(1)))
        attendees = re.search(r"参会人\s*([\w\s和、,，-]+?)(?:，|,|需要|$)", message)
        if attendees:
            values["attendee_ids"] = tuple(
                value
                for value in re.split(r"\s*(?:和|、|,|，)\s*|\s+", attendees.group(1).strip())
                if value
            )
        if "白板" in message:
            values["required_features"] = ("whiteboard",)
        return MeetingPatch(**values)

    def _availability_query(self, message: str, now: datetime) -> AvailabilityQuery:
        attendee_ids = tuple(
            dict.fromkeys(re.findall(r"\b(?:alice|bob|carol)\b", message.casefold()))
        )
        start = self._start_time(message, now)
        end = start + timedelta(hours=1) if start is not None else None
        if start is None and any(period in message for period in ("上午", "下午")):
            day = now.date() + timedelta(days=1 if "明天" in message else 0)
            start_hour, end_hour = (13, 18) if "下午" in message else (9, 12)
            start = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(
                hour=start_hour
            )
            end = start.replace(hour=end_hour)
        return AvailabilityQuery(
            attendee_ids=attendee_ids,
            window_start=start,
            window_end=end,
        )

    @staticmethod
    def _start_time(message: str, now: datetime, reference_date=None) -> datetime | None:
        match = re.search(r"(?:(明天|今天))?(?:下午|上午)?\s*(\d{1,2})\s*点", message)
        if not match:
            return None
        day = reference_date or now.date()
        if match.group(1) == "明天":
            day = now.date() + timedelta(days=1)
        elif match.group(1) == "今天":
            day = now.date()
        hour = int(match.group(2))
        if "下午" in message and hour < 12:
            hour += 12
        return datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour)
