from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field, field_validator, model_validator

from app.domain.models import SHANGHAI_TZ, ConversationState, ImmutableModel, MeetingPatch

Operation = Literal[
    "create",
    "query",
    "update",
    "availability",
    "select",
    "confirm",
    "cancel",
    "unsafe",
    "unknown",
]


class AvailabilityQuery(ImmutableModel):
    attendee_ids: tuple[str, ...] = ()
    window_start: datetime | None = None
    window_end: datetime | None = None
    duration_minutes: int = Field(default=60, gt=0)

    @field_validator("window_start", "window_end")
    @classmethod
    def normalize_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("availability times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_window_when_complete(self) -> "AvailabilityQuery":
        if (
            self.window_start is not None
            and self.window_end is not None
            and self.window_end <= self.window_start
        ):
            raise ValueError("availability window_end must be after window_start")
        return self


class MeetingCommand(ImmutableModel):
    operation: Operation
    patch: MeetingPatch = Field(default_factory=MeetingPatch)
    meeting_id: str | None = None
    availability: AvailabilityQuery | None = None


class InterpretContext(ImmutableModel):
    actor_id: str
    now: datetime
    state: ConversationState


class Interpreter(Protocol):
    async def interpret(self, message: str, context: InterpretContext) -> MeetingCommand: ...
