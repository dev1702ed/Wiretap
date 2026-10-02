"""What can be read back out of OpenLineage RunEvents. P4.

Two readings, measured against each other in benchmarks/ground_truth/score.py:

- What OpenLineage's core run model implies: a run lists inputs and outputs,
  and nothing says which input fed which output, so a reader can only assume
  every input fed every output (`implied_dataset_edges`). Provenance is then
  reachability over those edges (`dataset_provenance`).
- What a DCP-aware reader recovers from the `dcp` run facet: the original
  DCP events (`dcp_events`), from which the backend graph can be rebuilt
  exactly.
"""

import json
from collections import deque

Dataset = tuple[str, str]


def implied_dataset_edges(ol_events) -> set[tuple[Dataset, Dataset, str]]:
    """(input, output, job name) for every input x output of every run."""
    runs: dict[str, dict] = {}
    for event in ol_events:
        run = runs.setdefault(
            event["run"]["runId"], {"job": event["job"]["name"], "in": set(), "out": set()}
        )
        run["in"] |= {_key(d) for d in event.get("inputs", [])}
        run["out"] |= {_key(d) for d in event.get("outputs", [])}
    return {
        (src, dst, run["job"]) for run in runs.values() for src in run["in"] for dst in run["out"]
    }


def dataset_provenance(edges, dataset: Dataset) -> set[Dataset]:
    """Every dataset that reaches `dataset` over the edges, excluding itself."""
    parents: dict[Dataset, set[Dataset]] = {}
    for src, dst, _job in edges:
        parents.setdefault(dst, set()).add(src)
    found: set[Dataset] = set()
    queue = deque([dataset])
    while queue:
        for up in parents.get(queue.popleft(), ()):
            if up not in found:
                found.add(up)
                queue.append(up)
    found.discard(dataset)
    return found


def dcp_events(ol_events) -> list[dict]:
    """The DCP events carried in `dcp` run facets, rebuilt as envelopes.

    Each distinct event once, sorted by edge_id then content.
    """
    rebuilt: dict[str, dict] = {}
    for event in ol_events:
        facet = event.get("run", {}).get("facets", {}).get("dcp")
        if not facet:
            continue
        for entry in facet["events"]:
            envelope = {
                "dcp_version": facet["dcp_version"],
                "trace_id": facet["trace_id"],
                "edge_id": entry["edge_id"],
                "parent": list(entry["parent"]),
                "op": entry["op"],
                "dataset": dict(entry["dataset"]),
                "job": dict(facet["job"]),
                "ts": entry["ts"],
            }
            if "columns" in entry:
                envelope["columns"] = list(entry["columns"])
            rebuilt[_canonical(envelope)] = envelope
    return [rebuilt[key] for key in sorted(rebuilt, key=lambda k: (rebuilt[k]["edge_id"], k))]


def _key(dataset: dict) -> Dataset:
    return dataset["namespace"], dataset["name"]


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
