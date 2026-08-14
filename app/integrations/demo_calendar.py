from collections.abc import Iterable
from datetime import datetime

from app.domain.models import SHANGHAI_TZ, Meeting
from app.integrations.models import (
    BusyInterval,
    FreeBusyRequest,
    FreeBusyResponse,
    UserBusyIntervals,
)

DEMO_BUSY_INTERVALS = (
    UserBusyIntervals(
        attendee_id="carol",
        busy_intervals=(
            BusyInterval(
                start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI_TZ),
                end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI_TZ),
            ),
        ),
    ),
)


def demo_freebusy(request: FreeBusyRequest, meetings: Iterable[Meeting] = ()) -> FreeBusyResponse:
    fixture_by_attendee = {entry.attendee_id: entry.busy_intervals for entry in DEMO_BUSY_INTERVALS}
    persisted_meetings = tuple(meetings)
    return FreeBusyResponse(
        busy_by_user=tuple(
            UserBusyIntervals(
                attendee_id=attendee_id,
                busy_intervals=_busy_intervals(
                    attendee_id,
                    request,
                    fixture_by_attendee.get(attendee_id, ()),
                    persisted_meetings,
                ),
            )
            for attendee_id in request.attendee_ids
        )
    )


def _busy_intervals(attendee_id, request, fixture_intervals, meetings):
    intervals = [
        interval
        for interval in fixture_intervals
        if interval.start_at < request.window_end and interval.end_at > request.window_start
    ]
    intervals.extend(
        BusyInterval(start_at=meeting.start_at, end_at=meeting.end_at)
        for meeting in meetings
        if meeting.id != request.exclude_meeting_id
        and (attendee_id == meeting.organizer_id or attendee_id in meeting.attendee_ids)
    )
    unique = {(interval.start_at, interval.end_at): interval for interval in intervals}
    return tuple(unique[key] for key in sorted(unique))
