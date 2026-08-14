from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.domain.errors import ConflictError
from app.domain.models import Actor, Meeting, MeetingDraft, MeetingPatch


class MeetingRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = str(database_path)
        with self._connect() as connection:
            schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
            connection.executescript(schema)

    def list_for_actor(self, actor: Actor) -> list[Meeting]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM meetings WHERE organizer_id = ? OR attendee_ids LIKE ? ORDER BY start_at, id",
                (actor.id, f'%"{actor.id}"%'),
            ).fetchall()
        return [self._to_meeting(row) for row in rows if self._is_visible(actor, row)]

    def find_visible(self, actor: Actor, meeting_id: str) -> Meeting | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
        return self._to_meeting(row) if row is not None and self._is_visible(actor, row) else None

    def create(self, organizer_id: str, draft: MeetingDraft, idempotency_key: str) -> Meeting:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM meetings WHERE organizer_id = ? AND idempotency_key = ?",
                (organizer_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return self._to_meeting(existing)
            meeting = Meeting(
                id=str(uuid4()),
                organizer_id=organizer_id,
                version=1,
                idempotency_key=idempotency_key,
                **draft.model_dump(),
            )
            connection.execute(
                """INSERT INTO meetings (
                    id, organizer_id, title, start_at, end_at, attendee_ids, room_id,
                    required_features, version, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._values(meeting),
            )
        return meeting

    def update(
        self, organizer_id: str, meeting_id: str, patch: MeetingPatch, expected_version: int
    ) -> Meeting:
        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise ConflictError("meeting update must include at least one change")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
            if (
                row is None
                or row["organizer_id"] != organizer_id
                or row["version"] != expected_version
            ):
                raise ConflictError("meeting was changed or is unavailable")
            current = self._to_meeting(row)
            candidate = current.model_copy(update=changes)
            if candidate.end_at <= candidate.start_at:
                raise ConflictError("updated meeting interval is invalid")
            updated = candidate.model_copy(update={"version": current.version + 1})
            result = connection.execute(
                """UPDATE meetings SET title = ?, start_at = ?, end_at = ?, attendee_ids = ?, room_id = ?,
                   required_features = ?, version = ? WHERE id = ? AND organizer_id = ? AND version = ?""",
                (
                    updated.title,
                    updated.start_at.isoformat(),
                    updated.end_at.isoformat(),
                    json.dumps(updated.attendee_ids),
                    updated.room_id,
                    json.dumps(updated.required_features),
                    updated.version,
                    meeting_id,
                    organizer_id,
                    expected_version,
                ),
            )
            if result.rowcount != 1:
                raise ConflictError("meeting was changed or is unavailable")
        return updated

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _is_visible(actor: Actor, row: sqlite3.Row) -> bool:
        return actor.id == row["organizer_id"] or actor.id in json.loads(row["attendee_ids"])

    @staticmethod
    def _values(meeting: Meeting) -> tuple[object, ...]:
        return (
            meeting.id,
            meeting.organizer_id,
            meeting.title,
            meeting.start_at.isoformat(),
            meeting.end_at.isoformat(),
            json.dumps(meeting.attendee_ids),
            meeting.room_id,
            json.dumps(meeting.required_features),
            meeting.version,
            meeting.idempotency_key,
        )

    @staticmethod
    def _to_meeting(row: sqlite3.Row) -> Meeting:
        return Meeting(
            id=row["id"],
            organizer_id=row["organizer_id"],
            title=row["title"],
            start_at=datetime.fromisoformat(row["start_at"]),
            end_at=datetime.fromisoformat(row["end_at"]),
            attendee_ids=tuple(json.loads(row["attendee_ids"])),
            room_id=row["room_id"],
            required_features=tuple(json.loads(row["required_features"])),
            version=row["version"],
            idempotency_key=row["idempotency_key"],
        )
