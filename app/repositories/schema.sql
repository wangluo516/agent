CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    organizer_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    attendee_ids TEXT NOT NULL,
    room_id TEXT,
    required_features TEXT NOT NULL,
    version INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    UNIQUE (organizer_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS meetings_organizer_idx ON meetings (organizer_id);
