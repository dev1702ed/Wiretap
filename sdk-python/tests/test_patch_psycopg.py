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


def test_capture_failure_never_reaches_the_caller(cursor_cls, events, monkeypatch):
    def boom(_):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(postgres, "_classify", boom)
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
