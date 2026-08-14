import json
import re
from datetime import datetime, timedelta
from os import getenv

from langchain_openai import ChatOpenAI

from app.agent.interpreter import InterpretContext, MeetingCommand, Operation
from app.domain.models import MeetingPatch

_EXPLICIT_OPERATION_TOKENS = (
    "查询",
    "查一下",
    "有什么会议",
    "有哪些会议",
    "是否",
    "有没有",
    "什么时候",
    "空闲",
    "有空",
    "忙不忙",
    "确认",
    "取消",
    "创建",
    "新建",
    "修改",
    "改到",
    "改成",
    "删除",
    "query",
    "create",
    "schedule",
    "update",
    "cancel",
    "confirm",
    "available",
    "availability",
    "free",
)

_FEATURE_INSTRUCTION = (
    "required_features 只能使用 display、whiteboard、video；"
    "投影仪、投影、显示屏或屏幕映射为 display，白板映射为 whiteboard，"
    "视频会议映射为 video。"
)

_TIME_RANGE_PATTERN = re.compile(
    r"(?:(明天|今天))?\s*(上午|下午)?\s*(\d{1,2})\s*点\s*"
    r"(半|\d{1,2}\s*分)?\s*(?:到|至|-|—)\s*(上午|下午)?\s*"
    r"(\d{1,2})\s*点\s*(半|\d{1,2}\s*分)?"
)
_START_TIME_PATTERN = re.compile(
    r"(?:(明天|今天))?\s*(上午|下午)?\s*(\d{1,2})\s*点\s*(半|\d{1,2}\s*分)?"
)
_DURATION_PATTERN = re.compile(r"持续\s*(\d+(?:\.\d+)?)\s*(小时|分钟)")
_ATTENDEE_PATTERN = re.compile(r"参会人\s*[:：]?\s*(.+?)(?=\s*(?:需要|要求)|$)")
_ATTENDEE_ADD_PATTERN = re.compile(
    r"(?:参会人\s*)?(?:再\s*)?(?:加|增加|添加)(?:上)?(?:\s*(?:一个|一位))?\s*"
    r"(.+?)(?=\s*(?:需要|要求)|$)"
)
_ATTENDEE_REMOVE_PATTERN = re.compile(
    r"(?:参会人\s*)?(?:删除|移除|去掉|减少)(?:\s*(?:一个|一位))?\s*"
    r"(.+?)(?=\s*(?:需要|要求)|$)"
)


