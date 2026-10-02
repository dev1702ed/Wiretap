"""Score DCP's lineage graph against the ground-truth answer keys.

    python benchmarks/ground_truth/score.py

For each workload: precision and recall for nodes, dataset edges, run edges,
and each provenance entry (definitions in README.md in this directory). Every
provenance entry is scored twice: run-level (`upstream`, following parent
links over events) and a dataset-level baseline (`dataset_upstream`,
reachability over dataset edges), which is what lineage without propagation
can do.

The events come from harness.replay: DCP's real capture code with faked
database and broker I/O. These are not live runs; live replay is P5.

Needs both packages installed: pip install -e ./sdk-python -e ./backend
"""

import sys

from harness import datasets, load, replay, workloads

try:
    from app.graph import build
except ImportError:
    sys.exit("score.py needs the DCP backend installed: pip install -e ./backend")


def ratio(hits: int, total: int) -> str:
    return f"{hits}/{total} = {hits / total:.3f}" if total else f"{hits}/{total} = n/a"


def rows(key: dict):
    """Yield (label, found, expected, render) for every level of one workload."""
    ds = datasets(key)
    alias = {d: a for a, d in ds.items()}

    def name(d):
        return alias.get(d, f"{d[0]}/{d[1]}")

    def names(found):
        return [name(d) for d in found]

    g = build(replay(key))

    yield "nodes", g.datasets(), set(ds.values()), names
    yield (
        "dataset edges",
        g.dataset_edges(),
        {(ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]},
        lambda edges: [f"{name(a)}->{name(b)} ({job})" for a, b, job in edges],
    )
    yield (
        "run edges",
        g.run_edges(),
        {(e["from_job"], e["to_job"], ds[e["via"]]) for e in key["run_edges"]},
        lambda edges: [f"{a}->{b} via {name(via)}" for a, b, via in edges],
    )
    for p in key["provenance"]:
        target, expected = ds[p["dataset"]], {ds[a] for a in p["upstream"]}
        yield f"upstream({p['dataset']}) run-level", g.upstream(target), expected, names
        yield (
            f"upstream({p['dataset']}) dataset-level baseline",
            g.dataset_upstream(target),
            expected,
            names,
        )


def main() -> int:
    print("DCP ground-truth score")
    print(
        "Replays DCP's real capture code with faked database and broker I/O; not a live run."
    )
    print(
        "precision = |found & expected| / |found|    recall = |found & expected| / |expected|"
    )
    for workload in workloads():
        print()
        print(f"== {workload}")
        print(f"{'level':<52}{'precision':<16}{'recall':<16}notes")
        for label, found, expected, render in rows(load(workload)):
            hits = len(found & expected)
            notes = [f"+{x}" for x in sorted(render(found - expected))]
            notes += [f"-{x}" for x in sorted(render(expected - found))]
            line = (
                f"{label:<52}{ratio(hits, len(found)):<16}"
                f"{ratio(hits, len(expected)):<16}{' '.join(notes)}"
            )
            print(line.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
