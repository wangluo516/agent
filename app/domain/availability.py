from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

Interval = tuple[datetime, datetime]


def find_common_free_slots(
    busy_by_user: Mapping[str, Sequence[Interval]],
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
) -> tuple[Interval, ...]:
    """Return free intervals shared by all attendees within a timezone-aware window."""
    _validate_interval(window_start, window_end)
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    busy = sorted(
        (
            _clip(interval, window_start, window_end)
            for intervals in busy_by_user.values()
            for interval in intervals
        ),
        key=lambda interval: interval[0],
    )
    merged = _merge(interval for interval in busy if interval is not None)
    minimum = timedelta(minutes=duration_minutes)
    cursor = window_start
    free: list[Interval] = []
    for start, end in merged:
        if start - cursor >= minimum:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if window_end - cursor >= minimum:
        free.append((cursor, window_end))
    return tuple(free)


def _validate_interval(start: datetime, end: datetime) -> None:
    if (
        start.tzinfo is None
        or start.utcoffset() is None
        or end.tzinfo is None
        or end.utcoffset() is None
    ):
        raise ValueError("interval times must include a timezone")
    if end <= start:
        raise ValueError("interval duration must be positive")


def _clip(interval: Interval, window_start: datetime, window_end: datetime) -> Interval | None:
    start, end = interval
    _validate_interval(start, end)
    clipped = (max(start, window_start), min(end, window_end))
    return clipped if clipped[0] < clipped[1] else None


def _merge(intervals: Sequence[Interval] | object) -> tuple[Interval, ...]:
    merged: list[Interval] = []
    for start, end in intervals:  # type: ignore[union-attr]
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return tuple(merged)
