"""SQLite append-only event log. P3. Source of truth; the graph is derived.

Events are stored as the JSON they arrived as, under an autoincrement id, and
replayed in that order. Nothing is ever updated or deleted.
"""

import json
import os
import sqlite3
import threading

DEFAULT_PATH = "dcp_events.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT    NOT NULL
)
"""


class EventStore:
    """The event log. Path: the argument, else $DCP_DB_PATH, else dcp_events.db."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = os.fspath(path or os.environ.get("DCP_DB_PATH") or DEFAULT_PATH)
        # One connection shared across request threads, serialised by a lock.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(_SCHEMA)

    def append(self, event: dict) -> None:
        """Store one event."""
        self.append_many([event])

    def append_many(self, events: list[dict]) -> None:
        """Store a batch in one transaction: all of it, or none of it."""
        rows = [(json.dumps(event),) for event in events]
        with self._lock, self._conn:
            self._conn.executemany("INSERT INTO events (event) VALUES (?)", rows)

    def replay(self) -> list[dict]:
        """Return every event in ingest order, for graph rebuild and benchmarks."""
        with self._lock:
            rows = self._conn.execute("SELECT event FROM events ORDER BY id").fetchall()
        return [json.loads(event) for (event,) in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
