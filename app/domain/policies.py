import json
import re
from hashlib import sha256

from app.domain.errors import AuthorizationError, ValidationError
from app.domain.models import Actor, ImmutableModel, Meeting, MeetingDraft, MeetingPatch

_UNSAFE_PATTERNS = (
    (
        re.compile(
            r"(?:删除|删掉|移除).*(?:所有人|所有|全部|批量|别人|其他人|大家)"
            r"|(?:所有人|所有|全部|批量|别人|其他人|大家).*(?:删除|删掉|删了|移除)"
            r"|(?:都|全).*(?:删|移除)",
            re.IGNORECASE,
        ),
        "不支持批量删除",
    ),
    (
        re.compile(
            r"\b(?:delete|remove|clear)\s+(?:all|every)\b|\bbulk\s+delete\b"
            r"|\bclear\s+meetings?\b",
            re.IGNORECASE,
        ),
        "不支持批量删除",
    ),
    (re.compile(r"清空", re.IGNORECASE), "不支持批量删除"),
    (
        re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
        "不支持数据库命令",
    ),
    (re.compile(r"\bdrop\b|\btruncate\b", re.IGNORECASE), "不支持数据库命令"),
    (re.compile(r"所有人.*会议|批量"), "不支持批量操作"),
    (
        re.compile(
            r"\b(select\s+.+\s+from|insert\s+into|update\s+\S+\s+set|create\s+(table|database|user|index)|alter\s+(table|database|user)|union\s+select)\b",
            re.IGNORECASE,
        ),
        "不支持 SQL 命令",
    ),
    (
        re.compile(r"\b(get|post|put|patch|delete)\s+https?://", re.IGNORECASE),
        "不支持任意 HTTP 请求",
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


def authorize_delete(actor: Actor, meeting: Meeting) -> bool:
    if actor.id != meeting.organizer_id:
        raise AuthorizationError("only the organizer may delete a meeting")
    return True


def classify_unsafe_request(message: str) -> str | None:
    return next((reason for pattern, reason in _UNSAFE_PATTERNS if pattern.search(message)), None)


def confirmation_hash(actor_id: str, action: str, payload: ImmutableModel) -> str:
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
