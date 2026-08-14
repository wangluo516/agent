from collections.abc import Callable
from datetime import datetime
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI

from app.agent.demo_interpreter import DemoInterpreter
from app.agent.interpreter import Interpreter
from app.agent.llm_interpreter import LLMInterpreter
from app.agent.service import MeetingAssistant
from app.api.mock_integrations import router as integrations_router
from app.config import Settings
from app.domain.models import Actor, MeetingDraft
from app.domain.room_ranking import Room, RoomBusyInterval, rank_rooms
from app.integrations.calendar_client import CalendarClient
from app.integrations.demo_calendar import demo_freebusy
from app.integrations.models import FreeBusyRequest, FreeBusyResponse
from app.integrations.room_client import RoomClient
from app.repositories.meetings import MeetingRepository
from app.repositories.seed import seed_meetings

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEMO_ACTORS = (
    Actor(id="alice", display_name="Alice"),
    Actor(id="bob", display_name="Bob"),
    Actor(id="carol", display_name="Carol"),
)
DEMO_ROOMS = (
    Room(
        id="room-orchid",
        name="Orchid",
        capacity=6,
        features=("display", "whiteboard"),
        topics=("design", "设计"),
        busy_intervals=(
            RoomBusyInterval(
                start_at=datetime(2026, 8, 20, 10, tzinfo=SHANGHAI),
                end_at=datetime(2026, 8, 20, 11, tzinfo=SHANGHAI),
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
DEMO_MEETINGS = (
    MeetingDraft(
        title="设计评审",
        start_at=datetime(2026, 8, 15, 10, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 15, 11, tzinfo=SHANGHAI),
        attendee_ids=("bob",),
        room_id="room-orchid",
        required_features=("whiteboard",),
    ),
)


class InProcessCalendar:
    """Deterministic demo free/busy port that exposes only availability."""

    async def freebusy(self, request: FreeBusyRequest) -> FreeBusyResponse:
        return demo_freebusy(request)


class InProcessRooms:
    async def search(
        self,
        topic: str,
        attendee_count: int,
        required_features: tuple[str, ...],
        start_at: datetime,
        end_at: datetime,
    ):
        return rank_rooms(DEMO_ROOMS, topic, attendee_count, required_features, start_at, end_at)


class Runtime:
    def __init__(
        self,
        repository: MeetingRepository,
        actors: tuple[Actor, ...],
        assistant: MeetingAssistant,
        integration_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.repository = repository
        self.actors = {actor.id: actor for actor in actors}
        self.assistant = assistant
        self.integration_client = integration_client

    def actor(self, actor_id: str) -> Actor | None:
        return self.actors.get(actor_id)

    async def aclose(self) -> None:
        if self.integration_client is not None and not self.integration_client.is_closed:
            await self.integration_client.aclose()


LLMFactory = Callable[..., Interpreter]


def build_interpreter(
    settings: Settings,
    *,
    llm_factory: LLMFactory = LLMInterpreter,
) -> Interpreter:
    if settings.mode == "demo":
        return DemoInterpreter()
    if not getenv("MEETING_ASSISTANT_LLM_API_KEY"):
        raise RuntimeError("MEETING_ASSISTANT_LLM_API_KEY is required for LLM mode")
    return llm_factory(model=settings.llm_model, base_url=settings.llm_base_url)


def build_runtime(
    database_path: Path | str | None = None,
    clock: Callable[[], datetime] | None = None,
    *,
    settings: Settings | None = None,
    interpreter: Interpreter | None = None,
    llm_factory: LLMFactory = LLMInterpreter,
) -> Runtime:
    effective_settings = settings or Settings(
        database_path=Path(database_path) if database_path is not None else Path("meetings.db")
    )
    selected_database_path = (
        Path(database_path) if database_path is not None else effective_settings.database_path
    )
    repository = MeetingRepository(selected_database_path)
    seed_meetings(repository, "alice", DEMO_MEETINGS)
    selected_interpreter = interpreter or build_interpreter(
        effective_settings, llm_factory=llm_factory
    )
    integrations_app = FastAPI()
    integrations_app.state.meeting_repository = repository
    integrations_app.include_router(integrations_router)
    integration_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=integrations_app),
        base_url="http://mock-integrations",
    )
    assistant = MeetingAssistant(
        repository=repository,
        calendar=CalendarClient(integration_client),
        rooms=RoomClient(integration_client),
        clock=clock or (lambda: datetime.now(SHANGHAI)),
        interpreter=selected_interpreter,
    )
    return Runtime(
        repository=repository,
        actors=DEMO_ACTORS,
        assistant=assistant,
        integration_client=integration_client,
    )
