from os import getenv

from langchain_openai import ChatOpenAI

from app.agent.interpreter import InterpretContext, MeetingCommand


class LLMInterpreter:
    """Optional structured-output interpreter. It never receives tool access or actor authority."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        api_key = getenv("MEETING_ASSISTANT_LLM_API_KEY")
        if not api_key:
            raise ValueError("MEETING_ASSISTANT_LLM_API_KEY is required for LLM mode")
        self._model = ChatOpenAI(
            model=model or getenv("MEETING_ASSISTANT_LLM_MODEL", "gpt-4.1-mini"),
            api_key=api_key,
            base_url=base_url or getenv("MEETING_ASSISTANT_LLM_BASE_URL"),
            temperature=0,
        ).with_structured_output(MeetingCommand)

    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand:
        prompt = (
            "只提取会议操作和用户明确提供的字段，不得生成身份、权限或调用工具。"
            f" 当前时间={context.now.isoformat()}，已有草稿={context.state.draft}。用户：{message}"
        )
        return await self._model.ainvoke(prompt)
