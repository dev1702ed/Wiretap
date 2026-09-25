"""Lineage graph over networkx. P3.

In-memory, no persistence beyond the event log. Per the spec, this is
explicitly a prototype choice — document what breaks at what scale rather than
pretending it scales.
"""


def add_edge(upstream: str, downstream: str, **attrs) -> None:
    raise NotImplementedError("P3")


def downstream(dataset: str) -> list[str]:
    """Blast radius. TODO(P3): handle cycles — lineage graphs do contain them."""
    raise NotImplementedError("P3")


def upstream(dataset: str) -> list[str]:
    raise NotImplementedError("P3")