class LLMInterpreter:
    """Optional structured-output interpreter. It never receives tool access or actor authority."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        api_key = getenv("MEETING_ASSISTANT_LLM_API_KEY")
        if not api_key:
            raise ValueError("MEETING_ASSISTANT_LLM_API_KEY is required for LLM mode")
        selected_model = model or getenv("MEETING_ASSISTANT_LLM_MODEL", "gpt-4.1-mini")
        model_options = {
            "model": selected_model,
            "api_key": api_key,
            "base_url": base_url or getenv("MEETING_ASSISTANT_LLM_BASE_URL"),
            "temperature": 0,
        }
        if selected_model.startswith("deepseek-"):
            model_options["extra_body"] = {"thinking": {"type": "disabled"}}
        client = ChatOpenAI(**model_options)
        self._model = client.with_structured_output(MeetingCommand, method="function_calling")
        self._patch_model = client.with_structured_output(MeetingPatch, method="function_calling")

    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand:
        state_summary = json.dumps(
            context.state.model_dump(
                mode="json",
                include={
                    "draft",
                    "selected_meeting_id",
                    "meeting_candidates",
                    "status",
                },
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
        continuation = self._continuation_operation(message, context)
        if continuation is not None:
            prompt = (
                f"当前存在未完成的{self._operation_label(continuation)}草稿。"
                "本轮是对该草稿补充字段，不是独立的忙闲查询。"
                "只提取用户本轮明确提供的 MeetingPatch 字段，不得复制已有字段，"
                "不得生成身份、权限、会议室或未提供的内容。"
                f"{_FEATURE_INSTRUCTION}"
                f" 当前时间={context.now.isoformat()}，会话状态={state_summary}。"
                f"用户：{message}"
            )
            extracted = await self._patch_model.ainvoke(prompt)
            patch = self._normalize_explicit_fields(message, context, extracted)
            return MeetingCommand(operation=continuation, patch=patch)
        prompt = (
            "只提取会议操作和用户明确提供的字段，不得生成身份、权限或调用工具。"
            " 用户只提供新时间而未提供日期时，保留已选会议的原日期；"
            "需要选择会议时，只能使用候选会议中的 ID。"
            f"{_FEATURE_INSTRUCTION}"
            f" 当前时间={context.now.isoformat()}，会话状态={state_summary}。用户：{message}"
        )
        return await self._model.ainvoke(prompt)

    @staticmethod
    def _continuation_operation(message: str, context: InterpretContext) -> Operation | None:
        state = context.state
        normalized = message.strip().casefold()
        if state.status == "needs_confirmation" and state.pending_action is not None:
            interrupt_tokens = (
                "查询",
                "查一下",
                "有什么会议",
                "有哪些会议",
                "是否",
                "有没有",
                "什么时候",
                "空闲",
                "有空",
                "忙不忙",
                "确认",
                "取消",
                "query",
                "cancel",
                "confirm",
                "available",
                "availability",
                "free",
            )
            if any(token in normalized for token in interrupt_tokens):
                return None
            return state.pending_action.action
        if state.status != "collecting" or state.draft is None:
            return None
        if any(token in normalized for token in _EXPLICIT_OPERATION_TOKENS):
            return None
        return "update" if state.selected_meeting_id else "create"

    @staticmethod
    def _operation_label(operation: Operation) -> str:
        return "修改" if operation == "update" else "创建"

    @classmethod
    def _normalize_explicit_fields(
        cls, message: str, context: InterpretContext, extracted: MeetingPatch
    ) -> MeetingPatch:
        values = extracted.model_dump(exclude_unset=True)
        interval = cls._explicit_interval(message, context)
        if interval is not None:
            values["start_at"], values["end_at"] = interval

        attendees = cls._explicit_attendees(message, context)
        if attendees is not None:
            values["attendee_ids"] = attendees

        features = cls._explicit_features(message)
        if features:
            values["required_features"] = features
        return MeetingPatch(**values)

    @classmethod
    def _explicit_interval(
        cls, message: str, context: InterpretContext
    ) -> tuple[datetime, datetime] | None:
        range_match = _TIME_RANGE_PATTERN.search(message)
        if range_match:
            day_token, start_period, start_hour, start_minute = range_match.group(1, 2, 3, 4)
            end_period, end_hour, end_minute = range_match.group(5, 6, 7)
            start = cls._to_datetime(
                context,
                day_token,
                start_period,
                start_hour,
                start_minute,
            )
            end = cls._to_datetime(
                context,
                day_token,
                end_period or start_period,
                end_hour,
                end_minute,
            )
            return (start, end)

        start_match = _START_TIME_PATTERN.search(message)
        duration_match = _DURATION_PATTERN.search(message)
        if start_match is None or duration_match is None:
            return None
        start = cls._to_datetime(context, *start_match.group(1, 2, 3, 4))
        amount = float(duration_match.group(1))
        duration = (
            timedelta(hours=amount)
            if duration_match.group(2) == "小时"
            else timedelta(minutes=amount)
        )
        return (start, start + duration)

    @staticmethod
    def _to_datetime(
        context: InterpretContext,
        day_token: str | None,
        period: str | None,
        hour_token: str,
        minute_token: str | None,
    ) -> datetime:
        day = context.now.date()
        if day_token == "明天":
            day += timedelta(days=1)
        elif day_token is None and context.state.selected_meeting_id:
            selected = next(
                (
                    meeting
                    for meeting in context.state.meeting_candidates
                    if meeting.id == context.state.selected_meeting_id
                ),
                None,
            )
            if selected is not None:
                day = selected.start_at.date()
        hour = int(hour_token)
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "上午" and hour == 12:
            hour = 0
        minute = 30 if minute_token == "半" else int((minute_token or "0").removesuffix("分"))
        return datetime.combine(day, datetime.min.time(), tzinfo=context.now.tzinfo).replace(
            hour=hour,
            minute=minute,
        )

    @staticmethod
    def _explicit_attendees(message: str, context: InterpretContext) -> tuple[str, ...] | None:
        existing = tuple(context.state.draft.attendee_ids or ()) if context.state.draft else ()
        add_match = _ATTENDEE_ADD_PATTERN.search(message)
        if add_match is not None:
            additions = LLMInterpreter._split_attendees(add_match.group(1))
            return tuple(dict.fromkeys((*existing, *additions)))

        remove_match = _ATTENDEE_REMOVE_PATTERN.search(message)
        if remove_match is not None:
            removals = frozenset(LLMInterpreter._split_attendees(remove_match.group(1)))
            return tuple(attendee for attendee in existing if attendee not in removals)

        match = _ATTENDEE_PATTERN.search(message)
        if match is None:
            return None
        return LLMInterpreter._split_attendees(match.group(1))

    @staticmethod
    def _split_attendees(value: str) -> tuple[str, ...]:
        return tuple(
            attendee
            for attendee in re.split(r"\s*(?:和|、|,|，)\s*|\s+", value.strip())
            if attendee
        )

    @staticmethod
    def _explicit_features(message: str) -> tuple[str, ...]:
        features: list[str] = []
        if any(token in message for token in ("投影仪", "投影", "显示屏", "屏幕")):
            features.append("display")
        if "白板" in message:
            features.append("whiteboard")
        if "视频会议" in message:
            features.append("video")
        return tuple(features)
