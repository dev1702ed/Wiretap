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

def build(events: list[dict]):
    """Build a lineage graph from DCP events. P3.

    Contract, fixed in advance by sdk-python/tests/test_ground_truth.py:
        g.datasets()      -> set[(namespace, name)]
        g.dataset_edges() -> set[((ns, name), (ns, name), job_name)]
        g.run_edges()     -> set[(from_job, to_job, (ns, name))]
        g.upstream(ds)    -> set[(ns, name)]: run-level provenance, every
                             dataset `ds` derives from, following parent edges
    """
    raise NotImplementedError("P3")