"""Shared fixtures. Events are built by hand, so the backend is tested without
the SDK; only the wire-contract tests import it."""

import pytest

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"


def make_event(
    edge_id: str,
    op: str,
    dataset: tuple[str, str],
    job: str = "job.py",
    parent: list[str] | tuple[str, ...] = (),
    trace_id: str = "trace-1",
) -> dict:
    """One schema-valid envelope."""
    return {
        "dcp_version": "0.1",
        "trace_id": trace_id,
        "edge_id": edge_id,
        "parent": list(parent),
        "op": op,
        "dataset": {"namespace": dataset[0], "name": dataset[1]},
        "job": {"name": job, "host": "test-host", "pid": 1},
        "ts": "2026-09-16T02:11:04+00:00",
    }


@pytest.fixture
def ev():
    """The event builder: ev(edge_id, op, dataset, job=..., parent=...)."""
    return make_event
