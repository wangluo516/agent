from typing import Protocol

from app.domain.errors import AttendeeBusyError, ValidationError
from app.domain.models import Actor, Meeting, MeetingDraft, MeetingPatch
from app.domain.policies import authorize_update, validate_draft
from app.integrations.models import FreeBusyRequest, FreeBusyResponse


class RepositoryPort(Protocol):
    def list_for_actor(self, actor: Actor) -> list[Meeting]: ...
    def find_visible(self, actor: Actor, meeting_id: str) -> Meeting | None: ...
    def create(self, organizer_id: str, draft: MeetingDraft, idempotency_key: str) -> Meeting: ...
    def update(
        self, organizer_id: str, meeting_id: str, patch: MeetingPatch, expected_version: int
    ) -> Meeting: ...


class CalendarPort(Protocol):
    async def freebusy(self, request: FreeBusyRequest) -> FreeBusyResponse: ...


class RoomPort(Protocol):
    async def search(self, topic, attendee_count, required_features, start_at, end_at): ...


class MeetingTools:
    def __init__(self, repository: RepositoryPort, calendar: CalendarPort, rooms: RoomPort) -> None:
        self.repository = repository
        self.calendar = calendar
        self.rooms = rooms

    def query(self, actor: Actor) -> tuple[Meeting, ...]:
        return tuple(self.repository.list_for_actor(actor))

    async def availability(self, request: FreeBusyRequest) -> FreeBusyResponse:
        return await self.calendar.freebusy(request)

    async def prepare_create(self, patch: MeetingPatch) -> MeetingDraft:
        draft = self._complete_draft(patch)
        await self._ensure_available(draft)
        ranked = await self.rooms.search(
            draft.title,
            len(draft.attendee_ids),
            draft.required_features,
            draft.start_at,
            draft.end_at,
        )
        if not ranked:
            raise ValidationError("no suitable room is available")
        return validate_draft(draft.model_copy(update={"room_id": ranked[0].room.id}))

    async def prepare_update(
        self, actor: Actor, meeting: Meeting, patch: MeetingPatch
    ) -> MeetingPatch:
        authorize_update(actor, meeting, patch)
        values = patch.model_dump(exclude_unset=True, exclude_none=True)
        if "start_at" in values and "end_at" not in values:
            values["end_at"] = values["start_at"] + (meeting.end_at - meeting.start_at)
        candidate = MeetingDraft(
            **meeting.model_dump(include=set(MeetingDraft.model_fields)) | values
        )
        await self._ensure_available(candidate)
        ranked = await self.rooms.search(
            candidate.title,
            len(candidate.attendee_ids),
            candidate.required_features,
            candidate.start_at,
            candidate.end_at,
        )
        if not ranked:
            raise ValidationError("no suitable room is available")
        available_room_ids = frozenset(item.room.id for item in ranked)
        if candidate.room_id not in available_room_ids:
            values["room_id"] = ranked[0].room.id
        return MeetingPatch(**values)

    async def _ensure_available(self, draft: MeetingDraft) -> None:
        response = await self.calendar.freebusy(
            FreeBusyRequest(
                attendee_ids=draft.attendee_ids,
                window_start=draft.start_at,
                window_end=draft.end_at,
            )
        )
        busy_attendees = tuple(
            attendee for attendee in draft.attendee_ids if response.intervals_for(attendee)
        )
        if busy_attendees:
            raise AttendeeBusyError(busy_attendees)

    @staticmethod
    def _complete_draft(patch: MeetingPatch) -> MeetingDraft:
        values = patch.model_dump(exclude_none=True)
        try:
            return MeetingDraft(**values)
        except (TypeError, ValueError) as error:
            raise ValidationError("meeting draft is incomplete") from error
