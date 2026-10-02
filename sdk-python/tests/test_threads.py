"""Context across ThreadPoolExecutor dispatch — the known contextvars hazard."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from dcp.context import current_trace_id, ensure_trace
from dcp.interceptors.postgres import _capture
from dcp.interceptors.threads import patch_threadpool


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class FakeCursor:
    connection = _Conn()


def test_context_survives_threadpool_dispatch():
    """Workers join the submitter's trace instead of minting their own."""
    patch_threadpool()
    main = ensure_trace()
    with ThreadPoolExecutor(max_workers=2) as pool:
        traces = list(pool.map(lambda _: current_trace_id(), range(4)))
    assert traces == [main] * 4


def test_workers_share_one_trace_when_submitter_had_none():
    patch_threadpool()
    with ThreadPoolExecutor(max_workers=2) as pool:
        traces = set(pool.map(lambda _: ensure_trace(), range(4)))
    assert len(traces) == 1


@pytest.mark.xfail(
    reason="Known limitation: context copy is one-way, so worker reads don't "
    "parent writes made after the pool returns",
    strict=True,
)
def test_worker_reads_parent_later_writes(events):
    patch_threadpool()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda q: _capture(FakeCursor(), q),
                ["SELECT id FROM orders", "SELECT id FROM refunds"],
            )
        )
    _capture(FakeCursor(), "INSERT INTO summary VALUES (1, 1)")
    (write,) = [e for e in events if e["op"] == "write"]
    reads = [e["edge_id"] for e in events if e["op"] == "read"]
    assert sorted(write["parent"]) == sorted(reads)
