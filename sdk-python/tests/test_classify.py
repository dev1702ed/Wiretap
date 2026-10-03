"""SQL classification: which statements produce edges, and in which direction.

Pure string-in, tuple-out. No database needed, so these run in CI and guard
the precision of every edge DCP emits.
"""

import pytest

from dcp.interceptors.postgres import _classify, _sql_text


@pytest.mark.parametrize(
    "query,reads,writes",
    [
        ("SELECT id FROM orders", ["public.orders"], []),
        (
            "INSERT INTO summary SELECT id FROM orders",
            ["public.orders"],
            ["public.summary"],
        ),
        (
            "SELECT o.id FROM orders o JOIN summary s ON o.id = s.id",
            ["public.orders", "public.summary"],
            [],
        ),
        (
            "CREATE TABLE derived AS SELECT id FROM orders",
            ["public.orders"],
            ["public.derived"],
        ),
        ("INSERT INTO summary VALUES (1, 10)", [], ["public.summary"]),
        (
            "UPDATE summary SET total = 0 WHERE id IN (SELECT id FROM orders)",
            ["public.orders"],
            ["public.summary"],
        ),
        ("DELETE FROM summary WHERE id = 1", [], ["public.summary"]),
        ("SELECT id FROM sales.orders", ["sales.orders"], []),
        # A CTE is not a table: its name is never a dataset (P5)
        ("WITH x AS (SELECT id FROM orders) SELECT id FROM x", ["public.orders"], []),
        (
            "WITH x AS (SELECT id FROM orders) INSERT INTO summary SELECT id, 1 FROM x",
            ["public.orders"],
            ["public.summary"],
        ),
        (
            (
                "WITH a AS (SELECT id FROM orders), b AS (SELECT a.id FROM a JOIN refunds r"
                " ON r.id = a.id) SELECT id FROM b"
            ),
            ["public.orders", "public.refunds"],
            [],
        ),
        (
            (
                "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 3)"
                " SELECT n FROM t"
            ),
            [],
            [],
        ),
        # ... but a schema-qualified name is the table, even when a CTE shares it
        (
            "WITH orders AS (SELECT 1 AS id) SELECT id FROM public.orders",
            ["public.orders"],
            [],
        ),
        ('WITH "X" AS (SELECT id FROM orders) SELECT id FROM x', ["public.x", "public.orders"], []),
    ],
)
def test_classify_data_movement(query, reads, writes):
    assert _classify(query) == (reads, writes)


@pytest.mark.parametrize(
    "query",
    [
        "CREATE TABLE IF NOT EXISTS orders (id int, total numeric)",
        "DROP TABLE orders",
        "ALTER TABLE orders ADD COLUMN note text",
        "BEGIN",
        "this is not sql at all ((",
    ],
)
def test_classify_ignores_statements_that_move_no_data(query):
    """DDL, transaction control, and unparseable text must produce no edges."""
    assert _classify(query) == ([], [])


def test_sql_text_handles_every_query_form():
    """str, bytes, and psycopg.sql.Composed-style objects all yield SQL text."""

    class FakeComposed:
        def as_string(self, context):
            return "SELECT id FROM orders"

    assert _sql_text(None, "SELECT 1") == "SELECT 1"
    assert _sql_text(None, b"SELECT 1") == "SELECT 1"
    assert _sql_text(None, FakeComposed()) == "SELECT id FROM orders"
