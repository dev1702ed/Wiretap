"""Edge parenting within one process.

The rules, from CLAUDE.md / spec: reads in one statement never feed each other;
a write is parented to the reads in its own statement when there are any, and
otherwise to the latest read of each dataset earlier in the flow (job-level).
"""

from dcp.interceptors.postgres import _capture


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class FakeCursor:
    connection = _Conn()


def run(sql: str) -> None:
    _capture(FakeCursor(), sql)


def by_op(events, op, name):
    return [e for e in events if e["op"] == op and e["dataset"]["name"] == name]


def test_ddl_emits_nothing(events):
    run("CREATE TABLE IF NOT EXISTS orders (id int)")
    assert events == []


def test_join_reads_do_not_chain(events):
    run("SELECT o.id FROM orders o JOIN summary s ON o.id = s.id")
    assert [e["op"] for e in events] == ["read", "read"]
    assert all(e["parent"] == [] for e in events)


def test_insert_select_write_parented_to_its_own_read_only(events):
    run("SELECT id FROM customers")  # earlier, unrelated read
    run("INSERT INTO summary SELECT id FROM orders")
    (orders_read,) = by_op(events, "read", "dcp.public.orders")
    (summary_write,) = by_op(events, "write", "dcp.public.summary")
    assert summary_write["parent"] == [orders_read["edge_id"]]


def test_insert_values_is_job_level(events):
    run("SELECT id FROM orders")
    run("SELECT id FROM customers")
    run("INSERT INTO summary VALUES (1, 10)")
    reads = {e["dataset"]["name"]: e["edge_id"] for e in events if e["op"] == "read"}
    (write,) = by_op(events, "write", "dcp.public.summary")
    assert sorted(write["parent"]) == sorted(reads.values())


def test_job_level_keeps_only_latest_read_per_dataset(events):
    """Bounded: a script polling one table keeps one parent, not one per poll."""
    run("SELECT id FROM orders")
    run("SELECT id FROM orders")
    run("INSERT INTO summary VALUES (1, 10)")
    orders_reads = by_op(events, "read", "dcp.public.orders")
    (write,) = by_op(events, "write", "dcp.public.summary")
    assert write["parent"] == [orders_reads[-1]["edge_id"]]


def test_one_flow_shares_one_trace(events):
    run("SELECT id FROM orders")
    run("INSERT INTO summary VALUES (1, 10)")
    assert len({e["trace_id"] for e in events}) == 1


def test_names_include_the_database(events):
    """Spec: Postgres datasets are db.schema.table, the db from the connection."""
    run("SELECT id FROM orders JOIN sales.refunds USING (id)")
    assert [e["dataset"]["name"] for e in events] == ["dcp.public.orders", "dcp.sales.refunds"]


def test_named_catalog_is_not_prefixed_twice(events):
    """A query that names the database already has three parts, and one table
    named two ways is still one dataset."""
    run("SELECT id FROM other.public.orders")
    run("SELECT o.id FROM orders o JOIN dcp.public.orders p USING (id)")
    assert [e["dataset"]["name"] for e in events] == ["other.public.orders", "dcp.public.orders"]


def test_unquoted_identifiers_fold_to_one_dataset(events):
    """Postgres folds unquoted identifiers: Orders and orders are one table."""
    run("SELECT id FROM Orders")
    run("SELECT id FROM orders")
    assert {e["dataset"]["name"] for e in events} == {"dcp.public.orders"}


def test_quoted_identifier_keeps_its_case(events):
    run('SELECT id FROM "Orders"')
    assert [e["dataset"]["name"] for e in events] == ["dcp.public.Orders"]


def test_unquoted_schema_and_table_both_fold(events):
    run("SELECT id FROM Sales.Orders")
    assert [e["dataset"]["name"] for e in events] == ["dcp.sales.orders"]


def test_quoted_name_with_a_dot_is_still_prefixed(events):
    """Qualification follows the parsed structure, not the dots in the name."""
    run('SELECT id FROM "a.b"')
    run('SELECT id FROM "x.y"."a.b"')
    assert [e["dataset"]["name"] for e in events] == ["dcp.public.a.b", "dcp.x.y.a.b"]
