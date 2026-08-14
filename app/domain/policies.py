import json
import re
from hashlib import sha256

from app.domain.errors import AuthorizationError, ValidationError
from app.domain.models import Actor, Meeting, MeetingDraft, MeetingPatch

_UNSAFE_PATTERNS = (
    (re.compile(r"\bdelete\b", re.IGNORECASE), "deletion is not supported"),
    (re.compile(r"\bdrop\b|\btruncate\b", re.IGNORECASE), "database commands are not supported"),
    (re.compile(r"删除|清空"), "deletion is not supported"),
    (re.compile(r"所有人.*会议|批量"), "bulk operations are not supported"),
    (
        re.compile(
            r"\b(select\s+.+\s+from|insert\s+into|update\s+\S+\s+set|create\s+(table|database|user|index)|alter\s+(table|database|user)|union\s+select)\b",
            re.IGNORECASE,
        ),
        "SQL commands are not supported",
    ),
    (
        re.compile(r"\b(get|post|put|patch|delete)\s+https?://", re.IGNORECASE),
        "arbitrary HTTP requests are not supported",
    ),
)


def validate_draft(draft: MeetingDraft) -> MeetingDraft:
    if not draft.title.strip():
        raise ValidationError("title must not be blank")
    if not draft.attendee_ids:
        raise ValidationError("at least one attendee is required")
    if len(set(draft.attendee_ids)) != len(draft.attendee_ids):
        raise ValidationError("attendees must be unique")
    return draft


def authorize_query(actor: Actor, meeting: Meeting) -> bool:
    if actor.id != meeting.organizer_id and actor.id not in meeting.attendee_ids:
        raise AuthorizationError("meeting is not visible to this actor")
    return True


def authorize_update(actor: Actor, meeting: Meeting, patch: MeetingPatch) -> bool:
    del patch
    if actor.id != meeting.organizer_id:
        raise AuthorizationError("only the organizer may update a meeting")
    return True


def classify_unsafe_request(message: str) -> str | None:
    return next((reason for pattern, reason in _UNSAFE_PATTERNS if pattern.search(message)), None)


def confirmation_hash(actor_id: str, action: str, payload: MeetingDraft | MeetingPatch) -> str:
    canonical = json.dumps(
        {
            "actor_id": actor_id,
            "action": action,
            "payload": payload.model_dump(mode="json", exclude_none=True),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
