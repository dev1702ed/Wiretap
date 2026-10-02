"""Lineage graph over networkx. P3.

A derived view of the event log: `build(events)` is a fold of `add` over the
events, and the result depends only on the set of events, never on their
order. HTTP emitters in different processes race, so a child routinely
arrives before its parent; a parent id that is not yet known is held as a
dangling node and linked when its event arrives.

Two graphs are kept:

- the event graph: one node per edge_id, an arc parent -> child for every
  `parent` reference. Run-level provenance walks this.
- the dataset graph: one node per dataset, an arc R -> W whenever a write W is
  parented to a read R. Dataset-level lineage (the unit comparable to
  OpenLineage) and blast radius walk this.

Nothing is inferred. In particular a write to a table followed by another
job's read of it is not linked at run level: rows carry no per-record
metadata, so that link would be a guess, and mixing guesses into attested
edges would silently corrupt precision.

In-memory, no persistence beyond the event log. That is a prototype choice,
and it breaks at scale in known ways: memory grows with every event ever
ingested, and `upstream` walks the whole history of every write to a dataset.
"""

import json

import networkx as nx

from app.identity import resolve

Dataset = tuple[str, str]


class LineageGraph:
    """Contract, fixed in advance by sdk-python/tests/test_ground_truth.py:

    g.datasets()      -> set[(namespace, name)]
    g.dataset_edges() -> set[((ns, name), (ns, name), job_name)]
    g.run_edges()     -> set[(from_job, to_job, (ns, name))]
    g.upstream(ds)    -> set[(ns, name)]: run-level provenance
    """

    def __init__(self) -> None:
        # edge_id -> node; attribute "records" is the set of distinct events
        # carrying that id. Empty for a parent referenced but not yet seen.
        self._events = nx.DiGraph()
        # dataset -> node; arc attribute "jobs" is the set of writing jobs.
        self._datasets = nx.DiGraph()
        self._run_edges: set[tuple[str, str, Dataset]] = set()
        self._writes: dict[Dataset, set[str]] = {}
        self._seen: set[str] = set()  # canonical JSON of every event added

    def add(self, event: dict) -> None:
        """Fold one event in. Adding an identical event twice is a no-op."""
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
        if canonical in self._seen:
            return
        self._seen.add(canonical)

        dataset = resolve(event["dataset"]["namespace"], event["dataset"]["name"])
        record = (event["op"], dataset, event["job"]["name"])
        edge_id = event["edge_id"]

        self._datasets.add_node(dataset)
        self._ensure_event(edge_id)
        self._records(edge_id).add(record)
        if record[0] == "write":
            self._writes.setdefault(dataset, set()).add(edge_id)
        for parent_id in event.get("parent", []):
            self._ensure_event(parent_id)
            self._events.add_edge(parent_id, edge_id)

        # Invariant: every arc P -> C links every record of P to every record
        # of C. Only arcs touching this node can have gained a pair, so relink
        # those; links are sets, so revisiting a pair is harmless. The result
        # is a function of the records and arcs alone, whatever the order.
        for parent_id in self._events.predecessors(edge_id):
            for parent in self._records(parent_id):
                for child in self._records(edge_id):
                    self._link(parent, child)
        for child_id in self._events.successors(edge_id):
            for child in self._records(child_id):
                self._link(record, child)

    def datasets(self) -> set[Dataset]:
        """Every dataset that appears in any event."""
        return set(self._datasets.nodes)

    def dataset_edges(self) -> set[tuple[Dataset, Dataset, str]]:
        """(read dataset, write dataset, writing job) for each write parented to a read."""
        return {
            (src, dst, job)
            for src, dst, jobs in self._datasets.edges(data="jobs")
            for job in jobs
        }

    def run_edges(self) -> set[tuple[str, str, Dataset]]:
        """(writing job, reading job, dataset) for each read parented to a write."""
        return set(self._run_edges)

    def upstream(self, dataset: Dataset) -> set[Dataset]:
        """Run-level provenance: every dataset `dataset` actually derives from.

        Walks parent links over events, starting from every write to the
        dataset. Never falls back to dataset-level reachability.
        """
        dataset = resolve(*dataset)
        reached: set[str] = set()
        for edge_id in self._writes.get(dataset, ()):
            if edge_id not in reached:  # an ancestor's ancestors are already in
                reached |= nx.ancestors(self._events, edge_id)
        found = {ds for edge_id in reached for _, ds, _ in self._records(edge_id)}
        found.discard(dataset)
        return found

    def dataset_upstream(self, dataset: Dataset) -> set[Dataset]:
        """Dataset-level ancestors: the baseline `upstream` is compared against."""
        dataset = resolve(*dataset)
        if dataset not in self._datasets:
            return set()
        return nx.ancestors(self._datasets, dataset) - {dataset}

    def downstream(self, dataset: Dataset) -> set[Dataset]:
        """Blast radius: dataset-level descendants. Impact analysis wants recall."""
        dataset = resolve(*dataset)
        if dataset not in self._datasets:
            return set()
        return nx.descendants(self._datasets, dataset) - {dataset}

    def dangling_parents(self) -> set[str]:
        """Parent ids referenced by some event but never seen."""
        return {
            edge_id
            for edge_id, records in self._events.nodes(data="records")
            if not records
        }

    def event_count(self) -> int:
        """Distinct events folded in; identical duplicates count once."""
        return len(self._seen)

    def snapshot(self) -> dict:
        """Everything the graph holds, in comparable form."""
        return {
            "events": {
                edge_id: frozenset(records)
                for edge_id, records in self._events.nodes(data="records")
            },
            "links": set(self._events.edges),
            "datasets": self.datasets(),
            "dataset_edges": self.dataset_edges(),
            "run_edges": self.run_edges(),
            "event_count": self.event_count(),
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LineageGraph):
            return NotImplemented
        return self.snapshot() == other.snapshot()

    __hash__ = None  # mutable

    def _ensure_event(self, edge_id: str) -> None:
        if edge_id not in self._events:
            self._events.add_node(edge_id, records=set())

    def _records(self, edge_id: str) -> set[tuple[str, Dataset, str]]:
        return self._events.nodes[edge_id]["records"]

    def _link(
        self, parent: tuple[str, Dataset, str], child: tuple[str, Dataset, str]
    ) -> None:
        parent_op, parent_ds, parent_job = parent
        child_op, child_ds, child_job = child
        if parent_op == "read" and child_op == "write":
            if not self._datasets.has_edge(parent_ds, child_ds):
                self._datasets.add_edge(parent_ds, child_ds, jobs=set())
            self._datasets.edges[parent_ds, child_ds]["jobs"].add(child_job)
        elif parent_op == "write" and child_op == "read":
            self._run_edges.add((parent_job, child_job, child_ds))


def build(events: list[dict]) -> LineageGraph:
    """Build a lineage graph from DCP events: a fold of `add` over them."""
    graph = LineageGraph()
    for event in events:
        graph.add(event)
    return graph
