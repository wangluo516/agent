from app.domain.models import MeetingDraft
from app.repositories.meetings import MeetingRepository

_DEMO_SEED_MARKER = "demo-seed-v1"


def seed_meetings(
    repository: MeetingRepository, organizer_id: str, drafts: tuple[MeetingDraft, ...]
) -> None:
    if repository.metadata_value(_DEMO_SEED_MARKER) == "applied":
        return
    for index, draft in enumerate(drafts, start=1):
        repository.create(organizer_id, draft, f"seed-{index}")
    repository.set_metadata(_DEMO_SEED_MARKER, "applied")
