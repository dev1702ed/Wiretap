"""SQLite append-only event log. P3. Source of truth; the graph is derived."""


def append(event: dict) -> None:
    raise NotImplementedError("P3")


def replay() -> list[dict]:
    """Return every event in ingest order, for graph rebuild and benchmarks."""
    raise NotImplementedError("P3")
