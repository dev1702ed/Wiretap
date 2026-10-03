"""Event ingest. P3.

Validate against the spec schema, append to the SQLite event log, then fold
into the graph. The event log is append-only and is the source of truth — the
networkx graph is a derived view and must be rebuildable from it.

That separation matters for the benchmarks: replaying a log has to reproduce
the graph exactly, or precision/recall numbers are not reproducible.
"""

import json
import pathlib
import threading

import jsonschema

from app.graph import LineageGraph, build
from app.store import EventStore

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "spec" / "envelope.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
_validator = jsonschema.Draft202012Validator(SCHEMA)


class InvalidEvents(ValueError):
    """A batch failed validation. Nothing from it was stored."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__(f"{len(errors)} invalid event(s)")
        self.errors = errors


def validate(events: list) -> list[dict]:
    """Return one {"index", "error"} entry per schema violation; [] if all valid."""
    return [
        {"index": index, "error": error.message}
        for index, event in enumerate(events)
        for error in _validator.iter_errors(event)
    ]


class Ingestor:
    """Owns the store and the graph built from it.

    On construction the graph is rebuilt by replaying the store, so a
    restarted backend answers exactly as it did before. One lock covers
    append-then-fold and every read of the graph: request handlers run in a
    thread pool, and networkx structures are not thread-safe.
    """

    def __init__(self, store: EventStore) -> None:
        self.store = store
        self.lock = threading.RLock()
        self.graph: LineageGraph = build(store.replay())

    def ingest(self, events: dict | list) -> int:
        """Accept one event or a batch, atomically. Returns the number accepted.

        The whole batch is validated before anything is appended, so a batch
        is either stored and folded in whole, or rejected with nothing stored.
        """
        batch = [events] if isinstance(events, dict) else list(events)
        errors = validate(batch)
        if errors:
            raise InvalidEvents(errors)
        with self.lock:
            self.store.append_many(batch)
            for event in batch:
                self.graph.add(event)
        return len(batch)
