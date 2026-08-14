from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.domain.models import SHANGHAI_TZ, ImmutableModel
from app.domain.room_ranking import RankedRoom


class BusyInterval(ImmutableModel):
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_interval(self) -> "BusyInterval":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class FreeBusyRequest(ImmutableModel):
    attendee_ids: tuple[str, ...] = Field(min_length=1)
    window_start: datetime
    window_end: datetime

    @field_validator("window_start", "window_end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_window(self) -> "FreeBusyRequest":
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class UserBusyIntervals(ImmutableModel):
    attendee_id: str = Field(min_length=1)
    busy_intervals: tuple[BusyInterval, ...] = ()


class FreeBusyResponse(ImmutableModel):
    busy_by_user: tuple[UserBusyIntervals, ...]

    def intervals_for(self, attendee_id: str) -> tuple[BusyInterval, ...]:
        return next(
            (
                entry.busy_intervals
                for entry in self.busy_by_user
                if entry.attendee_id == attendee_id
            ),
            (),
        )


class RoomSearchRequest(ImmutableModel):
    topic: str = Field(min_length=1)
    attendee_count: int = Field(gt=0)
    required_features: tuple[str, ...] = ()
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_window(self) -> "RoomSearchRequest":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class RoomSearchResponse(ImmutableModel):
    rooms: tuple[RankedRoom, ...]
