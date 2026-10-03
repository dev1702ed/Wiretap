"""patch_psycopg's wrapper, against a fake psycopg module. No database needed.

The wrapper is the one place DCP touches the caller's call path, so its
monitor-only contract is tested directly: the query still runs, the caller gets
psycopg's return value back, capture happens, and a DCP failure never escapes.
"""

import sys
import types

import pytest

from dcp import config
from dcp.interceptors import postgres
from dcp.propagation.sqlcomment import extract


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


@pytest.fixture
def cursor_cls(monkeypatch):
    """A fresh fake psycopg.Cursor per test, with patch_psycopg applied to it."""

    class Cursor:
        connection = _Conn()

        def execute(self, query, params=None, **kwargs):
            self.sent = query
            return self  # psycopg returns the cursor, enabling .fetchall() chaining

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(Cursor=Cursor))
    monkeypatch.setattr(postgres, "_patched", False)
    postgres.patch_psycopg()
    return Cursor


def test_returns_what_psycopg_returns(cursor_cls, events):
    cur = cursor_cls()
    assert cur.execute("SELECT id FROM orders") is cur


def test_captures_the_query(cursor_cls, events):
    cursor_cls().execute("SELECT id FROM orders")
    (read,) = events
    assert read["op"] == "read" and read["dataset"]["name"] == "dcp.public.orders"


def test_kill_switch_calls_straight_through(cursor_cls, events, monkeypatch):
    """capture=False (DCP_CAPTURE=off): the wrapper stays, captures nothing,
    and sends the query untouched even with the SQL comment opted in."""
    monkeypatch.setattr(config, "_capture", False)
    monkeypatch.setattr(config, "_propagate_sql", True)
    cur = cursor_cls()
    assert cur.execute("SELECT id FROM orders") is cur
    assert cur.sent == "SELECT id FROM orders"
    assert events == []


def test_capture_failure_never_reaches_the_caller(cursor_cls, events, monkeypatch):
    def boom(_):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(postgres, "_classify_parts", boom)
    cur = cursor_cls()
    assert cur.execute("SELECT id FROM orders") is cur
    assert events == []


def test_sends_trace_comment_only_when_opted_in(cursor_cls, events, monkeypatch):
    cur = cursor_cls()
    cur.execute("SELECT id FROM orders")
    assert cur.sent == "SELECT id FROM orders"

    monkeypatch.setattr(config, "_propagate_sql", True)
    cur.execute("SELECT id FROM orders")
    trace_id, _ = extract(cur.sent)
    assert trace_id == events[-1]["trace_id"]


# P5.1 O2: the connection's identity is read once per connection


class _CountingInfo:
    def __init__(self, host="localhost", port=5432, dbname="dcp"):
        self._values = {"host": host, "port": port, "dbname": dbname}
        self.reads = 0

    def __getattr__(self, name):
        if name.startswith("_") or name == "reads":
            raise AttributeError(name)
        self.reads += 1
        return self._values[name]


class _CountingConn:
    def __init__(self, **kwargs):
        self.info = _CountingInfo(**kwargs)


def _cursor(conn):
    class Cursor:
        connection = conn

        def execute(self, query, params=None, **kwargs):
            return self

    return Cursor()


def test_identity_is_read_once_per_connection(events):
    conn = _CountingConn()
    for _ in range(5):
        postgres._capture(_cursor(conn), "SELECT id FROM orders JOIN refunds ON true")
    assert conn.info.reads == 3  # host, port, dbname: once, not per event
    assert {e["dataset"]["name"] for e in events} == {"dcp.public.orders", "dcp.public.refunds"}
    assert {e["dataset"]["namespace"] for e in events} == {"postgres://localhost:5432"}


def test_each_connection_keeps_its_own_identity(events):
    a, b = _CountingConn(dbname="one"), _CountingConn(host="db2", port=6543, dbname="two")
    postgres._capture(_cursor(a), "SELECT id FROM orders")
    postgres._capture(_cursor(b), "SELECT id FROM orders")
    postgres._capture(_cursor(a), "SELECT id FROM orders")
    assert [(e["dataset"]["namespace"], e["dataset"]["name"]) for e in events] == [
        ("postgres://localhost:5432", "one.public.orders"),
        ("postgres://db2:6543", "two.public.orders"),
        ("postgres://localhost:5432", "one.public.orders"),
    ]


def test_a_connection_is_not_kept_alive_by_the_cache(events):
    import gc
    import weakref

    conn = _CountingConn()
    postgres._capture(_cursor(conn), "SELECT id FROM orders")
    ref = weakref.ref(conn)
    del conn
    gc.collect()
    assert ref() is None


def test_a_connection_that_cannot_be_weakly_referenced_is_read_every_time(events):
    class Slotted:
        __slots__ = ("info",)

    conn = Slotted()
    conn.info = _CountingInfo()
    postgres._capture(_cursor(conn), "SELECT id FROM orders")
    postgres._capture(_cursor(conn), "SELECT id FROM orders")
    assert conn.info.reads == 6
    assert [e["dataset"]["name"] for e in events] == ["dcp.public.orders"] * 2
