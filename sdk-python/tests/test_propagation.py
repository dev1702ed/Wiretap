"""Propagation round-trips. P2.

The multi-hop claim lives or dies here.
"""

import os

import pytest

TRACE = "c70006d3-9485-47e3-9dec-ceb473550352"
EDGE_A = "ac64413b-f75e-4bae-9676-4a7e37cd19dc"
EDGE_B = "390385ba-9984-4c60-8b73-719e1f5fafa5"


@pytest.mark.parametrize(
    "query,parents",
    [
        ("SELECT id FROM orders", []),
        ("SELECT id FROM orders", [EDGE_A]),
        ("INSERT INTO summary SELECT id FROM orders", [EDGE_A, EDGE_B]),
        ("SELECT 1;", [EDGE_A]),
        ("SELECT /* existing note */ 1", [EDGE_A]),
    ],
)
def test_sqlcomment_roundtrip(query, parents):
    """inject then extract returns the same trace_id and parents."""
    from dcp.propagation.sqlcomment import extract, inject

    injected = inject(query, TRACE, parents)
    trace_id, recovered = extract(injected)
    assert trace_id == TRACE
    assert recovered == parents


def test_sqlcomment_absent_returns_nothing():
    from dcp.propagation.sqlcomment import extract

    assert extract("SELECT 1") == (None, [])


def test_sqlcomment_rejects_comment_terminator_injection():
    """A malicious parent value must not escape the comment block."""
    from dcp.propagation.sqlcomment import inject

    hostile = inject("SELECT 1", TRACE, ["*/ DROP TABLE users --"])
    assert hostile == inject("SELECT 1", TRACE, [])
    assert "DROP TABLE" not in hostile


@pytest.mark.skipif(
    not os.environ.get("DCP_TEST_PG"),
    reason="needs live Postgres; set DCP_TEST_PG to the connection string",
)
def test_sqlcomment_does_not_alter_semantics():
    """An injected query returns identical results to the original."""
    import psycopg

    from dcp.propagation.sqlcomment import inject

    query = "SELECT 1 AS n, 'x' AS s"
    with psycopg.connect(os.environ["DCP_TEST_PG"]) as conn:
        plain = conn.execute(query).fetchall()
        commented = conn.execute(inject(query, TRACE, [EDGE_A])).fetchall()
    assert plain == commented


# @pytest.mark.xfail(reason="P2", strict=True)
def test_kafka_header_roundtrip():
    from dcp.propagation.kafka_header import extract, inject

    assert extract(inject(None, TRACE, [EDGE_A, EDGE_B])) == (TRACE, [EDGE_A, EDGE_B])


def test_kafka_header_preserves_caller_headers():
    from dcp.propagation.kafka_header import HEADER_KEY, inject

    headers = inject([("app", b"1")], TRACE, [EDGE_A])
    assert ("app", b"1") in headers
    assert sum(k == HEADER_KEY for k, _ in headers) == 1


def test_kafka_header_rejects_malformed():
    from dcp.propagation.kafka_header import HEADER_KEY, extract, inject

    assert extract([(HEADER_KEY, b"{not json")]) == (None, [])
    assert extract(inject(None, TRACE, ["*/ DROP"])) == (TRACE, [])


@pytest.mark.xfail(reason="P2", strict=True)
def test_context_survives_threadpool_dispatch():
    """Known contextvars hazard — work dispatched to a ThreadPoolExecutor does
    not inherit context automatically. Documented failure mode in the OTel
    propagation literature. Test it; do not assume it works."""
    raise NotImplementedError("P2")
