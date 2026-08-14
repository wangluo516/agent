import re
from datetime import datetime, timedelta

from app.agent.interpreter import InterpretContext, MeetingCommand
from app.domain.models import MeetingPatch


class DemoInterpreter:
    """Deterministic parser for the documented Chinese demo journeys."""

    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand:
        normalized = message.strip()
        if normalized in {"确认", "确认执行", "是的，确认"}:
            return MeetingCommand(operation="confirm")
        if normalized in {"取消", "取消操作", "不确认"}:
            return MeetingCommand(operation="cancel")
        if "查询" in normalized or "有哪些会议" in normalized:
            return MeetingCommand(operation="query")
        operation = self._operation(normalized, context)
        return MeetingCommand(operation=operation, patch=self._patch(normalized, context.now))

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

    def _patch(self, message: str, now: datetime) -> MeetingPatch:
        values: dict[str, object] = {}
        title = re.search(r"创建(.+?)(?:会议|$)", message)
        if title:
            values["title"] = title.group(1).strip()
        start = self._start_time(message, now)
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

    @staticmethod
    def _start_time(message: str, now: datetime) -> datetime | None:
        match = re.search(r"(?:(明天|今天))?(?:下午|上午)?\s*(\d{1,2})\s*点", message)
        if not match:
            return None
        day = now.date() + timedelta(days=1 if match.group(1) == "明天" else 0)
        hour = int(match.group(2))
        if "下午" in message and hour < 12:
            hour += 12
        return datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour)
