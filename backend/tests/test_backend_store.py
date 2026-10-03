"""The SQLite event log: append-only, replayed in ingest order."""

import pytest

from app.store import DEFAULT_PATH, EventStore


def test_append_replay_round_trip_in_order(tmp_path, ev):
    store = EventStore(tmp_path / "events.db")
    events = [ev(f"e{i}", "read", ("postgres://localhost:5432", f"t{i}")) for i in range(20)]
    for event in events:
        store.append(event)
    assert store.replay() == events
    store.close()


def test_batch_append_keeps_order_across_batches(tmp_path, ev):
    store = EventStore(tmp_path / "events.db")
    first = [ev("a", "read", ("ns", "x")), ev("b", "read", ("ns", "y"))]
    second = [ev("c", "read", ("ns", "z"))]
    store.append_many(first)
    store.append_many(second)
    assert [e["edge_id"] for e in store.replay()] == ["a", "b", "c"]
    store.close()


def test_failed_batch_stores_nothing(tmp_path, ev):
    store = EventStore(tmp_path / "events.db")
    with pytest.raises(TypeError):
        store.append_many([ev("a", "read", ("ns", "x")), {"not": object()}])
    assert store.replay() == []
    store.close()


def test_log_survives_reopen(tmp_path, ev):
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.append(ev("a", "read", ("ns", "x")))
    store.close()
    reopened = EventStore(path)
    assert [e["edge_id"] for e in reopened.replay()] == ["a"]
    reopened.close()


def test_path_from_environment(tmp_path, monkeypatch):
    path = tmp_path / "from_env.db"
    monkeypatch.setenv("DCP_DB_PATH", str(path))
    store = EventStore()
    assert store.path == str(path)
    assert path.exists()
    store.close()


def test_default_path(tmp_path, monkeypatch):
    monkeypatch.delenv("DCP_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)  # the default is relative; keep it out of the repo
    store = EventStore()
    assert store.path == DEFAULT_PATH == "dcp_events.db"
    assert (tmp_path / DEFAULT_PATH).exists()
    store.close()
