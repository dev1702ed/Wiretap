"""Ingest: validate the whole batch, append it, fold it in. And reproducibility:
the graph is a derived view, so replaying the log must rebuild it exactly."""

import random

import pytest

from app.graph import build
from app.ingest import Ingestor, InvalidEvents
from app.store import EventStore

PG = "postgres://localhost:5432"
ORDERS = (PG, "dcp.public.orders")
SUMMARY = (PG, "dcp.public.summary")


@pytest.fixture
def ingestor(tmp_path):
    store = EventStore(tmp_path / "events.db")
    yield Ingestor(store)
    store.close()


def test_valid_batch_is_accepted(ingestor, ev):
    batch = [ev("r", "read", ORDERS), ev("w", "write", SUMMARY, parent=["r"])]
    assert ingestor.ingest(batch) == 2
    assert ingestor.store.replay() == batch
    assert ingestor.graph.dataset_edges() == {(ORDERS, SUMMARY, "job.py")}


def test_single_event_is_accepted(ingestor, ev):
    assert ingestor.ingest(ev("r", "read", ORDERS)) == 1
    assert ingestor.graph.datasets() == {ORDERS}


def test_invalid_batch_is_rejected_with_nothing_stored(ingestor, ev):
    bad = ev("w", "write", SUMMARY, parent=["r"])
    bad["op"] = "delete"
    with pytest.raises(InvalidEvents) as exc_info:
        ingestor.ingest([ev("r", "read", ORDERS), bad])
    assert [error["index"] for error in exc_info.value.errors] == [1]
    assert ingestor.store.replay() == []
    assert ingestor.graph.event_count() == 0
    assert ingestor.graph.datasets() == set()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("edge_id"),
        lambda e: e.pop("dataset"),
        lambda e: e["dataset"].pop("name"),
        lambda e: e["job"].pop("name"),
        lambda e: e.update(dcp_version="0.2"),
        lambda e: e.update(parent="r"),  # a list, not a string
        lambda e: e.update(extra=1),  # additionalProperties: false
    ],
)
def test_schema_violations_are_rejected(ingestor, ev, mutate):
    event = ev("w", "write", SUMMARY)
    mutate(event)
    with pytest.raises(InvalidEvents):
        ingestor.ingest([event])
    assert ingestor.store.replay() == []


def test_non_object_in_batch_is_rejected(ingestor, ev):
    with pytest.raises(InvalidEvents):
        ingestor.ingest([ev("r", "read", ORDERS), "not an event"])
    assert ingestor.store.replay() == []


def test_replaying_the_log_rebuilds_the_graph_exactly(tmp_path, ev):
    """Incremental ingest, in shuffled batches, children before parents, then
    build(replay()): identical. So is a restarted Ingestor on the same log."""
    events = [
        ev("r-orders", "read", ORDERS, "enrich.py"),
        ev(
            "w-topic",
            "write",
            ("kafka://localhost:9092", "t"),
            "enrich.py",
            ["r-orders"],
        ),
        ev("r-topic", "read", ("kafka://localhost:9092", "t"), "load.py", ["w-topic"]),
        ev("w-summary", "write", SUMMARY, "load.py", ["r-topic", "missing"]),
        ev("r-s", "read", SUMMARY, "fix.py"),
        ev("w-s", "write", SUMMARY, "fix.py", ["r-s"]),
    ]
    random.Random(7).shuffle(events)
    path = tmp_path / "events.db"
    store = EventStore(path)
    ingestor = Ingestor(store)
    ingestor.ingest(events[:2])
    ingestor.ingest(events[2])
    ingestor.ingest(events[3:])
    ingestor.ingest(events[:1])  # a retried POST: stored twice, folded in once

    rebuilt = build(store.replay())
    assert rebuilt == ingestor.graph
    assert rebuilt.dangling_parents() == ingestor.graph.dangling_parents() == {"missing"}
    for ds in rebuilt.datasets():
        assert rebuilt.upstream(ds) == ingestor.graph.upstream(ds)
        assert rebuilt.dataset_upstream(ds) == ingestor.graph.dataset_upstream(ds)
        assert rebuilt.downstream(ds) == ingestor.graph.downstream(ds)
    store.close()

    reopened = EventStore(path)
    assert Ingestor(reopened).graph == ingestor.graph
    reopened.close()
