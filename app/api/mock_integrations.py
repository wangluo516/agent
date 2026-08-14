from datetime import datetime

from fastapi import APIRouter, Request

from app.domain.models import SHANGHAI_TZ
from app.domain.room_ranking import Room, RoomBusyInterval, rank_rooms
from app.integrations.demo_calendar import demo_freebusy
from app.integrations.models import (
    FreeBusyRequest,
    FreeBusyResponse,
    RoomSearchRequest,
    RoomSearchResponse,
)

router = APIRouter()

_ROOMS = (
    Room(
        id="room-orchid",
        name="Orchid",
        capacity=6,
        features=("display", "whiteboard"),
        topics=("design", "设计"),
        busy_intervals=(
            RoomBusyInterval(
                start_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI_TZ),
                end_at=datetime(2026, 8, 20, 11, tzinfo=SHANGHAI_TZ),
            ),
        ),
    ),
    Room(
        id="room-bamboo",
        name="Bamboo",
        capacity=12,
        features=("display", "video"),
        topics=("planning",),
    ),
    Room(id="room-lotus", name="Lotus", capacity=4, features=("whiteboard",), topics=("focus",)),
)


@router.post("/mock/calendar/freebusy", response_model=FreeBusyResponse)
def freebusy(payload: FreeBusyRequest, request: Request) -> FreeBusyResponse:
    repository = getattr(request.app.state, "meeting_repository", None)
    runtime = getattr(request.app.state, "runtime", None)
    if repository is None and runtime is not None:
        repository = runtime.repository
    meetings = (
        repository.list_overlapping(payload.window_start, payload.window_end)
        if repository is not None
        else ()
    )
    return demo_freebusy(payload, meetings)


@router.post("/mock/rooms/search", response_model=RoomSearchResponse)
def search_rooms(request: RoomSearchRequest) -> RoomSearchResponse:
    return RoomSearchResponse(
        rooms=rank_rooms(
            _ROOMS,
            request.topic,
            request.attendee_count,
            request.required_features,
            request.start_at,
            request.end_at,
        )
    )
