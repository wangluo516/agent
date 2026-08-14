import json
from os import getenv

from langchain_openai import ChatOpenAI

from app.agent.interpreter import InterpretContext, MeetingCommand


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
        self._model = ChatOpenAI(**model_options).with_structured_output(
            MeetingCommand, method="function_calling"
        )

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
        prompt = (
            "只提取会议操作和用户明确提供的字段，不得生成身份、权限或调用工具。"
            " 用户只提供新时间而未提供日期时，保留已选会议的原日期；"
            "需要选择会议时，只能使用候选会议中的 ID。"
            f" 当前时间={context.now.isoformat()}，会话状态={state_summary}。用户：{message}"
        )
        return await self._model.ainvoke(prompt)
