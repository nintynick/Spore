"""Durable storage for signed control-plane events."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .control import SignedControlEvent

CONTROL_SCHEMA = """
CREATE TABLE IF NOT EXISTS control_event (
    event_id   TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    timestamp  INTEGER NOT NULL,
    payload    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_control_event_timestamp
ON control_event(timestamp, event_id);
"""


class ControlStore:
    """SQLite-backed store for replayable signed control events."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(CONTROL_SCHEMA)

    def close(self):
        self.conn.close()

    def store(self, event: SignedControlEvent) -> bool:
        """Persist an event. Returns True if it was newly inserted."""
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO control_event (event_id, type, node_id, timestamp, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.type,
                event.node_id,
                event.timestamp,
                json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")),
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list_since(self, since_timestamp: int = 0) -> list[SignedControlEvent]:
        rows = self.conn.execute(
            """
            SELECT payload
            FROM control_event
            WHERE timestamp > ?
            ORDER BY timestamp ASC, event_id ASC
            """,
            (since_timestamp,),
        ).fetchall()
        return [SignedControlEvent.from_json(row["payload"]) for row in rows]

    def latest_timestamp(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(timestamp), 0) AS ts FROM control_event"
        ).fetchone()
        return int(row["ts"]) if row else 0
