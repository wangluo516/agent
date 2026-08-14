from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field

from app.domain.models import ConversationState, ImmutableModel, MeetingPatch

Operation = Literal["create", "query", "update", "confirm", "cancel", "unsafe", "unknown"]


class MeetingCommand(ImmutableModel):
    operation: Operation
    patch: MeetingPatch = Field(default_factory=MeetingPatch)
    meeting_id: str | None = None


class InterpretContext(ImmutableModel):
    actor_id: str
    now: datetime
    state: ConversationState


class Interpreter(Protocol):
    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand: ...
