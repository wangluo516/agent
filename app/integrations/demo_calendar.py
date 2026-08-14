from datetime import datetime

from app.domain.models import SHANGHAI_TZ
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


def demo_freebusy(request: FreeBusyRequest) -> FreeBusyResponse:
    fixture_by_attendee = {entry.attendee_id: entry.busy_intervals for entry in DEMO_BUSY_INTERVALS}
    return FreeBusyResponse(
        busy_by_user=tuple(
            UserBusyIntervals(
                attendee_id=attendee_id,
                busy_intervals=tuple(
                    interval
                    for interval in fixture_by_attendee.get(attendee_id, ())
                    if interval.start_at < request.window_end
                    and interval.end_at > request.window_start
                ),
            )
            for attendee_id in request.attendee_ids
        )
    )
