"""SQL comment injection on the way out: opt-in, trace only."""

import pytest

from dcp import config
from dcp.context import ensure_trace
from dcp.interceptors.postgres import _outbound
from dcp.propagation.sqlcomment import extract


@pytest.fixture
def propagation(monkeypatch):
    def set_enabled(on: bool):
        monkeypatch.setattr(config, "_propagate_sql", on)

    return set_enabled


def test_off_by_default_sends_query_unchanged(propagation):
    propagation(False)
    assert _outbound("SELECT 1") == "SELECT 1"


def test_on_carries_trace_only(propagation):
    propagation(True)
    trace = ensure_trace()
    sent = _outbound("SELECT id FROM orders WHERE id = %s")
    assert extract(sent) == (trace, [])
    assert "dcp_parent" not in sent


def test_on_never_adds_a_percent_sign(propagation):
    """A bare % would be read as a placeholder in a parameterised query."""
    propagation(True)
    ensure_trace()
    query = "SELECT id FROM orders WHERE id = %s"
    assert _outbound(query).count("%") == query.count("%")


def test_non_string_queries_pass_through(propagation):
    propagation(True)
    composed = object()
    assert _outbound(composed) is composed
