"""Shared fixtures.

Every capture test runs against an in-memory emitter, and every event it
captures is validated against spec/envelope.schema.json. That makes the
schema-conformance guarantee cover all emitted events, not one hand-built one.
"""

import json
import pathlib

import jsonschema
import pytest

from dcp import config, context
from dcp.emitters.base import Emitter

SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[2] / "spec" / "envelope.schema.json").read_text()
)


class ListEmitter(Emitter):
    """Captures events in memory and schema-checks each one on arrival."""

    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event) -> None:
        d = event.to_dict()
        jsonschema.validate(d, SCHEMA)
        self.events.append(d)

    def flush(self, timeout: float = 5.0) -> None:
        return None


@pytest.fixture(autouse=True)
def fresh_context():
    """Isolate contextvars between tests: each test starts a new flow."""
    tokens = [
        (context._trace_id, context._trace_id.set(None)),
        (context._inbound, context._inbound.set(())),
        (context._reads, context._reads.set(None)),
    ]
    yield
    for var, token in reversed(tokens):
        var.reset(token)


@pytest.fixture
def events(monkeypatch) -> list[dict]:
    """Install a capturing emitter and a fixed job identity; return the event list."""
    emitter = ListEmitter()
    monkeypatch.setattr(config, "_emitter", emitter)
    monkeypatch.setattr(config, "_job", config.JobIdentity("test_job.py", "test-host", 1))
    return emitter.events
