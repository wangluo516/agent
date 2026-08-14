from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class Actor(ImmutableModel):
    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class MeetingDraft(ImmutableModel):
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    attendee_ids: tuple[str, ...]
    room_id: str | None = None
    required_features: tuple[str, ...] = ()

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("meeting times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_interval(self) -> "MeetingDraft":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class MeetingPatch(ImmutableModel):
    title: str | None = Field(default=None, min_length=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendee_ids: tuple[str, ...] | None = None
    room_id: str | None = None
    required_features: tuple[str, ...] | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone_when_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("meeting times must include a timezone")
        return value.astimezone(SHANGHAI_TZ) if value is not None else None


class Meeting(MeetingDraft):
    id: str = Field(min_length=1)
    organizer_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1)


class PendingAction(ImmutableModel):
    action: Literal["create", "update"]
    confirmation_hash: str = Field(min_length=1)
    meeting_id: str | None = None


class MeetingCandidate(ImmutableModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime


class ConversationState(ImmutableModel):
    actor_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    draft: MeetingPatch | None = None
    selected_meeting_id: str | None = None
    meeting_candidates: tuple[MeetingCandidate, ...] = ()
    pending_action: PendingAction | None = None
    last_tool_results: tuple[dict[str, object], ...] = ()
    status: Literal[
        "collecting", "needs_clarification", "needs_confirmation", "done", "rejected"
    ] = "collecting"

    def with_draft(self, patch: MeetingPatch) -> "ConversationState":
        merged = (self.draft or MeetingPatch()).model_dump(exclude_unset=True)
        changes = patch.model_dump(exclude_unset=True)
        if (
            changes.get("start_at") is not None
            and changes.get("end_at") is None
            and self.draft is not None
            and self.draft.start_at is not None
            and self.draft.end_at is not None
        ):
            changes["end_at"] = changes["start_at"] + (self.draft.end_at - self.draft.start_at)
        merged.update(changes)
        return self.model_copy(update={"draft": MeetingPatch(**merged)})
