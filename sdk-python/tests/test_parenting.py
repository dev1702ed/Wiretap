"""Edge parenting within one process.

The rules, from CLAUDE.md / spec: reads in one statement never feed each other;
a write is parented to the reads in its own statement when there are any, and
otherwise to the latest read of each dataset earlier in the flow (job-level).
"""

from dcp.interceptors.postgres import _capture


class _Info:
    host = "localhost"
    port = 5432


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
    (orders_read,) = by_op(events, "read", "public.orders")
    (summary_write,) = by_op(events, "write", "public.summary")
    assert summary_write["parent"] == [orders_read["edge_id"]]


def test_insert_values_is_job_level(events):
    run("SELECT id FROM orders")
    run("SELECT id FROM customers")
    run("INSERT INTO summary VALUES (1, 10)")
    reads = {e["dataset"]["name"]: e["edge_id"] for e in events if e["op"] == "read"}
    (write,) = by_op(events, "write", "public.summary")
    assert sorted(write["parent"]) == sorted(reads.values())


def test_job_level_keeps_only_latest_read_per_dataset(events):
    """Bounded: a script polling one table keeps one parent, not one per poll."""
    run("SELECT id FROM orders")
    run("SELECT id FROM orders")
    run("INSERT INTO summary VALUES (1, 10)")
    orders_reads = by_op(events, "read", "public.orders")
    (write,) = by_op(events, "write", "public.summary")
    assert write["parent"] == [orders_reads[-1]["edge_id"]]


def test_one_flow_shares_one_trace(events):
    run("SELECT id FROM orders")
    run("INSERT INTO summary VALUES (1, 10)")
    assert len({e["trace_id"] for e in events}) == 1
