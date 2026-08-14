from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.domain.models import SHANGHAI_TZ, ImmutableModel


class RoomBusyInterval(ImmutableModel):
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("times must include a timezone")
        return value.astimezone(SHANGHAI_TZ)

    @model_validator(mode="after")
    def require_positive_interval(self) -> "RoomBusyInterval":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class Room(ImmutableModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capacity: int = Field(gt=0)
    features: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    busy_intervals: tuple[RoomBusyInterval, ...] = ()


class RankedRoom(ImmutableModel):
    room: Room
    score: int
    reason: str


def rank_rooms(
    rooms: tuple[Room, ...],
    topic: str,
    attendee_count: int,
    required_features: tuple[str, ...],
    start_at: datetime,
    end_at: datetime,
) -> tuple[RankedRoom, ...]:
    if attendee_count <= 0:
        raise ValueError("attendee_count must be positive")
    if (
        start_at.tzinfo is None
        or start_at.utcoffset() is None
        or end_at.tzinfo is None
        or end_at.utcoffset() is None
    ):
        raise ValueError("room search times must include a timezone")
    if end_at <= start_at:
        raise ValueError("room search end_at must be after start_at")
    normalized_topic = topic.casefold()
    required = frozenset(feature.casefold() for feature in required_features)
    ranking = [
        _rank(room, normalized_topic, attendee_count, required)
        for room in rooms
        if room.capacity >= attendee_count
        and required <= {feature.casefold() for feature in room.features}
        and not _is_busy(room, start_at, end_at)
    ]
    return tuple(sorted(ranking, key=lambda item: (-item.score, item.room.id)))


def _rank(room: Room, topic: str, attendee_count: int, required: frozenset[str]) -> RankedRoom:
    topic_match = any(label.casefold() in topic for label in room.topics)
    spare = room.capacity - attendee_count
    # Prefer a closer capacity fit after satisfying hard requirements.
    score = (100 if topic_match else 0) + max(0, 4 - spare)
    topic_reason = (
        f"matches topic '{next(label for label in room.topics if label.casefold() in topic)}'"
        if topic_match
        else "general-purpose room"
    )
    feature_reason = ", ".join(sorted(required)) if required else "no required features"
    return RankedRoom(
        room=room, score=score, reason=f"{topic_reason}; {spare} spare seats; has {feature_reason}"
    )


def _is_busy(room: Room, start_at: datetime, end_at: datetime) -> bool:
    return any(
        interval.start_at < end_at and interval.end_at > start_at
        for interval in room.busy_intervals
    )
