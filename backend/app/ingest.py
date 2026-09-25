"""Event ingest. P3.

Validate against the spec schema, append to the SQLite event log, then fold
into the graph. The event log is append-only and is the source of truth — the
networkx graph is a derived view and must be rebuildable from it.

That separation matters for the benchmarks: replaying a log has to reproduce
the graph exactly, or precision/recall numbers are not reproducible.
"""


def ingest(event: dict) -> None:
    raise NotImplementedError("P3")
