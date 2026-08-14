from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI

from app.api.mock_integrations import router
from app.domain.models import MeetingDraft
from app.integrations.calendar_client import CalendarClient
from app.integrations.errors import IntegrationError
from app.integrations.models import FreeBusyRequest
from app.integrations.room_client import RoomClient
from app.repositories.meetings import MeetingRepository
from app.runtime import InProcessCalendar

SHANGHAI = ZoneInfo("Asia/Shanghai")


def create_app(repository=None) -> FastAPI:
    app = FastAPI()
    if repository is not None:
        app.state.meeting_repository = repository
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_mock_endpoints_expose_only_busy_intervals_and_ranked_room_contract() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        calendar = CalendarClient(client)
        room_client = RoomClient(client)
        busy = await calendar.freebusy(
            FreeBusyRequest(
                attendee_ids=("alice",),
                window_start=datetime(2026, 8, 20, 9, tzinfo=SHANGHAI),
                window_end=datetime(2026, 8, 20, 12, tzinfo=SHANGHAI),
            )
        )
        rooms = await room_client.search(
            topic="design",
            attendee_count=4,
            required_features=("display",),
            start_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 20, 11, tzinfo=SHANGHAI),
        )

    assert busy.intervals_for("alice") == ()
    assert rooms[0].room.id == "room-bamboo"
    assert "title" not in (await _raw_calendar_response()).lower()


@pytest.mark.asyncio
async def test_calendar_client_and_in_process_calendar_share_carol_busy_fixture() -> None:
    request = FreeBusyRequest(
        attendee_ids=("carol",),
        window_start=datetime(2026, 8, 15, 9, tzinfo=SHANGHAI),
        window_end=datetime(2026, 8, 15, 12, tzinfo=SHANGHAI),
    )
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        public_response = await CalendarClient(client).freebusy(request)

    runtime_response = await InProcessCalendar().freebusy(request)

    assert public_response == runtime_response
    assert public_response.intervals_for("carol")[0].start_at == datetime(
        2026, 8, 15, 10, tzinfo=SHANGHAI
    )
    assert "title" not in (await _raw_calendar_response_for(request)).lower()


@pytest.mark.asyncio
async def test_mock_calendar_excludes_the_meeting_currently_being_updated(tmp_path) -> None:
    repository = MeetingRepository(tmp_path / "calendar-exclusion.db")
    meeting = repository.create(
        "alice",
        MeetingDraft(
            title="设计评审",
            start_at=datetime(2026, 8, 15, 15, tzinfo=SHANGHAI),
            end_at=datetime(2026, 8, 15, 16, tzinfo=SHANGHAI),
            attendee_ids=("bob",),
        ),
        "seed-calendar-exclusion",
    )
    transport = httpx.ASGITransport(app=create_app(repository))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/mock/calendar/freebusy",
            json={
                "attendee_ids": ["bob"],
                "window_start": "2026-08-15T15:00:00+08:00",
                "window_end": "2026-08-15T16:00:00+08:00",
                "exclude_meeting_id": meeting.id,
            },
        )

    assert response.status_code == 200
    assert response.json()["busy_by_user"][0]["busy_intervals"] == []


@pytest.mark.asyncio
async def test_typed_clients_surface_controlled_error_for_malformed_upstream_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"busy_by_user": {"alice": [{}]}})
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(IntegrationError, match="invalid response"):
            await CalendarClient(client).freebusy(
                FreeBusyRequest(
                    attendee_ids=("alice",),
                    window_start=datetime(2026, 8, 20, 9, tzinfo=SHANGHAI),
                    window_end=datetime(2026, 8, 20, 12, tzinfo=SHANGHAI),
                )
            )


@pytest.mark.asyncio
async def test_room_client_rejects_malformed_upstream_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"rooms": [{"score": 3}]})
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(IntegrationError, match="invalid response"):
            await RoomClient(client).search(
                topic="design",
                attendee_count=4,
                required_features=("display",),
                start_at=datetime(2026, 8, 20, 9, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
            )


async def _raw_calendar_response() -> str:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return (
            await client.post(
                "/mock/calendar/freebusy",
                json={
                    "attendee_ids": ["alice"],
                    "window_start": "2026-08-20T09:00:00+08:00",
                    "window_end": "2026-08-20T12:00:00+08:00",
                },
            )
        ).text


async def _raw_calendar_response_for(request: FreeBusyRequest) -> str:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return (
            await client.post(
                "/mock/calendar/freebusy",
                json=request.model_dump(mode="json"),
            )
        ).text
