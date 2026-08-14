from app.domain.models import MeetingDraft
from app.repositories.meetings import MeetingRepository


def seed_meetings(
    repository: MeetingRepository, organizer_id: str, drafts: tuple[MeetingDraft, ...]
) -> None:
    for index, draft in enumerate(drafts, start=1):
        repository.create(organizer_id, draft, f"seed-{index}")
