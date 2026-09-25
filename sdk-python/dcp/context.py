"""In-process propagation via contextvars. P1–P2.

This is what links a read to the write that follows it. A script reads `orders`
then produces to Kafka; both events share the trace, so the edge links with no
application involvement.

contextvars (not thread-locals) because it survives async/await correctly.
Known hazard, documented in the OTel context-propagation literature: work
dispatched to a ThreadPoolExecutor does NOT inherit context automatically.
That is a real gap to test for in P2, not an edge case.
"""

from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("dcp_trace_id", default=None)
_inbound: ContextVar[tuple[str, ...]] = ContextVar("dcp_inbound", default=())


def current_trace_id() -> str | None:
    return _trace_id.get()


def ensure_trace() -> str:
    """Return the active trace_id, starting a new flow if none exists."""
    from dcp.envelope import new_id

    tid = _trace_id.get()
    if tid is None:
        tid = new_id()
        _trace_id.set(tid)
    return tid


def set_trace(trace_id: str) -> None:
    """Adopt an inbound trace_id extracted from a hop. P2."""
    _trace_id.set(trace_id)


def set_inbound(edge_ids: list[str]) -> None:
    """Adopt upstream edge ids extracted from a hop (SQL comment, Kafka header). P2."""
    _inbound.set(list(edge_ids))


def inbound() -> list[str]:
    """Upstream edges from a prior hop, if this process received context. P2."""
    return list(_inbound.get())
